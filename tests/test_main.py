"""Tests for the FastAPI application."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.task import TaskSource


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Return a TestClient with lifespan support."""
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    """GET /health should return ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_task(client: TestClient) -> None:
    """POST /tasks should submit a task and return the result."""
    response = client.post(
        "/tasks",
        json={
            "source": "api",
            "raw_text": "/audit ozon",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "audit"
    assert data["status"] == "draft"
    assert data["result"]["data"]["marketplace"] == "ozon"


def test_create_task_help(client: TestClient) -> None:
    """POST /tasks should resolve help intent via rules."""
    response = client.post(
        "/tasks",
        json={
            "source": "telegram",
            "raw_text": "/help",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "help"
    assert data["status"] == "draft"
    assert "/audit" in data["result"]["data"]["message"]
