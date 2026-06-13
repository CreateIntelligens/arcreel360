"""Tests for task cancellation API endpoints."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from server.auth import CurrentUserInfo, get_current_user
from server.routers import tasks as tasks_router


def _build_app(queue, monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(tasks_router.router, prefix="/api/v1")
    monkeypatch.setattr(tasks_router, "get_task_queue", lambda: queue)
    return app


class TestCancelPreview:
    async def test_cancel_preview_queued_task(self, generation_queue, monkeypatch):
        queue = generation_queue
        result = await queue.enqueue_task(
            project_name="demo",
            task_type="storyboard",
            media_type="image",
            resource_id="E1S01",
            payload={},
            script_file="ep1.json",
        )

        app = _build_app(queue, monkeypatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/tasks/{result['task_id']}/cancel-preview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task"]["task_id"] == result["task_id"]
        assert data["cascaded"] == []

    async def test_cancel_preview_running_task_400(self, generation_queue, monkeypatch):
        queue = generation_queue
        result = await queue.enqueue_task(
            project_name="demo",
            task_type="storyboard",
            media_type="image",
            resource_id="E1S01",
            payload={},
            script_file="ep1.json",
        )
        await queue.claim_next_task("image")

        app = _build_app(queue, monkeypatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/tasks/{result['task_id']}/cancel-preview")

        assert resp.status_code == 400
        assert "只有排隊中的任務可以取消" in resp.json()["detail"]


class TestCancelTask:
    async def test_cancel_queued_task(self, generation_queue, monkeypatch):
        queue = generation_queue
        result = await queue.enqueue_task(
            project_name="demo",
            task_type="storyboard",
            media_type="image",
            resource_id="E1S01",
            payload={},
            script_file="ep1.json",
        )

        app = _build_app(queue, monkeypatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/v1/tasks/{result['task_id']}/cancel")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["cancelled"]) == 1
        assert data["cancelled"][0]["status"] == "cancelled"

    async def test_cancel_nonexistent_task_400(self, generation_queue, monkeypatch):
        app = _build_app(generation_queue, monkeypatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/tasks/nonexistent/cancel")

        assert resp.status_code == 400


class TestCancelAllQueued:
    async def test_cancel_all_preview(self, generation_queue, monkeypatch):
        queue = generation_queue
        await queue.enqueue_task(
            project_name="demo",
            task_type="storyboard",
            media_type="image",
            resource_id="E1S01",
            payload={},
            script_file="ep1.json",
        )
        await queue.enqueue_task(
            project_name="demo",
            task_type="video",
            media_type="video",
            resource_id="E1S02",
            payload={},
            script_file="ep1.json",
        )

        app = _build_app(queue, monkeypatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/projects/demo/tasks/cancel-all-preview")

        assert resp.status_code == 200
        assert resp.json()["queued_count"] == 2

    async def test_cancel_all(self, generation_queue, monkeypatch):
        queue = generation_queue
        await queue.enqueue_task(
            project_name="demo",
            task_type="storyboard",
            media_type="image",
            resource_id="E1S01",
            payload={},
            script_file="ep1.json",
        )

        app = _build_app(queue, monkeypatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/projects/demo/tasks/cancel-all")

        assert resp.status_code == 200
        assert resp.json()["cancelled_count"] == 1
