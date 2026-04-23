from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from app import models  # noqa: F401
from app.database import engine, run_schema_migrations
from app.routers.health import router as health_router
from app.routers.applications import router as applications_router
from app.routers.status import router as status_router

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

@app.on_event("startup")
def on_startup():
    run_schema_migrations()
    SQLModel.metadata.create_all(engine)

@app.get("/")
def read_root():
    return {"status": "FlowTrack API is live"}

