from typing import Any


class ValidationError(ValueError):
    pass


def _require_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if value is None:
        raise ValidationError(f"Missing required field: {key}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Field must be numeric: {key}") from exc


def validate_live_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("Payload must be a JSON object.")
    _require_number(payload, "total_generation_mw")
    if "gencos" in payload and not isinstance(payload["gencos"], list):
        raise ValidationError("Field must be an array: gencos")
    disco_profile = payload.get("disco_profile")
    if disco_profile is not None:
        if not isinstance(disco_profile, dict):
            raise ValidationError("Field must be an object: disco_profile")
        if "discos" in disco_profile and not isinstance(disco_profile["discos"], list):
            raise ValidationError("Field must be an array: disco_profile.discos")


def bounded_float(raw: str | None, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(raw) if raw is not None else default
    except ValueError:
        parsed = default
    return min(max(parsed, minimum), maximum)


def bounded_int(raw: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(raw) if raw is not None else default
    except ValueError:
        parsed = default
    return min(max(parsed, minimum), maximum)
