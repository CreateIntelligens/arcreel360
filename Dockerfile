# ============================================================
# Runtime image: 僅安裝系統依賴與 Python 依賴
# 應用程式碼（lib/server/alembic/scripts/agent_runtime_profile/public）
# 與前端構建產物 frontend/dist 透過 docker-compose volume 掛載進入容器，
# 不在映象內 COPY。
# ============================================================
FROM python:3.12-slim AS runner

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 禁用 Python 輸出緩衝，確保日誌實時輸出到 Docker logs
ENV PYTHONUNBUFFERED=1 \
    HOME=/app/.home \
    PORT=1241 \
    UV_CACHE_DIR=/app/.cache/uv \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# 預建立執行時目錄並放寬許可權，使容器以非 root（uid 1000）執行時可寫。
# 此步驟與依賴內容無關，刻意排在 COPY/uv sync 之前：
#   1. 此時 /app 尚空，chmod -R 僅作用於數個空目錄，瞬間完成；
#   2. 不會被 pyproject.toml/uv.lock 變更牽連而重跑，可長期命中 build cache。
# projects / vertex_keys / frontend/dist / claude_data 等均由 compose 掛載覆蓋
RUN mkdir -p projects vertex_keys frontend/dist .home/.claude .cache/uv \
    && chmod -R 0777 /app

# 僅複製依賴與包後設資料檔案，安裝到映象內的虛擬環境
# （依賴必須在映象中預裝，否則啟動時掛載原始碼後會缺少 site-packages）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --no-install-project \
    && chmod -R a+rwX .cache/uv

EXPOSE 1241

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f "http://localhost:${PORT:-1241}/health" || exit 1

CMD ["sh", "-c", "uv run --no-sync uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-1241}"]
