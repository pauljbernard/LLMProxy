"""Routing engine stub."""

from app.proxy.policy import policy_version


def select_route() -> dict[str, str]:
    return {"selected_mode": "frontier_single", "policy_version": policy_version()}
