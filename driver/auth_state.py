import time
from datetime import datetime


def get_expiry_timestamp(expiry: dict) -> float | None:
    if not isinstance(expiry, dict):
        return None

    expiry_timestamp = expiry.get("expiry_timestamp")
    if expiry_timestamp is not None:
        try:
            return float(expiry_timestamp)
        except (TypeError, ValueError):
            pass

    expiry_time = expiry.get("expiry_time")
    if expiry_time:
        try:
            return datetime.strptime(
                str(expiry_time), "%Y-%m-%d %H:%M:%S"
            ).timestamp()
        except (TypeError, ValueError):
            pass

    return None


def is_expired(expiry: dict, now: float | None = None) -> bool:
    expiry_timestamp = get_expiry_timestamp(expiry)
    if expiry_timestamp is not None:
        return expiry_timestamp <= (time.time() if now is None else now)

    remaining_seconds = expiry.get("remaining_seconds") if isinstance(expiry, dict) else None
    if remaining_seconds is not None:
        try:
            return float(remaining_seconds) <= 0
        except (TypeError, ValueError):
            pass

    return False
