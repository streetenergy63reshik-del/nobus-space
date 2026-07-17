"""FastAPI entry point for the Nobus Orchestrator."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.models.task import Task, UserRequest
from src.orchestrator.orchestrator import NobusOrchestrator


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Initialize the orchestrator on startup."""
    app.state.orchestrator = NobusOrchestrator()
    yield


app = FastAPI(
    title="Nobus Orchestrator",
    description="Space Nobus AI orchestrator API.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/tasks", response_model=Task)
async def create_task(request: UserRequest) -> Task:
    """Submit a new task to the orchestrator."""
    orchestrator: NobusOrchestrator = app.state.orchestrator
    return await orchestrator.submit(request)
