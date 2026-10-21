from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List
from ..database import get_session
from ..schemas.applications import (
    ApplicationCreate,
    CustomEventClose,
    CustomEventCreate,
    CustomEventRead,
    ProjectDetailRead,
    ProjectDetailUpdate,
    ProjectNoteInput,
    ProjectNoteRead,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationStatusUpdate,
    ApplicationTimelineRead,
)
from ..services.application_service import (
    add_custom_event,
    add_project_note,
    close_custom_event,
    create_application,
    delete_custom_event,
    get_applications,
    get_application_by_id,
    get_application_timeline,
    get_project_detail,
    update_application,
    update_application_status,
    update_project_detail,
    update_project_note,
    delete_application,
)


router = APIRouter()


@router.post("/", response_model=ApplicationRead)
def create_application_endpoint(application: ApplicationCreate, session: Session = Depends(get_session)):
    try:
        return create_application(session, application)
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get("/", response_model=List[ApplicationRead])
def get_applications_endpoint(session: Session = Depends(get_session)):
    return get_applications(session)


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application_endpoint(application_id: int, session: Session = Depends(get_session)):
    application = get_application_by_id(session, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.get("/{application_id}/timeline", response_model=ApplicationTimelineRead)
def get_application_timeline_endpoint(application_id: int, session: Session = Depends(get_session)):
    timeline = get_application_timeline(session, application_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="Application not found")
    return timeline


@router.get("/{application_id}/detail", response_model=ProjectDetailRead)
def get_project_detail_endpoint(application_id: int, session: Session = Depends(get_session)):
    detail = get_project_detail(session, application_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Application not found")
    return detail


@router.put("/{application_id}", response_model=ApplicationRead)
def update_application_endpoint(application_id: int, update_data: ApplicationUpdate, session: Session = Depends(get_session)):
    try:
        application = update_application(session, application_id, update_data)
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        return application
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.put("/{application_id}/detail", response_model=ProjectDetailRead)
def update_project_detail_endpoint(
    application_id: int, detail_update: ProjectDetailUpdate, session: Session = Depends(get_session)
):
    try:
        detail = update_project_detail(session, application_id, detail_update)
        if not detail:
            raise HTTPException(status_code=404, detail="Application not found")
        return detail
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.put("/{application_id}/status", response_model=ApplicationRead)
def update_application_status_endpoint(
    application_id: int, status_update: ApplicationStatusUpdate, session: Session = Depends(get_session)
):
    try:
        application = update_application_status(session, application_id, status_update)
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        return application
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{application_id}")
def delete_application_endpoint(application_id: int, session: Session = Depends(get_session)):
    deleted = delete_application(session, application_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"message": "Application deleted"}


@router.post("/{application_id}/notes", response_model=List[ProjectNoteRead])
def add_project_note_endpoint(
    application_id: int, payload: ProjectNoteInput, session: Session = Depends(get_session)
):
    try:
        notes = add_project_note(session, application_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if notes is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return notes


@router.put("/{application_id}/notes/{note_id}", response_model=List[ProjectNoteRead])
def update_project_note_endpoint(
    application_id: int,
    note_id: int,
    payload: ProjectNoteInput,
    session: Session = Depends(get_session),
):
    try:
        notes = update_project_note(session, application_id, note_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if notes is None:
        raise HTTPException(status_code=404, detail="Project note not found")
    return notes


@router.post("/{application_id}/custom-events", response_model=List[CustomEventRead])
def add_custom_event_endpoint(
    application_id: int, payload: CustomEventCreate, session: Session = Depends(get_session)
):
    events = add_custom_event(session, application_id, payload)
    if events is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return events


@router.put("/{application_id}/custom-events/{event_id}/close", response_model=List[CustomEventRead])
def close_custom_event_endpoint(
    application_id: int,
    event_id: int,
    payload: CustomEventClose,
    session: Session = Depends(get_session),
):
    try:
        events = close_custom_event(session, application_id, event_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if events is None:
        raise HTTPException(status_code=404, detail="Custom event not found")
    return events


@router.delete("/{application_id}/custom-events/{event_id}", response_model=List[CustomEventRead])
def delete_custom_event_endpoint(
    application_id: int, event_id: int, session: Session = Depends(get_session)
):
    try:
        events = delete_custom_event(session, application_id, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if events is None:
        raise HTTPException(status_code=404, detail="Custom event not found")
    return events
