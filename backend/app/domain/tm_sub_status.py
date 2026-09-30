"""Combines dated milestones and the informative sub-status label into a
single "current status" for display, plus the coarser 5-phase main-status
badge. See app/tm_status_catalog.py for the underlying catalog/ordering."""

from __future__ import annotations

from app.tm_status_catalog import (
    DISPLAY_SEQUENCE,
    STATUS_NAME_TO_PHASE,
    STATUS_TM_APPLICATION_FILED,
    SUB_STATUS_CHOICES,
)

_RANK = {name: index for index, name in enumerate(DISPLAY_SEQUENCE)}


def is_valid_sub_status(value: str | None) -> bool:
    return value is None or value in SUB_STATUS_CHOICES


def compute_display_status(
    sub_status: str | None,
    dated_status_names: list[str],
) -> str:
    """The single most-advanced status name to show as "current status" -
    whichever of the dated milestones (that actually have a date) or the
    informative sub-status ranks highest in real-world chronological order.
    A later dated milestone always beats a stale sub-status once it lands;
    a sub-status set after the latest dated milestone takes precedence
    until a later date arrives."""
    candidates = list(dated_status_names)
    if sub_status:
        candidates.append(sub_status)
    if not candidates:
        return STATUS_TM_APPLICATION_FILED
    return max(candidates, key=lambda name: _RANK.get(name, -1))


def main_status_phase_for(display_status_name: str) -> str:
    return STATUS_NAME_TO_PHASE.get(display_status_name, "")
