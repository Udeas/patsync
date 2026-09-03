from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.database import get_session

from .schemas import (
    PatentAgentInput,
    PatentAgentRead,
    PatentAgentUpdate,
    PatentAnnuityPaymentInput,
    PatentAnnuitySummary,
    PatentAnnuityTransferInput,
    PatentClientInput,
    PatentClientRead,
    PatentClientUpdate,
    PatentCustomEventClose,
    PatentCustomEventCreate,
    PatentCustomEventRead,
    PatentDraftFinalizeRequest,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectNoteInput,
    PatentProjectNoteRead,
    PatentProjectRead,
    PatentProjectUpdate,
    PatentStatusUpdate,
)
from .service import (
    add_patent_custom_event,
    add_project_note,
    close_patent_custom_event,
    delete_patent_custom_event,
    update_project_note,
    archive_project,
    convert_draft_to_final,
    create_patent_agent,
    create_patent_client,
    create_project,
    delete_patent_agent,
    delete_patent_client,
    get_annuity_summary,
    transfer_annuity_case,
    get_project,
    list_patent_agents,
    list_patent_clients,
    list_projects,
    record_annuity_payment,
    update_project,
    update_project_detail,
    update_patent_agent,
    update_patent_client,
    update_status_event,
)

router = APIRouter()


@router.post("/projects", response_model=PatentProjectRead)
def create_project_endpoint(payload: PatentProjectCreate, session: Session = Depends(get_session)):
    try:
        return create_project(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects", response_model=list[PatentProjectRead])
def list_projects_endpoint(
    include_archived: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    return list_projects(session, include_archived=include_archived)


@router.get("/projects/{project_id}", response_model=PatentProjectRead)
def get_project_endpoint(project_id: int, session: Session = Depends(get_session)):
    project = get_project(session, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.post("/projects/{project_id}/convert-final", response_model=PatentProjectRead)
def convert_final_endpoint(
    project_id: int,
    payload: PatentDraftFinalizeRequest,
    session: Session = Depends(get_session),
):
    try:
        project = convert_draft_to_final(session, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.put("/projects/{project_id}", response_model=PatentProjectRead)
def update_project_endpoint(
    project_id: int,
    payload: PatentProjectUpdate,
    session: Session = Depends(get_session),
):
    try:
        project = update_project(session, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.put("/projects/{project_id}/detail", response_model=PatentProjectRead)
def update_project_detail_endpoint(
    project_id: int,
    payload: PatentProjectDetailUpdate,
    session: Session = Depends(get_session),
):
    try:
        project = update_project_detail(session, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.put("/projects/{project_id}/status", response_model=PatentProjectRead)
def update_status_endpoint(
    project_id: int,
    payload: PatentStatusUpdate,
    session: Session = Depends(get_session),
):
    try:
        project = update_status_event(session, project_id, payload.status_id, payload.status_date, payload.abandon_reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.delete("/projects/{project_id}", response_model=PatentProjectRead)
def archive_project_endpoint(project_id: int, session: Session = Depends(get_session)):
    project = archive_project(session, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.get("/projects/{project_id}/annuity", response_model=PatentAnnuitySummary)
def get_annuity_summary_endpoint(project_id: int, session: Session = Depends(get_session)):
    summary = get_annuity_summary(session, project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return summary


@router.post("/projects/{project_id}/annuity/payments", response_model=PatentAnnuitySummary)
def record_annuity_payment_endpoint(
    project_id: int,
    payload: PatentAnnuityPaymentInput,
    session: Session = Depends(get_session),
):
    try:
        summary = record_annuity_payment(session, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if summary is None:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return summary


@router.post("/projects/{project_id}/annuity/transfer", response_model=PatentAnnuitySummary)
def transfer_annuity_case_endpoint(
    project_id: int,
    payload: PatentAnnuityTransferInput,
    session: Session = Depends(get_session),
):
    try:
        summary = transfer_annuity_case(session, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if summary is None:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return summary


@router.post("/projects/{project_id}/notes", response_model=list[PatentProjectNoteRead])
def add_project_note_endpoint(
    project_id: int,
    payload: PatentProjectNoteInput,
    session: Session = Depends(get_session),
):
    try:
        notes = add_project_note(session, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if notes is None:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return notes


@router.put("/projects/{project_id}/notes/{note_id}", response_model=list[PatentProjectNoteRead])
def update_project_note_endpoint(
    project_id: int,
    note_id: int,
    payload: PatentProjectNoteInput,
    session: Session = Depends(get_session),
):
    try:
        notes = update_project_note(session, project_id, note_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if notes is None:
        raise HTTPException(status_code=404, detail="Patent project note not found")
    return notes


@router.post("/projects/{project_id}/custom-events", response_model=list[PatentCustomEventRead])
def add_patent_custom_event_endpoint(
    project_id: int,
    payload: PatentCustomEventCreate,
    session: Session = Depends(get_session),
):
    events = add_patent_custom_event(session, project_id, payload)
    if events is None:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return events


@router.put(
    "/projects/{project_id}/custom-events/{event_id}/close",
    response_model=list[PatentCustomEventRead],
)
def close_patent_custom_event_endpoint(
    project_id: int,
    event_id: int,
    payload: PatentCustomEventClose,
    session: Session = Depends(get_session),
):
    try:
        events = close_patent_custom_event(session, project_id, event_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if events is None:
        raise HTTPException(status_code=404, detail="Patent custom event not found")
    return events


@router.delete(
    "/projects/{project_id}/custom-events/{event_id}",
    response_model=list[PatentCustomEventRead],
)
def delete_patent_custom_event_endpoint(
    project_id: int, event_id: int, session: Session = Depends(get_session)
):
    try:
        events = delete_patent_custom_event(session, project_id, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if events is None:
        raise HTTPException(status_code=404, detail="Patent custom event not found")
    return events


@router.get("/clients", response_model=list[PatentClientRead])
def list_clients_endpoint(session: Session = Depends(get_session)):
    return list_patent_clients(session)


@router.post("/clients", response_model=PatentClientRead)
def create_client_endpoint(payload: PatentClientInput, session: Session = Depends(get_session)):
    try:
        return create_patent_client(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/clients/{client_id}", response_model=PatentClientRead)
def update_client_endpoint(
    client_id: int,
    payload: PatentClientUpdate,
    session: Session = Depends(get_session),
):
    try:
        updated = update_patent_client(session, client_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Patent client not found")
    return updated


@router.delete("/clients/{client_id}")
def delete_client_endpoint(client_id: int, session: Session = Depends(get_session)):
    try:
        deleted = delete_patent_client(session, client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Patent client not found")
    return {"ok": True}


@router.get("/agents", response_model=list[PatentAgentRead])
def list_agents_endpoint(session: Session = Depends(get_session)):
    return list_patent_agents(session)


@router.post("/agents", response_model=PatentAgentRead)
def create_agent_endpoint(payload: PatentAgentInput, session: Session = Depends(get_session)):
    try:
        return create_patent_agent(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/agents/{agent_id}", response_model=PatentAgentRead)
def update_agent_endpoint(
    agent_id: int,
    payload: PatentAgentUpdate,
    session: Session = Depends(get_session),
):
    try:
        updated = update_patent_agent(session, agent_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Patent agent not found")
    return updated


@router.delete("/agents/{agent_id}")
def delete_agent_endpoint(agent_id: int, session: Session = Depends(get_session)):
    try:
        deleted = delete_patent_agent(session, agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Patent agent not found")
    return {"ok": True}
