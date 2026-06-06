from app.config import Settings
from app.integration.jobs import claim_next_job, enqueue_dataset_import_job, enqueue_evaluation_run_job, enqueue_kpi_report_job
from app.integration.outbox import process_pending_events
from app.runtime import run_worker_iteration


class FakeJob:
    def __init__(self, *, job_type: str, payload_json: dict[str, object], job_id: str = "job_1") -> None:
        self.id = job_id
        self.job_type = job_type
        self.payload_json = payload_json
        self.status = "pending"
        self.attempts = 0
        self.max_attempts = 3
        self.claimed_at = None
        self.completed_at = None
        self.last_error = None


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self

    def all(self):
        return list(self._items)

    def __iter__(self):
        return iter(self._items)


class FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return FakeScalarResult(self._items)


class FakeSession:
    def __init__(self, *, events=None, jobs=None):
        self.events = events or []
        self.jobs = jobs or []
        self.added = []
        self.committed = False
        self.closed = False

    def add(self, item):
        self.added.append(item)
        if getattr(item, "job_type", None):
            self.jobs.append(item)

    def execute(self, statement):
        text = str(statement)
        if "integration_event" in text:
            return FakeExecuteResult(self.events)
        if "job_queue" in text:
            return FakeExecuteResult([job for job in self.jobs if job.status == "pending"])
        if "dataset_import" in text:
            return FakeExecuteResult([])
        return FakeExecuteResult([])

    def commit(self):
        self.committed = True

    def rollback(self):
        return None

    def close(self):
        self.closed = True

    def get(self, model, job_id):
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None


def test_process_pending_events_enqueues_dataset_import_job():
    event = type(
        "Event",
        (),
        {
            "event_type": "dataset.exported",
            "payload_json": {
                "dataset_export_id": "dsexp_1",
                "manifest_path": "/tmp/export.manifest.json",
                "data_path": "/tmp/export.jsonl",
            },
            "processed_at": None,
            "occurred_at": None,
        },
    )()
    session = FakeSession(events=[event])

    result = process_pending_events(session, settings=Settings())

    assert result.processed_count == 1
    assert result.imported_count == 1
    assert len(session.jobs) == 1
    assert session.jobs[0].job_type == "dataset.import"


def test_process_pending_events_enqueues_follow_on_jobs_for_phase8_events():
    from app.integration import outbox as outbox_module

    event = type(
        "Event",
        (),
        {
            "event_type": "training.completed",
            "payload_json": {"training_run_id": "train_1", "domain": "coding"},
            "processed_at": None,
            "occurred_at": None,
        },
    )()
    session = FakeSession(events=[event])

    original_create = outbox_module.create_evaluation_run
    outbox_module.create_evaluation_run = lambda session, request, settings: session.add(
        FakeJob(job_type="evaluation.run", payload_json={"evaluation_run_id": "eval_1"}, job_id="job_eval_1")
    )
    result = process_pending_events(session, settings=Settings())
    outbox_module.create_evaluation_run = original_create

    assert result.processed_count == 1
    assert result.imported_count == 0
    assert {job.job_type for job in session.jobs} == {"kpi.generate", "evaluation.run"}


def test_enqueue_kpi_report_job_creates_pending_job():
    session = FakeSession()

    job = enqueue_kpi_report_job(session)

    assert job.job_type == "kpi.generate"
    assert job.status == "pending"
    assert len(session.jobs) == 1


def test_enqueue_evaluation_run_job_creates_pending_job() -> None:
    session = FakeSession()

    job = enqueue_evaluation_run_job(session, evaluation_run_id="eval_1")

    assert job.job_type == "evaluation.run"
    assert job.status == "pending"
    assert job.payload_json["evaluation_run_id"] == "eval_1"


def test_claim_next_job_marks_job_running():
    job = FakeJob(job_type="kpi.generate", payload_json={})
    session = FakeSession(jobs=[job])

    claimed = claim_next_job(session)

    assert claimed is job
    assert claimed.status == "running"
    assert claimed.attempts == 1
