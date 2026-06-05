from fastapi.testclient import TestClient

from app.main import app


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    def add(self, item) -> None:
        self.added.append(item)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        return None


def test_import_dataset_requires_auth() -> None:
    client = TestClient(app)
    response = client.post("/datasets/import", json={"dataset_export_id": "x", "manifest_path": "a", "data_path": "b"})
    assert response.status_code == 401
