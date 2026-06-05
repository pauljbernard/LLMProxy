from app.datasets.dedupe import dedupe_dataset
from app.datasets.normalization import normalize_dataset
from app.datasets.splitter import split_dataset


def test_normalize_dataset_trims_content() -> None:
    records = [
        {
            "candidate_id": "cand_1",
            "domain": "coding",
            "task_type": "code_review",
            "messages": [{"role": "user", "content": "  Review patch  "}],
            "selected_response": "  Looks good  ",
        }
    ]
    normalized = normalize_dataset(records)
    assert normalized[0]["messages"][0]["content"] == "Review patch"
    assert normalized[0]["selected_response"] == "Looks good"


def test_dedupe_dataset_removes_duplicate_records() -> None:
    records = [
        {
            "candidate_id": "cand_1",
            "domain": "coding",
            "task_type": "code_review",
            "messages": [{"role": "user", "content": "Review patch"}],
            "selected_response": "Looks good",
        },
        {
            "candidate_id": "cand_2",
            "domain": "coding",
            "task_type": "code_review",
            "messages": [{"role": "user", "content": "Review patch"}],
            "selected_response": "Looks good",
        },
    ]
    deduped = dedupe_dataset(records)
    assert len(deduped) == 1


def test_split_dataset_is_deterministic() -> None:
    records = [
        {"candidate_id": f"cand_{i}", "domain": "coding", "task_type": "code_review", "messages": [], "selected_response": "x"}
        for i in range(10)
    ]
    split_one = split_dataset(records)
    split_two = split_dataset(records)
    assert split_one == split_two
    assert len(split_one["train"]) == 8
