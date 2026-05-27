"""Patent application status progression: mutually exclusive FER vs Secrecy paths."""

from __future__ import annotations

from datetime import date
from typing import Literal, Mapping, Sequence

from app.status_catalog import STATUS_ID_APPLICATION_FILED

ActivePath = Literal["none", "direct_fer", "secrecy"]

STATUS_ID_SECRECY = 2
STATUS_ID_FER_ISSUED = 3
STATUS_ID_FER_RESPONSE = 4
STATUS_ID_HEARING = 5
STATUS_ID_PUBLISHED = 6
STATUS_ID_GRANTED = 7
STATUS_ID_ABANDONED = 8

OPTIONAL_STATUS_IDS = frozenset({STATUS_ID_HEARING, STATUS_ID_PUBLISHED})

ALL_STATUS_IDS = frozenset(range(1, 9))

_STATUS_LABELS = {
    1: "Application Filed",
    2: "Secrecy directions issued",
    3: "FER Issued",
    4: "FER Response submitted",
    5: "Case under hearing",
    6: "Accepted and published",
    7: "Granted",
    8: "Abandoned",
}


def get_active_path(filled: Mapping[int, date]) -> ActivePath:
    if STATUS_ID_SECRECY in filled:
        return "secrecy"
    if STATUS_ID_FER_ISSUED in filled:
        return "direct_fer"
    return "none"


def is_optional_status(status_id: int) -> bool:
    return status_id in OPTIONAL_STATUS_IDS


def enabled_status_ids(filled: Mapping[int, date]) -> set[int]:
    """Status ids that may receive or keep a date given current milestones."""
    enabled: set[int] = set(filled.keys())

    if STATUS_ID_APPLICATION_FILED not in filled:
        enabled.add(STATUS_ID_APPLICATION_FILED)
        return enabled

    enabled.add(STATUS_ID_ABANDONED)

    path = get_active_path(filled)

    if path == "none":
        enabled.add(STATUS_ID_SECRECY)
        enabled.add(STATUS_ID_FER_ISSUED)
        return enabled

    if path == "direct_fer":
        if STATUS_ID_FER_RESPONSE not in filled:
            enabled.add(STATUS_ID_FER_RESPONSE)
        else:
            enabled.update(OPTIONAL_STATUS_IDS)
            enabled.add(STATUS_ID_GRANTED)
        return enabled

    # secrecy path
    if STATUS_ID_FER_ISSUED not in filled:
        enabled.add(STATUS_ID_FER_ISSUED)
    elif STATUS_ID_FER_RESPONSE not in filled:
        enabled.add(STATUS_ID_FER_RESPONSE)
    else:
        enabled.update(OPTIONAL_STATUS_IDS)
        enabled.add(STATUS_ID_GRANTED)
    return enabled


def _status_label(status_id: int) -> str:
    return _STATUS_LABELS.get(status_id, f"status {status_id}")


def validate_filled_timeline(filled: Mapping[int, date]) -> None:
    """Raise ValueError if milestone set violates workflow rules."""
    unknown = set(filled.keys()) - ALL_STATUS_IDS
    if unknown:
        raise ValueError(f"invalid status_id: {min(unknown)}")

    if not filled:
        return

    if STATUS_ID_APPLICATION_FILED not in filled:
        raise ValueError("Application Filed must be set before other statuses.")

    if STATUS_ID_SECRECY in filled and STATUS_ID_FER_ISSUED in filled:
        if filled[STATUS_ID_SECRECY] > filled[STATUS_ID_FER_ISSUED]:
            raise ValueError(
                "Secrecy directions date must be on or before FER Issued date."
            )

    path = get_active_path(filled)

    if path == "none":
        for sid in filled:
            if sid not in (STATUS_ID_APPLICATION_FILED, STATUS_ID_ABANDONED):
                raise ValueError(
                    "Choose either Secrecy directions or FER Issued after Application Filed."
                )
        return

    if path == "direct_fer":
        if STATUS_ID_SECRECY in filled:
            raise ValueError(
                "Secrecy directions cannot be set on the direct FER path."
            )
        _require_present(filled, STATUS_ID_FER_ISSUED)
    else:
        _require_present(filled, STATUS_ID_SECRECY)

    if STATUS_ID_FER_RESPONSE in filled or STATUS_ID_GRANTED in filled:
        _require_present(filled, STATUS_ID_FER_ISSUED)
        _require_present(filled, STATUS_ID_FER_RESPONSE)

    if STATUS_ID_GRANTED in filled:
        _require_present(filled, STATUS_ID_FER_RESPONSE)

    for optional_id in OPTIONAL_STATUS_IDS:
        if optional_id in filled:
            _require_present(filled, STATUS_ID_FER_RESPONSE)

    allowed = enabled_status_ids(filled) | {STATUS_ID_ABANDONED}
    for sid in filled:
        if sid not in allowed:
            raise ValueError(
                f"{_status_label(sid)} is not allowed for the current workflow path."
            )


def _require_present(filled: Mapping[int, date], status_id: int) -> None:
    if status_id not in filled:
        raise ValueError(f"{_status_label(status_id)} is required before later milestones.")


def validate_timeline_updates(
    updates: Sequence[tuple[int, date]],
) -> None:
    """Validate a full timeline payload (only statuses with dates)."""
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
    """Validate adding or updating one status against existing milestones."""
    if status_id not in ALL_STATUS_IDS:
        raise ValueError(f"invalid status_id: {status_id}")

    if status_id not in existing_filled and status_id not in enabled_status_ids(
        existing_filled
    ):
        raise ValueError(
            f"Cannot set {_status_label(status_id)} until previous milestones are completed."
        )

    merged = dict(existing_filled)
    merged[status_id] = application_date
    validate_filled_timeline(merged)
