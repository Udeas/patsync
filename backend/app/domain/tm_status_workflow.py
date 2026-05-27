"""Trademark status progression: linear flow with optional formality fail and accepted & advertised."""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED

STATUS_ID_FORMALITY_FAIL = 2
STATUS_ID_FORMALITY_PASS = 3
STATUS_ID_FER_ISSUED = 4
STATUS_ID_FER_RESPONSE = 5
STATUS_ID_HEARING = 6
STATUS_ID_ACCEPTED_ADVERTISED = 7
STATUS_ID_REGISTERED = 8

OPTIONAL_STATUS_IDS = frozenset({STATUS_ID_FORMALITY_FAIL, STATUS_ID_ACCEPTED_ADVERTISED})

ALL_STATUS_IDS = frozenset(range(1, 9))

REQUIRED_CHAIN = (
    STATUS_ID_TM_APPLICATION_FILED,
    STATUS_ID_FORMALITY_PASS,
    STATUS_ID_FER_ISSUED,
    STATUS_ID_FER_RESPONSE,
    STATUS_ID_HEARING,
    STATUS_ID_REGISTERED,
)

_STATUS_LABELS = {
    1: "Application filed",
    2: "Formality check Fail",
    3: "Formality check pass",
    4: "FER Issued",
    5: "FER Response Submitted",
    6: "Hearing Issued",
    7: "Accepted & Advertised",
    8: "Registered",
}


def is_optional_status(status_id: int) -> bool:
    return status_id in OPTIONAL_STATUS_IDS


def _next_required_unfilled(filled: Mapping[int, date]) -> int | None:
    for status_id in REQUIRED_CHAIN:
        if status_id not in filled:
            return status_id
    return None


def enabled_status_ids(filled: Mapping[int, date]) -> set[int]:
    """Status ids that may receive or keep a date given current milestones."""
    enabled: set[int] = set(filled.keys())

    if STATUS_ID_TM_APPLICATION_FILED not in filled:
        enabled.add(STATUS_ID_TM_APPLICATION_FILED)
        return enabled

    if STATUS_ID_FORMALITY_PASS not in filled:
        enabled.add(STATUS_ID_FORMALITY_FAIL)
        enabled.add(STATUS_ID_FORMALITY_PASS)
        return enabled

    next_required = _next_required_unfilled(filled)
    if next_required is not None and next_required != STATUS_ID_TM_APPLICATION_FILED:
        enabled.add(next_required)

    if STATUS_ID_HEARING in filled and STATUS_ID_REGISTERED not in filled:
        enabled.add(STATUS_ID_ACCEPTED_ADVERTISED)
        enabled.add(STATUS_ID_REGISTERED)

    return enabled


def _status_label(status_id: int) -> str:
    return _STATUS_LABELS.get(status_id, f"status {status_id}")


def _require_present(filled: Mapping[int, date], status_id: int) -> None:
    if status_id not in filled:
        raise ValueError(f"{_status_label(status_id)} is required before later milestones.")


def validate_filled_timeline(filled: Mapping[int, date]) -> None:
    unknown = set(filled.keys()) - ALL_STATUS_IDS
    if unknown:
        raise ValueError(f"invalid status_id: {min(unknown)}")

    if not filled:
        return

    if STATUS_ID_TM_APPLICATION_FILED not in filled:
        raise ValueError("Application filed must be set before other statuses.")

    if STATUS_ID_FORMALITY_FAIL in filled:
        _require_present(filled, STATUS_ID_TM_APPLICATION_FILED)

    if STATUS_ID_FORMALITY_PASS in filled:
        _require_present(filled, STATUS_ID_TM_APPLICATION_FILED)

    if STATUS_ID_FER_ISSUED in filled:
        _require_present(filled, STATUS_ID_FORMALITY_PASS)

    if STATUS_ID_FER_RESPONSE in filled:
        _require_present(filled, STATUS_ID_FER_ISSUED)

    if STATUS_ID_HEARING in filled:
        _require_present(filled, STATUS_ID_FER_RESPONSE)

    if STATUS_ID_ACCEPTED_ADVERTISED in filled:
        _require_present(filled, STATUS_ID_HEARING)

    if STATUS_ID_REGISTERED in filled:
        _require_present(filled, STATUS_ID_HEARING)

    allowed = enabled_status_ids(filled)
    for sid in filled:
        if sid not in allowed:
            raise ValueError(
                f"{_status_label(sid)} is not allowed until previous milestones are completed."
            )


def validate_timeline_updates(updates: Sequence[tuple[int, date]]) -> None:
    filled: dict[int, date] = {}
    for status_id, application_date in updates:
        if status_id not in ALL_STATUS_IDS:
            raise ValueError(f"invalid status_id: {status_id}")
        filled[status_id] = application_date
    validate_filled_timeline(filled)


def validate_status_change(
    existing_filled: Mapping[int, date],
    status_id: int,
    application_date: date,
) -> None:
    if status_id not in ALL_STATUS_IDS:
        raise ValueError(f"invalid status_id: {status_id}")

    if status_id not in existing_filled and status_id not in enabled_status_ids(existing_filled):
        raise ValueError(
            f"Cannot set {_status_label(status_id)} until previous milestones are completed."
        )

    merged = dict(existing_filled)
    merged[status_id] = application_date
    validate_filled_timeline(merged)
