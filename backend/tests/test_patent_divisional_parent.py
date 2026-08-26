from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.schemas import (
    PatentApplicantInput,
    PatentInventorInput,
    PatentPriorityInput,
    PatentProjectCreate,
    PatentProjectUpdate,
)
from app.patents.service import create_project, get_project, list_projects, update_project
from app.patents.workflow import compute_divisional_rfe_deadline, compute_rfe_deadline


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _final_docket_kwargs(**overrides) -> dict:
    kwargs = dict(
        project_mode="final",
        docket_no="DIV-DOCKET-1",
        applicant_name="",
        applicants=[PatentApplicantInput(name="Acme Corp", country="IN", address="Somewhere")],
        inventors=[PatentInventorInput(name="Jane Doe", nationality="IN", address="Elsewhere")],
    )
    kwargs.update(overrides)
    return kwargs


def test_create_divisional_final_docket_persists_parent_application_data() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            PatentProjectCreate(
                application_type="Ordinary Divisional",
                in_application_no="202412000001",
                in_application_date=date(2024, 1, 20),
                parent_project_id=7,
                parent_application_no="201911000001",
                parent_application_date=date(2019, 11, 1),
                **_final_docket_kwargs(),
            ),
        )

    assert created["parent_project_id"] == 7
    assert created["parent_application_no"] == "201911000001"
    assert str(created["parent_application_date"]) == "2019-11-01"
    # own IN application no/date remain the child's, untouched by parent data
    assert created["in_application_no"] == "202412000001"
    assert str(created["in_application_date"]) == "2024-01-20"


def test_create_divisional_final_docket_skips_year_mismatch_check() -> None:
    # IN number embeds filing year 2019, but in_application_date year is 2024 -
    # would raise for a non-divisional type, must pass for divisional.
    with _make_session() as session:
        created = create_project(
            session,
            PatentProjectCreate(
                application_type="Ordinary Divisional",
                in_application_no="201912000001",
                in_application_date=date(2024, 1, 20),
                parent_application_no="201911000001",
                parent_application_date=date(2019, 11, 1),
                **_final_docket_kwargs(),
            ),
        )

    assert created["in_application_no"] == "201912000001"


def test_create_non_divisional_final_docket_still_enforces_year_match() -> None:
    with _make_session() as session:
        with pytest.raises(ValueError, match="does not match"):
            create_project(
                session,
                PatentProjectCreate(
                    application_type="Non-Provisional Application",
                    in_application_no="201911000001",
                    in_application_date=date(2024, 1, 20),
                    **_final_docket_kwargs(docket_no="NONDIV-DOCKET-1"),
                ),
            )


def test_create_divisional_final_docket_requires_parent_application_data() -> None:
    with _make_session() as session:
        with pytest.raises(ValueError, match="Parent application"):
            create_project(
                session,
                PatentProjectCreate(
                    application_type="Convention divisional",
                    in_application_no="202412000001",
                    in_application_date=date(2024, 1, 20),
                    **_final_docket_kwargs(docket_no="DIV-DOCKET-2"),
                ),
            )


def test_update_divisional_project_persists_and_skips_year_match() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            PatentProjectCreate(
                application_type="Ordinary Divisional",
                in_application_no="202412000001",
                in_application_date=date(2024, 1, 20),
                parent_application_no="201911000001",
                parent_application_date=date(2019, 11, 1),
                **_final_docket_kwargs(docket_no="DIV-DOCKET-3"),
            ),
        )

        updated = update_project(
            session,
            created["id"],
            PatentProjectUpdate(
                docket_no="DIV-DOCKET-3",
                application_type="Ordinary Divisional",
                in_application_no="201812000009",  # mismatched year vs date, must not raise
                in_application_date=date(2024, 2, 1),
                applicant_name="Acme Corp",
                applicant_country="IN",
                applicant_address="Somewhere",
            ),
        )

    assert updated is not None
    assert updated["in_application_no"] == "201812000009"
    assert updated["parent_application_no"] == "201911000001"
    assert str(updated["parent_application_date"]) == "2019-11-01"


def test_parent_docket_no_and_client_docket_no_resolved_on_single_get() -> None:
    with _make_session() as session:
        parent = create_project(
            session,
            PatentProjectCreate(
                project_mode="draft",
                application_type="Convention",
                docket_no="PARENT-DOCKET-1",
                client_docket_no="PARENT-CLIENT-DKT-1",
                in_application_no="201911000001",
                in_application_date=date(2019, 11, 1),
                applicant_name="Acme Corp",
                applicant_country="IN",
                applicant_address="Somewhere",
            ),
        )

        child = create_project(
            session,
            PatentProjectCreate(
                application_type="Ordinary Divisional",
                in_application_no="202412000001",
                in_application_date=date(2024, 1, 20),
                parent_project_id=parent["id"],
                parent_application_no="201911000001",
                parent_application_date=date(2019, 11, 1),
                **_final_docket_kwargs(docket_no="CHILD-DOCKET-1"),
            ),
        )

        fetched = get_project(session, child["id"])
        assert fetched is not None
        assert fetched["parent_docket_no"] == "PARENT-DOCKET-1"
        assert fetched["parent_client_docket_no"] == "PARENT-CLIENT-DKT-1"

        listed = {row["id"]: row for row in list_projects(session)}
        assert listed[child["id"]]["parent_docket_no"] == "PARENT-DOCKET-1"
        assert listed[child["id"]]["parent_client_docket_no"] == "PARENT-CLIENT-DKT-1"


def test_divisional_docket_rfe_due_date_uses_parent_and_own_filing_formula() -> None:
    with _make_session() as session:
        parent = create_project(
            session,
            PatentProjectCreate(
                project_mode="draft",
                application_type="Convention",
                docket_no="PARENT-DOCKET-2",
                in_application_no="201911000001",
                in_application_date=date(2019, 11, 1),
                applicant_name="Acme Corp",
                applicant_country="IN",
                applicant_address="Somewhere",
                priorities=[
                    PatentPriorityInput(
                        priority_application_no="US999",
                        priority_application_date=date(2019, 1, 1),
                        country="US",
                        title="Widget",
                    )
                ],
            ),
        )

        child = create_project(
            session,
            PatentProjectCreate(
                application_type="Ordinary Divisional",
                in_application_no="202412000001",
                in_application_date=date(2024, 1, 20),
                parent_project_id=parent["id"],
                parent_application_no="201911000001",
                parent_application_date=date(2019, 11, 1),
                **_final_docket_kwargs(docket_no="CHILD-DOCKET-2"),
            ),
        )

        expected = compute_divisional_rfe_deadline(
            date(2024, 1, 20), date(2019, 11, 1), [date(2019, 1, 1)]
        )
        # sanity: must actually exercise the divisional formula, not silently
        # fall back to the plain one.
        assert expected != compute_rfe_deadline(date(2024, 1, 20))

        fetched = get_project(session, child["id"])
        assert fetched is not None
        assert fetched["due_action"] == "Request for Examination"
        assert fetched["action_due_date"] == expected
        assert fetched["parent_priority_dates"] == [date(2019, 1, 1)]

        listed = {row["id"]: row for row in list_projects(session)}
        assert listed[child["id"]]["action_due_date"] == expected
        assert listed[child["id"]]["parent_priority_dates"] == [date(2019, 1, 1)]
