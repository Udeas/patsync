"""Canonical trademark workflow status ids and labels (must match DB seed).

Status Model v2: dated milestones (tm_status / tm_application_state, as
before) plus a separate set of informative "sub-status" labels that carry no
date and no document - see app/domain/tm_status_workflow.py and
app/domain/tm_sub_status.py for how the two combine into a single displayed
"current status" and a coarser 5-phase "main status" badge.

Formality check pass (3) is kept in the seed so old recorded dates for
existing projects keep displaying, but is no longer offered as an editable
dated milestone going forward - it's an informative sub-status instead.
Every other "X Issued" / "X Response Filed" pair IS a real dated milestone:
entering the response date is what clears the issued date's reminder.
"""

TM_STATUS_SEED: list[tuple[int, str]] = [
    (1, "Application filed"),
    (2, "Formality check Fail"),
    (3, "Formality check pass"),
    (4, "FER Issued"),
    (5, "FER Response Filed"),
    (6, "Hearing Issued"),
    (7, "Accepted & Advertised"),
    (8, "Registered"),
    (9, "Notice U/s 132 Issued"),
    (10, "Notice U/s 132 Response Filed"),
    (11, "Written Response to hearing submitted"),
]

STATUS_TM_APPLICATION_FILED = "Application filed"
STATUS_TM_FORMALITY_FAIL = "Formality check Fail"
STATUS_TM_FORMALITY_PASS = "Formality check pass"
STATUS_TM_FER_ISSUED = "FER Issued"
STATUS_TM_FER_RESPONSE = "FER Response Filed"
STATUS_TM_HEARING = "Hearing Issued"
STATUS_TM_ACCEPTED_ADVERTISED = "Accepted & Advertised"
STATUS_TM_REGISTERED = "Registered"
STATUS_TM_NOTICE_132_ISSUED = "Notice U/s 132 Issued"
STATUS_TM_NOTICE_132_RESPONSE = "Notice U/s 132 Response Filed"
STATUS_TM_WRITTEN_RESPONSE_TO_HEARING = "Written Response to hearing submitted"

STATUS_ID_TM_APPLICATION_FILED = 1
STATUS_ID_TM_FORMALITY_FAIL = 2
STATUS_ID_TM_FORMALITY_PASS = 3
STATUS_ID_TM_FER_ISSUED = 4
STATUS_ID_TM_FER_RESPONSE = 5
STATUS_ID_TM_HEARING = 6
STATUS_ID_TM_ACCEPTED_ADVERTISED = 7
STATUS_ID_TM_REGISTERED = 8
STATUS_ID_TM_NOTICE_132_ISSUED = 9
STATUS_ID_TM_NOTICE_132_RESPONSE = 10
STATUS_ID_TM_WRITTEN_RESPONSE_TO_HEARING = 11

# Dated milestones still offered for new entry in the timeline editor.
# (3) Formality check pass is deliberately excluded - it's an informative
# sub-status now (see below), still shown read-only if a project already
# has one dated from before this change.
DATED_STATUS_IDS_EDITABLE = frozenset(
    {
        STATUS_ID_TM_APPLICATION_FILED,
        STATUS_ID_TM_FORMALITY_FAIL,
        STATUS_ID_TM_FER_ISSUED,
        STATUS_ID_TM_FER_RESPONSE,
        STATUS_ID_TM_NOTICE_132_ISSUED,
        STATUS_ID_TM_NOTICE_132_RESPONSE,
        STATUS_ID_TM_HEARING,
        STATUS_ID_TM_WRITTEN_RESPONSE_TO_HEARING,
        STATUS_ID_TM_ACCEPTED_ADVERTISED,
        STATUS_ID_TM_REGISTERED,
    }
)

# All ids that may still appear historically (superset of the editable set).
ALL_STATUS_IDS = frozenset({sid for sid, _ in TM_STATUS_SEED})

DEPRECATED_DATED_STATUS_IDS = frozenset({STATUS_ID_TM_FORMALITY_PASS})

# A "Response Filed" dated milestone only makes sense - and is only offered
# in the editor - once its "Issued" counterpart already has a date.
RESPONSE_REQUIRES_ISSUED_STATUS_ID: dict[int, int] = {
    STATUS_ID_TM_FER_RESPONSE: STATUS_ID_TM_FER_ISSUED,
    STATUS_ID_TM_NOTICE_132_RESPONSE: STATUS_ID_TM_NOTICE_132_ISSUED,
    STATUS_ID_TM_WRITTEN_RESPONSE_TO_HEARING: STATUS_ID_TM_HEARING,
}

# --- Informative sub-statuses: no date, no document, purely a label. -------

SUB_STATUS_FORMALITY_PASS = "Formality check pass"
SUB_STATUS_READY_FOR_EXAMINATION = "Ready for Examination"
SUB_STATUS_UNDER_EXAMINATION = "Under Examination"
SUB_STATUS_UNDER_HEARING = "Under Hearing"

SUB_STATUS_CHOICES: list[str] = [
    SUB_STATUS_FORMALITY_PASS,
    SUB_STATUS_READY_FOR_EXAMINATION,
    SUB_STATUS_UNDER_EXAMINATION,
    SUB_STATUS_UNDER_HEARING,
]

# --- Main status: 5 coarse phases shown as the big header badge. -----------

PHASE_APPLICATION_FILED = "Application Filed"
PHASE_OBJECTED = "Objected"
PHASE_HEARING = "Hearing"
PHASE_ACCEPTED_ADVERTISED = "Accepted and Advertised"
PHASE_REGISTERED = "Registered"

MAIN_STATUS_PHASES: list[str] = [
    PHASE_APPLICATION_FILED,
    PHASE_OBJECTED,
    PHASE_HEARING,
    PHASE_ACCEPTED_ADVERTISED,
    PHASE_REGISTERED,
]

# Every displayable status name (dated or informative) maps to one phase.
STATUS_NAME_TO_PHASE: dict[str, str] = {
    STATUS_TM_APPLICATION_FILED: PHASE_APPLICATION_FILED,
    STATUS_TM_FORMALITY_FAIL: PHASE_APPLICATION_FILED,
    STATUS_TM_FORMALITY_PASS: PHASE_APPLICATION_FILED,
    SUB_STATUS_READY_FOR_EXAMINATION: PHASE_APPLICATION_FILED,
    SUB_STATUS_UNDER_EXAMINATION: PHASE_APPLICATION_FILED,
    STATUS_TM_FER_ISSUED: PHASE_OBJECTED,
    STATUS_TM_FER_RESPONSE: PHASE_OBJECTED,
    STATUS_TM_NOTICE_132_ISSUED: PHASE_OBJECTED,
    STATUS_TM_NOTICE_132_RESPONSE: PHASE_OBJECTED,
    SUB_STATUS_UNDER_HEARING: PHASE_HEARING,
    STATUS_TM_HEARING: PHASE_HEARING,
    STATUS_TM_WRITTEN_RESPONSE_TO_HEARING: PHASE_HEARING,
    STATUS_TM_ACCEPTED_ADVERTISED: PHASE_ACCEPTED_ADVERTISED,
    STATUS_TM_REGISTERED: PHASE_REGISTERED,
}

# Ordinal rank (real-world chronological order) across dated milestones AND
# informative sub-statuses together. The "current status" shown to the user
# is whichever of {every dated status with a date} union {the sub-status, if
# set} has the HIGHEST rank here - so a later dated milestone always wins
# over a stale informative label, and a sub-status set after the latest
# dated milestone correctly takes precedence until a later date lands.
DISPLAY_SEQUENCE: list[str] = [
    STATUS_TM_APPLICATION_FILED,
    STATUS_TM_FORMALITY_FAIL,
    STATUS_TM_FORMALITY_PASS,
    SUB_STATUS_READY_FOR_EXAMINATION,
    SUB_STATUS_UNDER_EXAMINATION,
    STATUS_TM_FER_ISSUED,
    STATUS_TM_FER_RESPONSE,
    STATUS_TM_NOTICE_132_ISSUED,
    STATUS_TM_NOTICE_132_RESPONSE,
    SUB_STATUS_UNDER_HEARING,
    STATUS_TM_HEARING,
    STATUS_TM_WRITTEN_RESPONSE_TO_HEARING,
    STATUS_TM_ACCEPTED_ADVERTISED,
    STATUS_TM_REGISTERED,
]

# Display-order rank for each dated milestone's own status name - used to
# sort the timeline editor's rows in real-world chronological order instead
# of raw tm_status.id (ids are assigned by when a status was added to the
# catalog, e.g. Notice U/s 132 Issued got id 9 well after Registered's id 8,
# but it belongs between FER Response and Hearing in the displayed list).
DATED_STATUS_DISPLAY_RANK: dict[str, int] = {
    name: index for index, name in enumerate(DISPLAY_SEQUENCE)
}
