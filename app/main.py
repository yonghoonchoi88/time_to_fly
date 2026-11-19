"""FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import inspections, review
from app.db import Base, engine, get_session
from app.domain import models  # noqa: F401  (registers tables on Base.metadata)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema bootstrap for v0.1. Replace with Alembic migrations once the schema stabilises.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Defect-to-Action", version="0.1.0", lifespan=lifespan)
app.include_router(inspections.router)
app.include_router(review.router)


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
