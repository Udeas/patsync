"""Canonical trademark workflow status ids and labels (must match DB seed)."""

TM_STATUS_SEED: list[tuple[int, str]] = [
    (1, "Application filed"),
    (2, "Formality check Fail"),
    (3, "Formality check pass"),
    (4, "FER Issued"),
    (5, "FER Response Submitted"),
    (6, "Hearing Issued"),
    (7, "Accepted & Advertised"),
    (8, "Registered"),
]

STATUS_TM_APPLICATION_FILED = "Application filed"
STATUS_TM_FORMALITY_FAIL = "Formality check Fail"
STATUS_TM_FORMALITY_PASS = "Formality check pass"
STATUS_TM_FER_ISSUED = "FER Issued"
STATUS_TM_FER_RESPONSE = "FER Response Submitted"
STATUS_TM_HEARING = "Hearing Issued"
STATUS_TM_ACCEPTED_ADVERTISED = "Accepted & Advertised"
STATUS_TM_REGISTERED = "Registered"

STATUS_ID_TM_APPLICATION_FILED = 1
