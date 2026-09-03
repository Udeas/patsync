"""Auto-docketed Form 27 (Statement of Working) reminders on patent grant.

Section 146(2) + Rule 131(2), Patents Rules 2003, as amended by the Patents
(Amendment) Rules 2024. Worked examples from the spec:

| Grant date  | FY of grant | Branch                | First due date |
|-------------|-------------|------------------------|-----------------|
| 10 Feb 2022 | FY2021-22   | Transitional (Y<=2022) | 30 Sep 2026     |
| 5 Nov 2023  | FY2023-24   | Plain formula          | 30 Sep 2027     |
| 20 Jun 2026 | FY2026-27   | Plain formula          | 30 Sep 2030     |
"""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.docket import (
    ITEM_FORM27_PREFIX,
    parse_form27_block_start,
    plan_form27_first_entry,
    plan_form27_next_entry,
)
from app.patents.patent_status_catalog import STATUS_ID_APPLICATION_FILED, STATUS_ID_GRANTED
from app.patents.schemas import (
    PatentApplicantInput,
    PatentDocketEntryClose,
    PatentInventorInput,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectUpdate,
    PatentTimelineStatusUpdate,
)
from app.patents.service import (
    close_patent_docket_entry,
    create_project,
    get_project,
    update_project,
    update_project_detail,
    update_status_event,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _create_final_docket(session: Session, docket_no: str) -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="final",
            application_type="Non-Provisional Application",
            docket_no=docket_no,
            in_application_no="202312000001",
            in_application_date=date(2023, 1, 1),
            applicant_name="",
            applicants=[PatentApplicantInput(name="Acme Corp", country="IN", address="Somewhere")],
            inventors=[PatentInventorInput(name="Jane Doe", nationality="IN", address="Elsewhere")],
            priorities=[],
        ),
    )


def _update_payload(docket_no: str, grant_number: str | None = None) -> PatentProjectUpdate:
    return PatentProjectUpdate(
        docket_no=docket_no,
        applicant_name="Acme Corp",
        applicant_country="IN",
        applicant_address="Somewhere",
        grant_number=grant_number,
    )


def _grant(session: Session, project_id: int, docket_no: str, grant_date: date, grant_number: str) -> dict:
    return update_project_detail(
        session,
        project_id,
        PatentProjectDetailUpdate(
            application=_update_payload(docket_no, grant_number=grant_number),
            timeline_updates=[
                PatentTimelineStatusUpdate(status_id=STATUS_ID_APPLICATION_FILED, status_date=date(2023, 1, 1)),
                PatentTimelineStatusUpdate(status_id=STATUS_ID_GRANTED, status_date=grant_date),
            ],
        ),
    )


def _form27_entries(project: dict) -> list[dict]:
    return [e for e in project["docket_entries"] if e["item_type"].startswith(ITEM_FORM27_PREFIX)]


# --- pure due-date algorithm (docket.py) ----------------------------------


def test_worked_example_transitional_grant_2022() -> None:
    plan = plan_form27_first_entry(grant_date=date(2022, 2, 10), grant_number="IN123")
    assert plan.due_date == date(2026, 9, 30)


def test_worked_example_plain_formula_grant_2023() -> None:
    plan = plan_form27_first_entry(grant_date=date(2023, 11, 5), grant_number="IN123")
    assert plan.due_date == date(2027, 9, 30)


def test_worked_example_plain_formula_grant_2026() -> None:
    plan = plan_form27_first_entry(grant_date=date(2026, 6, 20), grant_number="IN123")
    assert plan.due_date == date(2030, 9, 30)


def test_transitional_cutoff_boundary_fy_2022_23_vs_2023_24() -> None:
    # 31 Mar 2023 is still FY2022-23 (Y=2022) -> transitional.
    still_transitional = plan_form27_first_entry(grant_date=date(2023, 3, 31), grant_number="X")
    assert still_transitional.due_date == date(2026, 9, 30)

    # 1 Apr 2023 is FY2023-24 (Y=2023) -> plain formula, due 2027-09-30.
    plain_formula = plan_form27_first_entry(grant_date=date(2023, 4, 1), grant_number="X")
    assert plain_formula.due_date == date(2027, 9, 30)
    assert plain_formula.item_type != still_transitional.item_type


def test_fy_boundary_mar_31_vs_apr_1_within_plain_formula() -> None:
    # 31 Mar 2026 -> FY2025-26 (Y=2025) -> block FY2026-27..FY2028-29, due 2029-09-30.
    mar_31 = plan_form27_first_entry(grant_date=date(2026, 3, 31), grant_number="X")
    assert mar_31.due_date == date(2029, 9, 30)

    # 1 Apr 2026 -> FY2026-27 (Y=2026) -> block FY2027-28..FY2029-30, due 2030-09-30.
    apr_1 = plan_form27_first_entry(grant_date=date(2026, 4, 1), grant_number="X")
    assert apr_1.due_date == date(2030, 9, 30)


def test_roll_forward_second_cycle_due_date_is_first_plus_three_years() -> None:
    first = plan_form27_first_entry(grant_date=date(2022, 2, 10), grant_number="IN123")
    block_start = parse_form27_block_start(first.item_type)
    second = plan_form27_next_entry(
        grant_number="IN123", prior_block_start_year=block_start, prior_due_date=first.due_date
    )
    assert second.due_date == date(2029, 9, 30)


# --- service-layer wiring --------------------------------------------------


def test_grant_creates_first_form27_entry_with_correct_due_date() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-1")
        updated = _grant(session, created["id"], "F27-1", date(2023, 11, 5), "IN-555")

        entries = _form27_entries(updated)
        assert len(entries) == 1
        assert entries[0]["due_date"] == date(2027, 9, 30)
        assert "IN-555" in entries[0]["title"]
        assert entries[0]["closure_date"] is None


def test_grant_creates_form27_entry_via_single_status_endpoint() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-2")
        update_project(session, created["id"], _update_payload("F27-2", grant_number="IN-777"))
        updated = update_status_event(session, created["id"], STATUS_ID_GRANTED, date(2026, 6, 20))

        entries = _form27_entries(updated)
        assert len(entries) == 1
        assert entries[0]["due_date"] == date(2030, 9, 30)


def test_correcting_grant_date_within_same_block_updates_in_place() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-3")
        _grant(session, created["id"], "F27-3", date(2023, 11, 5), "IN-555")
        corrected = _grant(session, created["id"], "F27-3", date(2023, 12, 20), "IN-555")

        entries = _form27_entries(corrected)
        assert len(entries) == 1
        assert entries[0]["due_date"] == date(2027, 9, 30)


def test_correcting_grant_date_across_blocks_replaces_open_entry_not_duplicates() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-4")
        # First grant date lands in FY2023-24 block (due 2027-09-30)...
        _grant(session, created["id"], "F27-4", date(2023, 11, 5), "IN-555")
        # ...corrected to a date that shifts the reporting block entirely.
        corrected = _grant(session, created["id"], "F27-4", date(2026, 6, 20), "IN-555")

        entries = _form27_entries(corrected)
        assert len(entries) == 1
        assert entries[0]["due_date"] == date(2030, 9, 30)


def test_closing_form27_entry_generates_next_cycle_when_in_force() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-5")
        granted = _grant(session, created["id"], "F27-5", date(2023, 2, 15), "IN-555")
        first_entry = _form27_entries(granted)[0]

        result = close_patent_docket_entry(
            session, created["id"], first_entry["id"], PatentDocketEntryClose(closure_date=date(2026, 8, 1))
        )
        form27_rows = [e for e in result if e.item_type.startswith(ITEM_FORM27_PREFIX)]
        assert len(form27_rows) == 2
        closed = next(e for e in form27_rows if e.id == first_entry["id"])
        next_cycle = next(e for e in form27_rows if e.id != first_entry["id"])
        assert closed.closure_date == date(2026, 8, 1)
        assert next_cycle.closure_date is None
        assert next_cycle.due_date == date(2029, 9, 30)


def test_closing_form27_entry_does_not_roll_forward_when_project_archived() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-6")
        granted = _grant(session, created["id"], "F27-6", date(2023, 2, 15), "IN-555")
        first_entry = _form27_entries(granted)[0]

        from app.patents.service import archive_project

        archive_project(session, created["id"])

        result = close_patent_docket_entry(
            session, created["id"], first_entry["id"], PatentDocketEntryClose(closure_date=date(2026, 8, 1))
        )
        form27_rows = [e for e in result if e.item_type.startswith(ITEM_FORM27_PREFIX)]
        assert len(form27_rows) == 1
        assert form27_rows[0].closure_date == date(2026, 8, 1)


def test_closing_already_closed_form27_entry_raises() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-7")
        granted = _grant(session, created["id"], "F27-7", date(2023, 11, 5), "IN-555")
        entry = _form27_entries(granted)[0]

        close_patent_docket_entry(
            session, created["id"], entry["id"], PatentDocketEntryClose(closure_date=date(2027, 9, 1))
        )
        with pytest.raises(ValueError, match="already closed"):
            close_patent_docket_entry(
                session, created["id"], entry["id"], PatentDocketEntryClose(closure_date=date(2027, 9, 2))
            )


def test_form27_reminders_surface_in_project_detail() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "F27-8")
        _grant(session, created["id"], "F27-8", date(2023, 11, 5), "IN-555")
        detail = get_project(session, created["id"])
        form27_reminders = [
            r for r in detail["docket_entry_reminders"] if r["fire_on"] == date(2027, 9, 30)
        ]
        assert len(form27_reminders) == 1
