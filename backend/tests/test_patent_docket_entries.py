"""Auto-docketed Indian filing-formality deadlines (Rule 10, 135(1), 12(1A), 12(2)).

Acceptance criteria covered:
- non-provisional project creates the correct subset of items with correct due dates
  (sample: filing date 2026-09-03 -> Assignment 2027-03-03, POA 2026-12-03,
  Form 3 2027-03-03, priority-document target 2026-12-03)
- provisional project creates none of these items
- PCT national phase project claiming priority gets a priority-document item too
- entering FER date creates exactly one "Form 3 with FER compliance" item; correcting
  it updates the due date without creating a second one
- idempotency on repeated project saves
"""

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.patents.docket import ITEM_ASSIGNMENT, ITEM_FORM3_FIRST, ITEM_FORM3_UPDATED, ITEM_POA, ITEM_PRIORITY_DOCUMENT
from app.patents.patent_status_catalog import (
    STATUS_ID_APPLICATION_FILED,
    STATUS_ID_FER_ISSUED,
    STATUS_ID_REQUEST_FOR_EXAMINATION,
)
from app.patents.schemas import (
    PatentInternationalInput,
    PatentInventorInput,
    PatentPriorityInput,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectUpdate,
    PatentTimelineStatusUpdate,
)
from app.patents.service import create_project, update_project_detail, update_status_event


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _base_payload(**overrides) -> PatentProjectCreate:
    kwargs = dict(
        project_mode="final",
        application_type="Convention",
        docket_no="DCKT-DOCKET-1",
        in_application_no="202611012345",
        in_application_date=date(2026, 9, 3),
        applicant_name="Acme",
        applicant_country="IN",
        applicant_address="Address",
        applicants=[],
        inventors=[PatentInventorInput(name="Jane Inventor", nationality="IN", address="Inventor Address")],
        priorities=[
            PatentPriorityInput(
                priority_application_no="US1234",
                priority_application_date=date(2025, 9, 3),
                country="US",
                title="Widget",
            )
        ],
    )
    kwargs.update(overrides)
    return PatentProjectCreate(**kwargs)


def test_non_provisional_creates_all_four_items_with_correct_due_dates() -> None:
    with _make_session() as session:
        created = create_project(session, _base_payload())
        by_type = {e["item_type"]: e for e in created["docket_entries"]}
        assert set(by_type) == {ITEM_ASSIGNMENT, ITEM_PRIORITY_DOCUMENT, ITEM_POA, ITEM_FORM3_FIRST}
        assert by_type[ITEM_ASSIGNMENT]["due_date"] == date(2027, 3, 3)
        assert by_type[ITEM_POA]["due_date"] == date(2026, 12, 3)
        assert by_type[ITEM_FORM3_FIRST]["due_date"] == date(2027, 3, 3)
        assert by_type[ITEM_PRIORITY_DOCUMENT]["due_date"] == date(2026, 12, 3)
        assert by_type[ITEM_PRIORITY_DOCUMENT]["is_internal_target"] is True
        assert by_type[ITEM_ASSIGNMENT]["is_internal_target"] is False


def test_provisional_project_creates_no_docket_entries() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            _base_payload(
                project_mode="draft",
                application_type="Provisional Application",
                docket_no="DCKT-DOCKET-2",
                in_application_no=None,
                in_application_date=date(2026, 9, 3),
                priorities=[],
            ),
        )
        assert created["docket_entries"] == []


def test_ordinary_application_without_priority_skips_priority_document_item() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            _base_payload(
                application_type="Non-Provisional Application",
                docket_no="DCKT-DOCKET-3",
                priorities=[],
            ),
        )
        by_type = {e["item_type"] for e in created["docket_entries"]}
        assert ITEM_PRIORITY_DOCUMENT not in by_type
        assert by_type == {ITEM_ASSIGNMENT, ITEM_POA, ITEM_FORM3_FIRST}


def test_pct_national_phase_claiming_priority_gets_priority_document_item() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            _base_payload(
                application_type="PCT National Phase Entry",
                docket_no="DCKT-DOCKET-4",
                international_applications=[
                    PatentInternationalInput(
                        international_application_no="PCT/US2025/012345",
                        international_application_date=date(2025, 9, 3),
                    )
                ],
            ),
        )
        by_type = {e["item_type"]: e for e in created["docket_entries"]}
        assert ITEM_PRIORITY_DOCUMENT in by_type
        assert by_type[ITEM_PRIORITY_DOCUMENT]["due_date"] == date(2026, 12, 3)


def test_proof_of_right_furnished_auto_satisfies_assignment_item_but_still_creates_it() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            _base_payload(docket_no="DCKT-DOCKET-5", proof_of_right_furnished=True),
        )
        by_type = {e["item_type"]: e for e in created["docket_entries"]}
        assert ITEM_ASSIGNMENT in by_type
        assert by_type[ITEM_ASSIGNMENT]["auto_satisfied"] is True
        assert by_type[ITEM_ASSIGNMENT]["closure_date"] is not None


def test_repeated_project_update_does_not_duplicate_docket_entries() -> None:
    with _make_session() as session:
        created = create_project(session, _base_payload(docket_no="DCKT-DOCKET-6"))
        project_id = created["id"]
        assert len(created["docket_entries"]) == 4

        # A plain application-detail update (no docket regeneration hook) must
        # not touch docket entries at all.
        from app.patents.service import get_project

        for _ in range(2):
            update_project_detail(
                session,
                project_id,
                PatentProjectDetailUpdate(
                    application=PatentProjectUpdate(
                        docket_no="DCKT-DOCKET-6",
                        applicant_name="Acme",
                        applicant_country="IN",
                        applicant_address="Address",
                    ),
                    timeline_updates=[],
                ),
            )
        reloaded = get_project(session, project_id)
        assert len(reloaded["docket_entries"]) == 4


def test_fer_date_creates_exactly_one_form3_updated_item() -> None:
    with _make_session() as session:
        created = create_project(session, _base_payload(docket_no="DCKT-DOCKET-7"))
        project_id = created["id"]

        updated = update_project_detail(
            session,
            project_id,
            PatentProjectDetailUpdate(
                application=PatentProjectUpdate(
                    docket_no="DCKT-DOCKET-7",
                    applicant_name="Acme",
                    applicant_country="IN",
                    applicant_address="Address",
                ),
                timeline_updates=[
                    PatentTimelineStatusUpdate(
                        status_id=STATUS_ID_APPLICATION_FILED, status_date=date(2026, 9, 3)
                    ),
                    PatentTimelineStatusUpdate(
                        status_id=STATUS_ID_REQUEST_FOR_EXAMINATION, status_date=date(2026, 10, 1)
                    ),
                    PatentTimelineStatusUpdate(status_id=STATUS_ID_FER_ISSUED, status_date=date(2026, 11, 1)),
                ],
            ),
        )
        form3_updated = [e for e in updated["docket_entries"] if e["item_type"] == ITEM_FORM3_UPDATED]
        assert len(form3_updated) == 1
        assert form3_updated[0]["due_date"] == date(2027, 2, 1)


def test_correcting_fer_date_updates_due_date_without_duplicate() -> None:
    with _make_session() as session:
        created = create_project(session, _base_payload(docket_no="DCKT-DOCKET-8"))
        project_id = created["id"]

        def _set_fer(fer_date: date) -> dict:
            return update_project_detail(
                session,
                project_id,
                PatentProjectDetailUpdate(
                    application=PatentProjectUpdate(
                        docket_no="DCKT-DOCKET-8",
                        applicant_name="Acme",
                        applicant_country="IN",
                        applicant_address="Address",
                    ),
                    timeline_updates=[
                        PatentTimelineStatusUpdate(
                            status_id=STATUS_ID_APPLICATION_FILED, status_date=date(2026, 9, 3)
                        ),
                        PatentTimelineStatusUpdate(
                            status_id=STATUS_ID_REQUEST_FOR_EXAMINATION, status_date=date(2026, 10, 1)
                        ),
                        PatentTimelineStatusUpdate(status_id=STATUS_ID_FER_ISSUED, status_date=fer_date),
                    ],
                ),
            )

        _set_fer(date(2026, 11, 1))
        corrected = _set_fer(date(2026, 11, 15))

        form3_updated = [e for e in corrected["docket_entries"] if e["item_type"] == ITEM_FORM3_UPDATED]
        assert len(form3_updated) == 1
        assert form3_updated[0]["due_date"] == date(2027, 2, 15)


def test_fer_date_via_single_status_endpoint_also_creates_form3_updated_item() -> None:
    with _make_session() as session:
        created = create_project(session, _base_payload(docket_no="DCKT-DOCKET-9"))
        project_id = created["id"]

        update_status_event(session, project_id, STATUS_ID_REQUEST_FOR_EXAMINATION, date(2026, 10, 1))
        updated = update_status_event(session, project_id, STATUS_ID_FER_ISSUED, date(2026, 11, 1))
        form3_updated = [e for e in updated["docket_entries"] if e["item_type"] == ITEM_FORM3_UPDATED]
        assert len(form3_updated) == 1
        assert form3_updated[0]["due_date"] == date(2027, 2, 1)

        updated_again = update_status_event(session, project_id, STATUS_ID_FER_ISSUED, date(2026, 12, 1))
        form3_updated_again = [
            e for e in updated_again["docket_entries"] if e["item_type"] == ITEM_FORM3_UPDATED
        ]
        assert len(form3_updated_again) == 1
        assert form3_updated_again[0]["due_date"] == date(2027, 3, 1)


def test_docket_entry_reminders_exclude_closed_items() -> None:
    with _make_session() as session:
        created = create_project(session, _base_payload(docket_no="DCKT-DOCKET-10"))
        assert len(created["docket_entry_reminders"]) == 4

        from app.patents.schemas import PatentDocketEntryClose
        from app.patents.service import close_patent_docket_entry, get_project

        poa_entry_id = next(e["id"] for e in created["docket_entries"] if e["item_type"] == ITEM_POA)
        close_patent_docket_entry(
            session, created["id"], poa_entry_id, PatentDocketEntryClose(closure_date=date(2026, 10, 1))
        )
        reloaded = get_project(session, created["id"])
        assert len(reloaded["docket_entry_reminders"]) == 3
        assert len(reloaded["docket_entries"]) == 4
