# 貢獻指南

歡迎貢獻程式碼、報告 Bug 或提出功能建議！

## 本地開發環境

```bash
# 前置要求：Python 3.12+, Node.js 20+, uv, pnpm, ffmpeg

# 安裝依賴
uv sync
cd frontend && pnpm install && cd ..

# 初始化資料庫
uv run alembic upgrade head

# 啟動後端 (終端 1)
uv run uvicorn server.app:app --reload --port 1241

# 啟動前端 (終端 2)
cd frontend && pnpm dev

# 訪問 http://localhost:5173
```

## 執行測試

```bash
# 後端測試
python -m pytest

# 前端型別檢查 + 測試
cd frontend && pnpm check
```

## 程式碼質量

**Lint & Format（ruff）：**

```bash
uv run ruff check . && uv run ruff format .
```

- 規則集：`E`/`F`/`I`/`UP`，忽略 `E402` 和 `E501`
- line-length：120
- CI 中強制檢查：`ruff check . && ruff format --check .`

**測試覆蓋率：**

- CI 要求 ≥80%
- `asyncio_mode = "auto"`（無需手動標記 async 測試）

## 提交規範

Commit message 採用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
feat: 新增功能描述
fix: 修復問題描述
refactor: 重構描述
docs: 文件變更
chore: 構建/工具變更
```
