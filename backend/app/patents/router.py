from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session

from .schemas import (
    PatentAgentInput,
    PatentAgentRead,
    PatentClientInput,
    PatentClientRead,
    PatentDraftFinalizeRequest,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectRead,
    PatentProjectUpdate,
    PatentStatusUpdate,
)
from .service import (
    convert_draft_to_final,
    create_patent_agent,
    create_patent_client,
    create_project,
    get_project,
    list_patent_agents,
    list_patent_clients,
    list_projects,
    update_project,
    update_project_detail,
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
def list_projects_endpoint(session: Session = Depends(get_session)):
    return list_projects(session)


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
        project = update_status_event(session, project_id, payload.status_id, payload.status_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project:
        raise HTTPException(status_code=404, detail="Patent project not found")
    return project


@router.get("/clients", response_model=list[PatentClientRead])
def list_clients_endpoint(session: Session = Depends(get_session)):
    return list_patent_clients(session)


@router.post("/clients", response_model=PatentClientRead)
def create_client_endpoint(payload: PatentClientInput, session: Session = Depends(get_session)):
    try:
        return create_patent_client(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agents", response_model=list[PatentAgentRead])
def list_agents_endpoint(session: Session = Depends(get_session)):
    return list_patent_agents(session)


@router.post("/agents", response_model=PatentAgentRead)
def create_agent_endpoint(payload: PatentAgentInput, session: Session = Depends(get_session)):
    try:
        return create_patent_agent(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
