from typing import List
from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..database import get_session
from ..schemas.applications import StatusRead
from ..services.application_service import list_statuses


router = APIRouter()


@router.get("/", response_model=List[StatusRead])
def get_statuses_endpoint(session: Session = Depends(get_session)):
    return list_statuses(session)
