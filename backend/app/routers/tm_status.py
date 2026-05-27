from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.schemas.trademark import TmStatusRead
from app.services.trademark_service import list_tm_statuses

router = APIRouter()


@router.get("/", response_model=List[TmStatusRead])
def get_tm_statuses_endpoint(session: Session = Depends(get_session)):
    return list_tm_statuses(session)
