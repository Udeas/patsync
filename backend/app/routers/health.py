from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from app.database import get_session

router = APIRouter()

@router.get("/health")
def health_check(db=Depends(get_session)):
    try:
        db.exec(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")