"""Dataset split helpers."""


def split_dataset(
    records: list[dict[str, object]],
    *,
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
) -> dict[str, list[dict[str, object]]]:
    ordered = sorted(records, key=lambda item: item["candidate_id"])
    total = len(ordered)
    train_end = max(1, int(total * train_ratio)) if total else 0
    validation_end = train_end + int(total * validation_ratio)
    return {
        "train": ordered[:train_end],
        "validation": ordered[train_end:validation_end],
        "test": ordered[validation_end:],
    }
