"""Tests for trademark status workflow progression (Status Model v2)."""

from datetime import date

import pytest

from app.domain.tm_status_workflow import (
    enabled_status_ids,
    validate_filled_timeline,
    validate_status_change,
)
from app.tm_status_catalog import (
    STATUS_ID_TM_APPLICATION_FILED,
    STATUS_ID_TM_FER_ISSUED,
    STATUS_ID_TM_FER_RESPONSE,
    STATUS_ID_TM_FORMALITY_FAIL,
    STATUS_ID_TM_FORMALITY_FAIL_RESPONSE,
    STATUS_ID_TM_REGISTERED,
    STATUS_ID_TM_RENEWED,
)

D = date


def test_only_application_filed_enabled_initially():
    enabled = enabled_status_ids({})
    assert enabled == {STATUS_ID_TM_APPLICATION_FILED}


def test_after_filed_formality_fail_is_available_but_not_its_response():
    filled = {STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1)}
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_TM_FORMALITY_FAIL in enabled
    assert STATUS_ID_TM_FORMALITY_FAIL_RESPONSE not in enabled


def test_formality_fail_response_enabled_once_formality_fail_dated():
    filled = {
        STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_TM_FORMALITY_FAIL: D(2025, 2, 1),
    }
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_TM_FORMALITY_FAIL_RESPONSE in enabled


def test_formality_fail_response_before_formality_fail_rejected():
    with pytest.raises(ValueError, match="Formality check Fail"):
        validate_filled_timeline(
            {
                STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1),
                STATUS_ID_TM_FORMALITY_FAIL_RESPONSE: D(2025, 2, 1),
            }
        )


def test_formality_fail_response_after_formality_fail_ok():
    validate_filled_timeline(
        {
            STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1),
            STATUS_ID_TM_FORMALITY_FAIL: D(2025, 2, 1),
            STATUS_ID_TM_FORMALITY_FAIL_RESPONSE: D(2025, 3, 1),
        }
    )


def test_fer_response_only_enabled_once_fer_issued_dated():
    filled = {STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1)}
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_TM_FER_ISSUED in enabled
    assert STATUS_ID_TM_FER_RESPONSE not in enabled

    filled[STATUS_ID_TM_FER_ISSUED] = D(2025, 2, 1)
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_TM_FER_RESPONSE in enabled


def test_fer_response_before_fer_issued_rejected():
    with pytest.raises(ValueError, match="FER Issued"):
        validate_filled_timeline(
            {
                STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1),
                STATUS_ID_TM_FER_RESPONSE: D(2025, 2, 1),
            }
        )


def test_renewed_only_enabled_once_registered_dated():
    filled = {STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1)}
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_TM_REGISTERED in enabled
    assert STATUS_ID_TM_RENEWED not in enabled

    filled[STATUS_ID_TM_REGISTERED] = D(2025, 2, 1)
    enabled = enabled_status_ids(filled)
    assert STATUS_ID_TM_RENEWED in enabled


def test_renewed_before_registered_rejected():
    with pytest.raises(ValueError, match="Registered"):
        validate_filled_timeline(
            {
                STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1),
                STATUS_ID_TM_RENEWED: D(2025, 2, 1),
            }
        )


def test_validate_status_change_allows_correction():
    existing = {
        STATUS_ID_TM_APPLICATION_FILED: D(2025, 1, 1),
        STATUS_ID_TM_FORMALITY_FAIL: D(2025, 2, 1),
        STATUS_ID_TM_FORMALITY_FAIL_RESPONSE: D(2025, 3, 1),
    }
    validate_status_change(existing, STATUS_ID_TM_FORMALITY_FAIL_RESPONSE, D(2025, 3, 15))
