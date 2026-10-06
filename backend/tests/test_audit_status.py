import json
from datetime import date

from sqlmodel import Session, SQLModel, create_engine, select

from app.audit.listener import register_audit_listener
from app.auth.models import AuditLog
from app.patents.patent_status_catalog import STATUS_ID_ABANDONED, STATUS_ID_APPLICATION_FILED, status_label
from app.patents.schemas import (
    PatentApplicantInput,
    PatentInventorInput,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectUpdate,
    PatentTimelineStatusUpdate,
)
from app.patents.service import create_project, update_project_detail, update_status_event

register_audit_listener()


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _final_patent(session) -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="final", application_type="Ordinary Application", docket_no="AUD-1",
            in_application_no="202411012345", in_application_date=date(2024, 11, 1),
            applicant_name="Acme", applicant_country="IN", applicant_address="Addr",
            applicants=[PatentApplicantInput(name="Acme", country="IN", address="Addr")],
            inventors=[PatentInventorInput(name="Inv A", nationality="IN", address="Inv Addr")],
            priorities=[], international_applications=[],
        ),
    )


def test_patent_abandon_writes_single_status_change_row() -> None:
    with _session() as session:
        project = _final_patent(session)
        update_status_event(session, project["id"], STATUS_ID_ABANDONED, date(2025, 1, 1),
                            abandon_reason="Fees not paid")
        rows = session.exec(select(AuditLog).where(AuditLog.action == "status_change")).all()
        assert len(rows) == 1
        changes = json.loads(rows[0].changes)
        fields = {c["field"]: c for c in changes}
        assert "status" in fields
        assert fields["status"]["new"] == "Abandoned"
        assert fields["abandon_reason"]["new"] == "Fees not paid"
        # no duplicate generic 'update' row for the same patent
        assert session.exec(select(AuditLog).where(AuditLog.action == "update")).all() == []


def _detail_payload(project: dict, status_date: date) -> PatentProjectDetailUpdate:
    return PatentProjectDetailUpdate(
        application=PatentProjectUpdate(
            docket_no=project["docket_no"],
            applicant_name=project["applicant_name"],
            applicant_country=project["applicant_country"],
            applicant_address=project["applicant_address"],
        ),
        timeline_updates=[
            PatentTimelineStatusUpdate(status_id=STATUS_ID_APPLICATION_FILED, status_date=status_date),
        ],
    )


def test_timeline_detail_update_writes_one_row_per_save_not_three() -> None:
    # Regression test for a bug where saving a timeline date through
    # update_project_detail (the "Application Timeline" editor's endpoint)
    # produced three audit rows for one save: two empty "touched" rows (the
    # project's modified_date got flushed twice - once via an autoflush
    # triggered by a SELECT partway through the function, once at the final
    # commit) plus the one real field-diff row.
    def update_rows():
        return session.exec(
            select(AuditLog).where(AuditLog.entity_id == project["id"], AuditLog.action == "update")
        ).all()

    with _session() as session:
        project = _final_patent(session)

        update_project_detail(session, project["id"], _detail_payload(project, date(2026, 10, 7)))
        rows = update_rows()
        assert len(rows) == 1
        changes = json.loads(rows[0].changes)
        assert changes == [
            {"field": status_label(STATUS_ID_APPLICATION_FILED), "old": "2024-11-01", "new": "2026-10-07"}
        ]

        update_project_detail(session, project["id"], _detail_payload(project, date(2026, 10, 8)))
        rows = update_rows()
        assert len(rows) == 2
        changes = json.loads(rows[-1].changes)
        assert changes == [
            {"field": status_label(STATUS_ID_APPLICATION_FILED), "old": "2026-10-07", "new": "2026-10-08"}
        ]

        # Saving with no actual change produces no audit row at all.
        update_project_detail(session, project["id"], _detail_payload(project, date(2026, 10, 8)))
        assert len(update_rows()) == 2
