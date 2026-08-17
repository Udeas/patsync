from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from app import models  # noqa: F401
from app.us_pto.models import UsptoTracker  # noqa: F401
from app.database import engine, run_schema_migrations
from app.routers.health import router as health_router
from app.routers.applications import router as applications_router
from app.routers.status import router as status_router
from app.routers.trademark import router as trademark_router
from app.routers.tm_status import router as tm_status_router
from app.patents.router import router as patents_router
from app.us_pto.router import router as us_pto_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(applications_router, prefix="/api/applications")
app.include_router(status_router, prefix="/api/status")
app.include_router(trademark_router, prefix="/api/tm-applications")
app.include_router(tm_status_router, prefix="/api/tm-status")
app.include_router(patents_router, prefix="/api/patents")
app.include_router(us_pto_router, prefix="/api/us-pto", tags=["us-pto"])


@app.on_event("startup")
def on_startup():
    # Create model-defined tables first so raw migrations that ALTER or
    # reference them (e.g. patent_project) succeed on a fresh database.
    SQLModel.metadata.create_all(engine)
    run_schema_migrations()


@app.get("/")
def read_root():
    return {"status": "FlowTrack API is live"}

