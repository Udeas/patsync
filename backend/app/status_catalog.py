"""Canonical patent workflow status ids and labels (must match DB seed)."""

PATENT_STATUS_SEED: list[tuple[int, str]] = [
    (1, "Application Filed"),
    (2, "Secrecy directions issued"),
    (3, "FER Issued"),
    (4, "FER Response submitted"),
    (5, "Case under hearing"),
    (6, "Accepted and published"),
    (7, "Granted"),
    (8, "Abandoned"),
]

STATUS_APPLICATION_FILED = "Application Filed"
STATUS_SECRECY_DIRECTIONS = "Secrecy directions issued"
STATUS_FER_ISSUED = "FER Issued"
STATUS_FER_RESPONSE_SUBMITTED = "FER Response submitted"
STATUS_CASE_UNDER_HEARING = "Case under hearing"
STATUS_ACCEPTED_PUBLISHED = "Accepted and published"
STATUS_GRANTED = "Granted"
STATUS_ABANDONED = "Abandoned"

STATUS_ID_APPLICATION_FILED = 1
