"""Dataset deduplication."""

import json


def dedupe_dataset(records: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    deduped: list[dict[str, object]] = []
    for record in records:
        fingerprint = json.dumps(
            {
                "messages": record["messages"],
                "selected_response": record["selected_response"],
                "domain": record["domain"],
                "task_type": record["task_type"],
            },
            sort_keys=True,
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(record)
    return deduped
