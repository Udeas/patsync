from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.schemas.trademark import (
    TmApplicationCreate,
    TmApplicationRead,
    TmApplicationStatusUpdate,
    TmApplicationTimelineRead,
    TmApplicationUpdate,
    TmProjectDetailRead,
    TmProjectDetailUpdate,
)
from app.services.trademark_service import (
    create_tm_application,
    delete_tm_application,
    get_tm_application_by_id,
    get_tm_application_timeline,
    get_tm_applications,
    get_tm_project_detail,
    update_tm_application,
    update_tm_application_status,
    update_tm_project_detail,
)

router = APIRouter()


@router.post("/", response_model=TmApplicationRead)
def create_tm_application_endpoint(
    application: TmApplicationCreate, session: Session = Depends(get_session)
):
    try:
        return create_tm_application(session, application)
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get("/", response_model=List[TmApplicationRead])
def get_tm_applications_endpoint(session: Session = Depends(get_session)):
    return get_tm_applications(session)


@router.get("/{application_id}", response_model=TmApplicationRead)
def get_tm_application_endpoint(application_id: int, session: Session = Depends(get_session)):
    application = get_tm_application_by_id(session, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Trademark application not found")
    return application


@router.get("/{application_id}/timeline", response_model=TmApplicationTimelineRead)
def get_tm_application_timeline_endpoint(
    application_id: int, session: Session = Depends(get_session)
):
    timeline = get_tm_application_timeline(session, application_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="Trademark application not found")
    return timeline


@router.get("/{application_id}/detail", response_model=TmProjectDetailRead)
def get_tm_project_detail_endpoint(application_id: int, session: Session = Depends(get_session)):
    detail = get_tm_project_detail(session, application_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Trademark application not found")
    return detail


@router.put("/{application_id}", response_model=TmApplicationRead)
def update_tm_application_endpoint(
    application_id: int, update_data: TmApplicationUpdate, session: Session = Depends(get_session)
):
    try:
        application = update_tm_application(session, application_id, update_data)
        if not application:
            raise HTTPException(status_code=404, detail="Trademark application not found")
        return application
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.put("/{application_id}/detail", response_model=TmProjectDetailRead)
def update_tm_project_detail_endpoint(
    application_id: int,
    detail_update: TmProjectDetailUpdate,
    session: Session = Depends(get_session),
):
    try:
        detail = update_tm_project_detail(session, application_id, detail_update)
        if not detail:
            raise HTTPException(status_code=404, detail="Trademark application not found")
        return detail
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.put("/{application_id}/status", response_model=TmApplicationRead)
def update_tm_application_status_endpoint(
    application_id: int,
    status_update: TmApplicationStatusUpdate,
    session: Session = Depends(get_session),
):
    try:
        application = update_tm_application_status(session, application_id, status_update)
        if not application:
            raise HTTPException(status_code=404, detail="Trademark application not found")
        return application
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{application_id}")
def delete_tm_application_endpoint(application_id: int, session: Session = Depends(get_session)):
    deleted = delete_tm_application(session, application_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trademark application not found")
    return {"message": "Trademark application deleted"}
