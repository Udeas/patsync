from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.patents.schemas import (
    PatentApplicantInput,
    PatentInternationalInput,
    PatentInventorInput,
    PatentPriorityInput,
    PatentProjectCreate,
    PatentProjectUpdate,
)
from app.patents.service import archive_project, create_project, get_project, list_projects, update_project


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_create_project_persists_multiple_applicants_and_inventors() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            PatentProjectCreate(
                project_mode="draft",
                application_type="Provisional Application",
                docket_no="DCKT-1001",
                applicant_name="Legacy Applicant",
                applicant_country="IN",
                applicant_address="Legacy Address",
                applicants=[
                    PatentApplicantInput(name="Applicant One", country="IN", address="Addr 1"),
                    PatentApplicantInput(name="Applicant Two", country="US", address="Addr 2"),
                ],
                inventors=[
                    PatentInventorInput(name="Inventor One", nationality="IN", address="Inv Addr 1"),
                    PatentInventorInput(name="Inventor Two", nationality="US", address="Inv Addr 2"),
                ],
                priorities=[],
                international_applications=[],
            ),
        )

        assert created["applicant_name"] == "Applicant One"
        assert len(created["applicants"]) == 2
        assert created["applicants"][1]["name"] == "Applicant Two"
        assert len(created["inventors"]) == 2


def test_update_project_supports_append_edit_delete_and_replace_for_collections() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            PatentProjectCreate(
                project_mode="final",
                application_type="Convention",
                docket_no="DCKT-2001",
                in_application_no="202311012345",
                in_application_date=date(2023, 11, 1),
                applicant_name="Applicant A",
                applicant_country="IN",
                applicant_address="Addr A",
                applicants=[PatentApplicantInput(name="Applicant A", country="IN", address="Addr A")],
                inventors=[PatentInventorInput(name="Inv A", nationality="IN", address="Inv Addr A")],
                priorities=[
                    PatentPriorityInput(
                        priority_application_no="US123456",
                        priority_application_date=date(2023, 6, 1),
                        country="US",
                        title="Priority One",
                    )
                ],
                international_applications=[],
            ),
        )

        project_id = created["id"]

        appended = update_project(
            session,
            project_id,
            PatentProjectUpdate(
                docket_no="DCKT-2001",
                project_mode="final",
                application_type="Convention",
                in_application_no="202311012345",
                in_application_date=date(2023, 11, 1),
                applicant_name="Applicant A Edited",
                applicant_country="US",
                applicant_address="Addr A Edited",
                applicants=[
                    PatentApplicantInput(name="Applicant A Edited", country="US", address="Addr A Edited"),
                    PatentApplicantInput(name="Applicant B", country="GB", address="Addr B"),
                ],
                inventors=[
                    PatentInventorInput(name="Inv A Edited", nationality="US", address="Inv Addr A Edited"),
                    PatentInventorInput(name="Inv B", nationality="GB", address="Inv Addr B"),
                ],
                priorities=[
                    PatentPriorityInput(
                        priority_application_no="US123456",
                        priority_application_date=date(2023, 6, 1),
                        country="US",
                        title="Priority One Edited",
                    ),
                    PatentPriorityInput(
                        priority_application_no="EP654321",
                        priority_application_date=date(2023, 7, 15),
                        country="EP",
                        title="Priority Two",
                    ),
                ],
                international_applications=[
                    PatentInternationalInput(
                        international_application_no="PCT/US2023/123456",
                        international_application_date=date(2023, 8, 20),
                    )
                ],
            ),
        )

        assert len(appended["applicants"]) == 2
        assert appended["applicant_name"] == "Applicant A Edited"
        assert len(appended["inventors"]) == 2
        assert len(appended["priorities"]) == 2
        assert len(appended["international_applications"]) == 1

        cleared = update_project(
            session,
            project_id,
            PatentProjectUpdate(
                docket_no="DCKT-2001",
                project_mode="final",
                application_type="Non-Provisional Application",
                in_application_no="202311012345",
                in_application_date=date(2023, 11, 1),
                applicant_name="",
                applicant_country=None,
                applicant_address=None,
                applicants=[],
                inventors=[],
                priorities=[],
                international_applications=[],
            ),
        )

        assert cleared["applicants"] == []
        assert cleared["inventors"] == []
        assert cleared["priorities"] == []
        assert cleared["international_applications"] == []

        fetched = get_project(session, project_id)
        assert fetched is not None
        assert fetched["applicants"] == []


def test_archive_project_hidden_by_default_and_visible_with_include_archived() -> None:
    with _make_session() as session:
        created = create_project(
            session,
            PatentProjectCreate(
                project_mode="draft",
                application_type="Provisional Application",
                docket_no="DCKT-ARCH-001",
                applicant_name="Applicant",
                applicant_country="IN",
                applicant_address="Address",
                applicants=[],
                inventors=[],
                priorities=[],
                international_applications=[],
            ),
        )
        archived = archive_project(session, created["id"])
        assert archived is not None
        assert archived["is_archived"] is True

        visible_default = list_projects(session)
        assert all(row["id"] != created["id"] for row in visible_default)

        visible_with_archived = list_projects(session, include_archived=True)
        assert any(row["id"] == created["id"] for row in visible_with_archived)
