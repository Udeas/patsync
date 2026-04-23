from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List
from ..database import get_session
from ..schemas.applications import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationStatusUpdate,
)
from ..services.application_service import (
    create_application,
    get_applications,
    get_application_by_id,
    update_application,
    update_application_status,
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
