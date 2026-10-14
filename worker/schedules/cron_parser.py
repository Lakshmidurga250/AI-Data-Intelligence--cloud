"""Cron expression parser and next-run calculator for scheduled ETL workflows."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Set


PRESET_EXPRESSIONS = {
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 0",
    "monthly": "0 0 1 * *",
    "every_15_mins": "*/15 * * * *",
    "every_30_mins": "*/30 * * * *",
}


def normalize_expression(expr: str) -> str:
    """Translate predefined interval names into 5-field cron expressions."""
    cleaned = expr.strip().lower()
    return PRESET_EXPRESSIONS.get(cleaned, cleaned)


def parse_field(field: str, min_val: int, max_val: int) -> Set[int]:
    """Parse a single cron field (wildcard, step, range, or comma-separated list)."""
    field = field.strip()
    if field == "*":
        return set(range(min_val, max_val + 1))

    if "/" in field:
        parts = field.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid step expression: '{field}'")
        base = parts[0].strip()
        step = int(parts[1])
        if step <= 0:
            raise ValueError("Step must be positive")
        start = min_val if base in ("*", "") else int(base)
        return {v for v in range(start, max_val + 1, step) if min_val <= v <= max_val}

    if "," in field:
        results = set()
        for item in field.split(","):
            results.update(parse_field(item, min_val, max_val))
        return results

    if "-" in field:
        parts = field.split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid range expression: '{field}'")
        start = int(parts[0])
        end = int(parts[1])
        if start > end:
            raise ValueError(f"Range start {start} exceeds end {end}")
        return {v for v in range(start, end + 1) if min_val <= v <= max_val}

    val = int(field)
    if not (min_val <= val <= max_val):
        raise ValueError(f"Value {val} outside bounds [{min_val}, {max_val}]")
    return {val}


def validate_cron_expression(expr: str) -> bool:
    """Validate whether an expression is a valid 5-field cron string or preset."""
    normalized = normalize_expression(expr)
    parts = normalized.split()
    if len(parts) != 5:
        return False
    try:
        parse_field(parts[0], 0, 59)
        parse_field(parts[1], 0, 23)
        parse_field(parts[2], 1, 31)
        parse_field(parts[3], 1, 12)
        parse_field(parts[4], 0, 6)
        return True
    except (ValueError, TypeError):
        return False


def calculate_next_run(expr: str, base_time: Optional[datetime] = None) -> datetime:
    """
    Calculate the next occurrence timestamp after base_time satisfying the cron specification.
    """
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    elif base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)

    normalized = normalize_expression(expr)
    parts = normalized.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: '{expr}'. Expected 5 fields or preset.")

    valid_minutes = parse_field(parts[0], 0, 59)
    valid_hours = parse_field(parts[1], 0, 23)
    valid_days = parse_field(parts[2], 1, 31)
    valid_months = parse_field(parts[3], 1, 12)
    valid_weekdays = parse_field(parts[4], 0, 6)

    # Start searching from the next whole minute
    current = base_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
    max_search_minutes = 60 * 24 * 366  # Search up to 1 year ahead

    for _ in range(max_search_minutes):
        # Python weekday: Monday is 0, Sunday is 6. Cron: Sunday is 0, Saturday is 6
        cron_weekday = (current.weekday() + 1) % 7

        if (
            current.month in valid_months
            and current.day in valid_days
            and cron_weekday in valid_weekdays
            and current.hour in valid_hours
            and current.minute in valid_minutes
        ):
            return current

        current += timedelta(minutes=1)

    # Fallback default: 1 hour ahead
    return base_time + timedelta(hours=1)
