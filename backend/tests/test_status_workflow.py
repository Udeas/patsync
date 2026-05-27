"""Tests for patent status workflow progression."""

from datetime import date

import pytest

from app.domain.status_workflow import (
    STATUS_ID_ABANDONED,
    STATUS_ID_APPLICATION_FILED,
    STATUS_ID_FER_ISSUED,
    STATUS_ID_FER_RESPONSE,
    STATUS_ID_GRANTED,
    STATUS_ID_HEARING,
    STATUS_ID_PUBLISHED,
    STATUS_ID_SECRECY,
    enabled_status_ids,
    get_active_path,
    validate_filled_timeline,
    validate_status_change,
    validate_timeline_updates,
)

D = date


def test_filed_only_enables_branch_starts_and_abandoned():
    filled = {STATUS_ID_APPLICATION_FILED: D(2025, 1, 1)}
    assert get_active_path(filled) == "none"
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_SECRECY in enabled
    assert STATUS_ID_FER_ISSUED in enabled
    assert STATUS_ID_ABANDONED in enabled
    assert STATUS_ID_FER_RESPONSE not in enabled


def test_direct_path_progression():
    filled = {
        STATUS_ID_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_FER_ISSUED: D(2025, 2, 1),
    }
    assert get_active_path(filled) == "direct_fer"
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_FER_RESPONSE in enabled
    assert STATUS_ID_SECRECY not in enabled

    filled[STATUS_ID_FER_RESPONSE] = D(2025, 3, 1)
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_GRANTED in enabled
    assert STATUS_ID_HEARING in enabled
    assert STATUS_ID_PUBLISHED in enabled

    validate_timeline_updates(
        [
            (1, D(2025, 1, 1)),
            (3, D(2025, 2, 1)),
            (4, D(2025, 3, 1)),
            (7, D(2025, 6, 1)),
        ]
    )


def test_secrecy_path_progression():
    filled = {
        STATUS_ID_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_SECRECY: D(2025, 2, 1),
    }
    assert get_active_path(filled) == "secrecy"
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_FER_ISSUED in enabled
    assert STATUS_ID_FER_RESPONSE not in enabled

    filled[STATUS_ID_FER_ISSUED] = D(2025, 3, 1)
    filled[STATUS_ID_FER_RESPONSE] = D(2025, 4, 1)
    validate_filled_timeline(filled)


def test_granted_requires_fer_response():
    with pytest.raises(ValueError, match="FER Response"):
        validate_timeline_updates(
            [
                (1, D(2025, 1, 1)),
                (3, D(2025, 2, 1)),
                (7, D(2025, 6, 1)),
            ]
        )


def test_cannot_add_secrecy_on_direct_path():
    existing = {
        STATUS_ID_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_FER_ISSUED: D(2025, 2, 1),
    }
    with pytest.raises(ValueError, match="until previous milestones"):
        validate_status_change(existing, STATUS_ID_SECRECY, D(2025, 3, 1))


def test_secrecy_fer_date_order():
    with pytest.raises(ValueError, match="Secrecy directions date"):
        validate_timeline_updates(
            [
                (1, D(2025, 1, 1)),
                (2, D(2025, 4, 1)),
                (3, D(2025, 2, 1)),
            ]
        )


def test_abandoned_requires_filed():
    with pytest.raises(ValueError, match="Application Filed"):
        validate_timeline_updates([(8, D(2025, 1, 1))])


def test_abandoned_after_filed_ok():
    validate_timeline_updates(
        [
            (1, D(2025, 1, 1)),
            (8, D(2025, 2, 1)),
        ]
    )


def test_fer_response_before_fer_rejected():
    with pytest.raises(ValueError):
        validate_timeline_updates(
            [
                (1, D(2025, 1, 1)),
                (4, D(2025, 2, 1)),
            ]
        )


def test_validate_status_change_blocks_skipped_step():
    existing = {
        STATUS_ID_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_FER_ISSUED: D(2025, 2, 1),
    }
    with pytest.raises(ValueError, match="until previous milestones"):
        validate_status_change(existing, STATUS_ID_GRANTED, D(2025, 6, 1))


def test_validate_status_change_allows_correction():
    existing = {
        STATUS_ID_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_FER_ISSUED: D(2025, 2, 1),
        STATUS_ID_FER_RESPONSE: D(2025, 3, 1),
    }
    validate_status_change(existing, STATUS_ID_FER_RESPONSE, D(2025, 3, 15))
