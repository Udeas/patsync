from datetime import date

import pytest

from app.domain.tm_status_workflow import (
    STATUS_ID_FER_ISSUED,
    STATUS_ID_FORMALITY_PASS,
    STATUS_ID_TM_APPLICATION_FILED,
    enabled_status_ids,
    validate_status_change,
)


def test_only_application_filed_enabled_initially():
    enabled = enabled_status_ids({})
    assert enabled == {STATUS_ID_TM_APPLICATION_FILED}


def test_after_filed_enables_formality_pass_and_optional_fail():
    filled = {STATUS_ID_TM_APPLICATION_FILED: date(2025, 1, 1)}
    enabled = enabled_status_ids(filled)
    assert 2 in enabled
    assert STATUS_ID_FORMALITY_PASS in enabled


def test_cannot_skip_formality_pass():
    filled = {
        STATUS_ID_TM_APPLICATION_FILED: date(2025, 1, 1),
    }
    with pytest.raises(ValueError, match="previous milestones"):
        validate_status_change(filled, STATUS_ID_FER_ISSUED, date(2025, 2, 1))


def test_fer_requires_formality_pass():
    filled = {
        STATUS_ID_TM_APPLICATION_FILED: date(2025, 1, 1),
        STATUS_ID_FORMALITY_PASS: date(2025, 2, 1),
    }
    validate_status_change(filled, STATUS_ID_FER_ISSUED, date(2025, 3, 1))
