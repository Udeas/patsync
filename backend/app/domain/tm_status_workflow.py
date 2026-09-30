"""Trademark dated-milestone workflow.

Status Model v2: every dated milestone beyond Application filed is an
independent optional branch (an application can jump straight from
Formality Check Pass - now informative, see tm_sub_status.py - to Accepted &
Advertised or Registered with no FER/hearing at all; or resolve after FER
Response without ever going to hearing; or go all the way through hearing).
The only hard rule is Application filed must exist before anything else.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from app.tm_status_catalog import (
    ALL_STATUS_IDS,
    DATED_STATUS_IDS_EDITABLE,
    RESPONSE_REQUIRES_ISSUED_STATUS_ID,
    STATUS_ID_TM_APPLICATION_FILED,
    TM_STATUS_SEED,
)

OPTIONAL_STATUS_IDS = frozenset(ALL_STATUS_IDS - {STATUS_ID_TM_APPLICATION_FILED})

_STATUS_LABELS = dict(TM_STATUS_SEED)


def is_optional_status(status_id: int) -> bool:
    return status_id in OPTIONAL_STATUS_IDS


def enabled_status_ids(filled: Mapping[int, date]) -> set[int]:
    """Status ids that may receive or keep a date given current milestones.

    Application filed unlocks everything else at once - none of the other
    dated milestones gate each other, they're independent optional branches,
    except a "Response Filed" milestone only makes sense (and is only
    offered) once its "Issued" counterpart already has a date. Ids already
    filled stay enabled even if they'd otherwise fall outside the editable
    set (legacy Formality check pass dates already on a project keep
    showing/being editable).
    """
    enabled: set[int] = set(filled.keys())

    if STATUS_ID_TM_APPLICATION_FILED not in filled:
        enabled.add(STATUS_ID_TM_APPLICATION_FILED)
        return enabled

    for status_id in DATED_STATUS_IDS_EDITABLE:
        prerequisite = RESPONSE_REQUIRES_ISSUED_STATUS_ID.get(status_id)
        if prerequisite is not None and prerequisite not in filled:
            continue
        enabled.add(status_id)
    return enabled


def _status_label(status_id: int) -> str:
    return _STATUS_LABELS.get(status_id, f"status {status_id}")


def validate_filled_timeline(filled: Mapping[int, date]) -> None:
    unknown = set(filled.keys()) - ALL_STATUS_IDS
    if unknown:
        raise ValueError(f"invalid status_id: {min(unknown)}")

    if not filled:
        return

    if STATUS_ID_TM_APPLICATION_FILED not in filled:
        raise ValueError("Application filed must be set before other statuses.")

    for response_id, issued_id in RESPONSE_REQUIRES_ISSUED_STATUS_ID.items():
        if response_id in filled and issued_id not in filled:
            raise ValueError(
                f"{_status_label(issued_id)} is required before {_status_label(response_id)}."
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
            f"Cannot set {_status_label(status_id)} until Application filed is set."
        )

    merged = dict(existing_filled)
    merged[status_id] = application_date
    validate_filled_timeline(merged)
