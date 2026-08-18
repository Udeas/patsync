from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from app import models  # noqa: F401
from app.us_pto.models import UsptoTracker  # noqa: F401
from app.auth.models import User  # noqa: F401
from app.database import engine, run_schema_migrations
from app.routers.health import router as health_router
from app.routers.applications import router as applications_router
from app.routers.status import router as status_router
from app.routers.trademark import router as trademark_router
from app.routers.tm_status import router as tm_status_router
from app.patents.router import router as patents_router
from app.us_pto.router import router as us_pto_router
from app.auth.router import router as auth_router
from app.auth.deps import get_current_user

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

_auth = [Depends(get_current_user)]
app.include_router(applications_router, prefix="/api/applications", dependencies=_auth)
app.include_router(status_router, prefix="/api/status", dependencies=_auth)
app.include_router(trademark_router, prefix="/api/tm-applications", dependencies=_auth)
app.include_router(tm_status_router, prefix="/api/tm-status", dependencies=_auth)
app.include_router(patents_router, prefix="/api/patents", dependencies=_auth)
app.include_router(us_pto_router, prefix="/api/us-pto", tags=["us-pto"], dependencies=_auth)


@app.on_event("startup")
def on_startup():
    # Create model-defined tables first so raw migrations that ALTER or
    # reference them (e.g. patent_project) succeed on a fresh database.
    SQLModel.metadata.create_all(engine)
    run_schema_migrations()
    _seed_admin_on_startup()


def _seed_admin_on_startup() -> None:
    from sqlmodel import Session

    from app.auth.service import seed_admin
    from app.core.config import settings

    username = settings.AUTH_ADMIN_USERNAME
    password = settings.AUTH_ADMIN_PASSWORD
    if not username or not password:
        if settings.DEBUG:
            return
        raise RuntimeError("AUTH_ADMIN_USERNAME and AUTH_ADMIN_PASSWORD must be set")
    if not settings.DEBUG and settings.SECRET_KEY == "dev-insecure-change-me":
        raise RuntimeError("SECRET_KEY must be set to a non-default value in production")
    with Session(engine) as session:
        seed_admin(session, username, password)


@app.get("/")
def read_root():
    return {"status": "FlowTrack API is live"}

