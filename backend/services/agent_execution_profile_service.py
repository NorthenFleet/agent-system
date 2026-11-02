"""Operator-owned model profiles; tasks cannot supply model or tool policy."""
import os

ROLES = {"planner", "worker", "advisor"}
THINKING = {"off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra"}


def resolve_profile(role: str, *, required: bool = False) -> dict:
    if role not in ROLES:
        raise ValueError("Unknown execution role")
    model = os.getenv(f"COMMAND_CENTER_{role.upper()}_MODEL", "").strip()
    thinking = os.getenv(f"COMMAND_CENTER_{role.upper()}_THINKING", "").strip()
    if required and not model:
        raise ValueError(f"{role} model profile is not configured")
    if len(model) > 200 or any(c.isspace() for c in model) or model.startswith("-"):
        raise ValueError("Invalid configured model")
    if thinking and thinking not in THINKING:
        raise ValueError("Invalid configured thinking level")
    return {"role": role, "requested_model": model or None, "requested_thinking": thinking or None,
            "actual_model": None, "actual_provider": None, "usage": None, "cost_usd": None}
