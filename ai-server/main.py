"""Inference server entry point: ``uvicorn main:app --port 8001``.

Answers only "which defect candidates are in this image?". Verdicts, persistence and lots
are handled by the Django service and its Celery workers (ADR 0001).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.predict import router
from config import Settings
from models import load_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Settings are read and the engine is loaded once, at startup. A missing weights
        # file stops the server here instead of surfacing as a 500 on the first request.
        resolved = settings or Settings.from_env()
        app.state.settings = resolved
        app.state.engine = load_engine(resolved)
        yield
        app.state.engine = None

    app = FastAPI(title="time_to_fly ai-server", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
