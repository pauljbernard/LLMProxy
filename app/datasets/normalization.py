"""Dataset normalization."""


def normalize_dataset(records: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for record in records:
        normalized.append(
            {
                **record,
                "messages": [
                    {
                        "role": message["role"],
                        "content": str(message["content"]).strip(),
                    }
                    for message in record["messages"]
                ],
                "selected_response": str(record["selected_response"]).strip(),
                "domain": str(record["domain"]).strip(),
                "task_type": str(record["task_type"]).strip(),
            }
        )
    return normalized
