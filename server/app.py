"""
影片專案管理 WebUI - FastAPI 主應用

啟動方式:
    cd ArcReel
    uv run uvicorn server.app:app --reload --port 1241
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from lib import PROJECT_ROOT
from lib.db import async_session_factory, close_db, init_db
from lib.generation_worker import GenerationWorker
from lib.logging_config import setup_logging
from server.auth import ensure_auth_password
from server.routers import (
    agent_chat,
    api_keys,
    assistant,
    characters,
    clues,
    cost_estimation,
    custom_providers,
    files,
    generate,
    project_events,
    projects,
    providers,
    scenes,
    system_config,
    tasks,
    usage,
    versions,
)
from server.routers import auth as auth_router
from server.services.project_events import ProjectEventService

# 初始化日誌
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # Startup
    ensure_auth_password()

    # Run Alembic migrations (auto-creates tables on first start)
    await init_db()

    # Migrate legacy .system_config.json → DB (no-op if file doesn't exist or already migrated)
    try:
        from lib.config.migration import migrate_json_to_db

        json_path = PROJECT_ROOT / "projects" / ".system_config.json"
        async with async_session_factory() as session:
            await migrate_json_to_db(session, json_path)
    except Exception as exc:
        logger.warning("JSON→DB config migration failed (non-fatal): %s", exc)

    # Sync Anthropic DB settings to env vars (Claude Agent SDK reads from os.environ)
    try:
        from lib.config.service import ConfigService, sync_anthropic_env

        async with async_session_factory() as session:
            svc = ConfigService(session)
            all_settings = await svc.get_all_settings()
            sync_anthropic_env(all_settings)
    except Exception as exc:
        logger.warning("DB→env Anthropic config sync failed (non-fatal): %s", exc)

    # 修復存量專案的 agent_runtime 軟連線
    from lib.project_manager import ProjectManager

    _pm = ProjectManager(PROJECT_ROOT / "projects")
    _symlink_stats = _pm.repair_all_symlinks()
    if any(v > 0 for v in _symlink_stats.values()):
        logger.info("agent_runtime 軟連線修復完成: %s", _symlink_stats)

    # Initialize async services
    await assistant.assistant_service.startup()
    assistant.assistant_service.session_manager.start_patrol()

    logger.info("啟動 GenerationWorker...")
    worker = create_generation_worker()
    app.state.generation_worker = worker
    await worker.start()
    logger.info("GenerationWorker 已啟動")

    logger.info("啟動 ProjectEventService...")
    project_event_service = ProjectEventService(PROJECT_ROOT)
    app.state.project_event_service = project_event_service
    await project_event_service.start()
    logger.info("ProjectEventService 已啟動")

    yield

    # Shutdown
    project_event_service = getattr(app.state, "project_event_service", None)
    if project_event_service:
        logger.info("正在停止 ProjectEventService...")
        await project_event_service.shutdown()
        logger.info("ProjectEventService 已停止")
    worker = getattr(app.state, "generation_worker", None)
    if worker:
        logger.info("正在停止 GenerationWorker...")
        await worker.stop()
        logger.info("GenerationWorker 已停止")
    await close_db()


# 建立 FastAPI 應用
app = FastAPI(
    title="影片專案管理 WebUI",
    description="AI 影片生成工作空間的 Web 管理介面",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 高频轮询/SSE 路径：仅 4xx/5xx 才记录，2xx 静默
_NOISY_PATHS: tuple[str, ...] = (
    "/api/v1/tasks",
    "/api/v1/tasks/stats",
)
_NOISY_PREFIXES: tuple[str, ...] = (
    "/api/v1/tasks/stream",
    "/api/v1/projects/",  # 包含 events/stream、assistant/stream 等 SSE
)

_MAX_LOG_USER_AGENT_LENGTH = 200


def _is_noisy_path(path: str) -> bool:
    if path in _NOISY_PATHS:
        return True
    if any(path.startswith(p) for p in _NOISY_PREFIXES) and ("/stream" in path or path.endswith("/events")):
        return True
    return False


def _sanitize_log_value(value: str) -> str:
    cleaned = " ".join(value.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())
    return cleaned or "-"


def _quote_log_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _request_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    forwarded_ip = forwarded_for.split(",", 1)[0].strip()
    if forwarded_ip:
        return _sanitize_log_value(forwarded_ip)

    if request.client is not None and request.client.host:
        return _sanitize_log_value(request.client.host)
    return "-"


def _request_log_source(request: Request) -> str:
    user_agent = _sanitize_log_value(request.headers.get("user-agent", "-"))
    if len(user_agent) > _MAX_LOG_USER_AGENT_LENGTH:
        user_agent = f"{user_agent[: _MAX_LOG_USER_AGENT_LENGTH - 3]}..."
    return f'client={_request_client_ip(request)} ua="{_quote_log_value(user_agent)}"'


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    source = _request_log_source(request)
    _always_skip = path.startswith("/assets") or path == "/health"
    _noisy = _is_noisy_path(path)
    try:
        response: Response = await call_next(request)
    except Exception:
        if not _always_skip:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "%s %s 500 %.0fms %s (unhandled)",
                request.method,
                path,
                elapsed_ms,
                source,
            )
        raise
    if _always_skip:
        return response
    # 噪音路径：只在非 2xx 时记录
    if _noisy and 200 <= response.status_code < 300:
        return response
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s %d %.0fms %s",
        request.method,
        path,
        response.status_code,
        elapsed_ms,
        source,
    )
    return response


# 註冊 API 路由
app.include_router(auth_router.router, prefix="/api/v1", tags=["認證"])
app.include_router(projects.router, prefix="/api/v1", tags=["專案管理"])
app.include_router(characters.router, prefix="/api/v1", tags=["角色管理"])
app.include_router(clues.router, prefix="/api/v1", tags=["線索管理"])
app.include_router(scenes.router, prefix="/api/v1", tags=["場景管理"])
app.include_router(files.router, prefix="/api/v1", tags=["檔案管理"])
app.include_router(generate.router, prefix="/api/v1", tags=["生成"])
app.include_router(versions.router, prefix="/api/v1", tags=["版本管理"])
app.include_router(usage.router, prefix="/api/v1", tags=["費用統計"])
app.include_router(assistant.router, prefix="/api/v1/projects/{project_name}/assistant", tags=["助理會話"])
app.include_router(tasks.router, prefix="/api/v1", tags=["任務佇列"])
app.include_router(project_events.router, prefix="/api/v1", tags=["專案變更流"])
app.include_router(providers.router, prefix="/api/v1", tags=["供應商管理"])
app.include_router(system_config.router, prefix="/api/v1", tags=["系統配置"])
app.include_router(api_keys.router, prefix="/api/v1", tags=["API Key 管理"])
app.include_router(agent_chat.router, prefix="/api/v1", tags=["Agent 對話"])
app.include_router(custom_providers.router, prefix="/api/v1", tags=["自定義供應商"])
app.include_router(cost_estimation.router, prefix="/api/v1", tags=["費用估算"])


def create_generation_worker() -> GenerationWorker:
    return GenerationWorker()


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "message": "影片專案管理 WebUI 運作正常"}


@app.get("/skill.md", include_in_schema=False)
async def serve_skill_md(request: Request) -> Response:
    """動態渲染 skill.md 模板，將 {{BASE_URL}} 替換為實際服務地址（無需認證）。"""
    from starlette.responses import PlainTextResponse

    template_path = PROJECT_ROOT / "public" / "skill.md.template"
    if not template_path.exists():
        return PlainTextResponse("skill.md 樣板不存在", status_code=404)

    template = template_path.read_text(encoding="utf-8")

    # 從請求推斷 base URL；僅信任 x-forwarded-proto（反向代理標準頭），
    # host 使用連線實際目標地址，不接受可被使用者偽造的 x-forwarded-host。
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = forwarded_proto or request.url.scheme or "http"
    host = request.url.netloc
    base_url = f"{scheme}://{host}"

    content = template.replace("{{BASE_URL}}", base_url)
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


# 前端構建產物：SPA 靜態檔案服務（必須在所有顯式路由之後掛載）
frontend_dist_dir = PROJECT_ROOT / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """服務 Vite 構建產物，未匹配的路徑回退到 index.html（SPA 路由）。"""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


if frontend_dist_dir.exists():
    app.mount("/", SPAStaticFiles(directory=frontend_dist_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1241, reload=True)
