import json
from datetime import date

from sqlmodel import Session, SQLModel, create_engine, select

from app.audit.listener import register_audit_listener
from app.auth.models import AuditLog
from app.patents.patent_status_catalog import STATUS_ID_ABANDONED
from app.patents.schemas import PatentApplicantInput, PatentInventorInput, PatentProjectCreate
from app.patents.service import create_project, update_status_event

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
