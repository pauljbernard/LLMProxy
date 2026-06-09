"""Dataset split helpers."""


def split_dataset(
    records: list[dict[str, object]],
    *,
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
) -> dict[str, list[dict[str, object]]]:
    ordered = sorted(records, key=lambda item: item["candidate_id"])
    total = len(ordered)
    if total == 0:
        return {"train": [], "validation": [], "test": []}
    if total == 1:
        return {"train": ordered[:1], "validation": [], "test": []}

    train_count = max(1, int(total * train_ratio))
    validation_count = int(total * validation_ratio)
    test_count = total - train_count - validation_count

    if total >= 2 and validation_count == 0:
        validation_count = 1
        if train_count > 1:
            train_count -= 1
        elif test_count > 0:
            test_count -= 1
    if total >= 3 and test_count == 0:
        test_count = 1
        if train_count > 1:
            train_count -= 1
        elif validation_count > 1:
            validation_count -= 1

    while train_count + validation_count + test_count > total:
        if train_count > 1:
            train_count -= 1
        elif test_count > 0:
            test_count -= 1
        else:
            validation_count -= 1

    while train_count + validation_count + test_count < total:
        train_count += 1

    train_end = train_count
    validation_end = train_end + validation_count
    return {
        "train": ordered[:train_end],
        "validation": ordered[train_end:validation_end],
        "test": ordered[validation_end:],
    }
