# 從 SQLite 遷移到 PostgreSQL

本文件適用於已使用預設 SQLite 部署 ArcReel、希望切換到 PostgreSQL 的場景。

## 前置條件

- 已安裝 Docker 和 Docker Compose
- ArcReel 當前使用 SQLite 執行（資料庫檔案位於 `projects/.arcreel.db`）

## 遷移步驟

### 1. 停止 ArcReel 服務

```bash
# 如果透過 Docker 執行
docker compose down

# 如果透過命令列直接執行，停止 uvicorn 程序
```

### 2. 備份 SQLite 資料庫

```bash
cp projects/.arcreel.db projects/.arcreel.db.bak
```

### 3. 配置環境變數

在 `.env` 中新增以下變數（用於 docker-compose 中 PostgreSQL 容器的初始化）：

```env
POSTGRES_PASSWORD=你的資料庫密碼
```

> `DATABASE_URL` 無需手動設定，已在 `docker-compose.yml` 中透過 `POSTGRES_PASSWORD` 自動拼接。

### 4. 啟動 PostgreSQL

先只啟動資料庫服務：

```bash
docker compose up -d postgres
```

等待健康檢查透過：

```bash
docker compose ps  # 確認 postgres 狀態為 healthy
```

### 5. 遷移資料

在 ArcReel 容器內使用 pgloader 將 SQLite 資料直接遷移到 PostgreSQL：

```bash
docker compose run --rm arcreel bash -c "
  apt-get update && apt-get install -y --no-install-recommends pgloader &&
  pgloader sqlite:///app/projects/.arcreel.db \
           postgresql://arcreel:\${POSTGRES_PASSWORD}@postgres:5432/arcreel
"
```

> pgloader 會自動處理 SQLite 與 PostgreSQL 之間的型別和語法差異（布林值、時間格式等），
> 並跳過已存在的表結構，只匯入資料。

### 6. 驗證資料

```bash
docker compose exec postgres psql -U arcreel -d arcreel -c "
  SELECT 'tasks' AS tbl, COUNT(*) FROM tasks
  UNION ALL
  SELECT 'api_calls', COUNT(*) FROM api_calls
  UNION ALL
  SELECT 'agent_sessions', COUNT(*) FROM agent_sessions
  UNION ALL
  SELECT 'api_keys', COUNT(*) FROM api_keys;
"
```

對比 SQLite 中的記錄數：

```bash
sqlite3 projects/.arcreel.db "
  SELECT 'tasks', COUNT(*) FROM tasks
  UNION ALL
  SELECT 'api_calls', COUNT(*) FROM api_calls
  UNION ALL
  SELECT 'agent_sessions', COUNT(*) FROM agent_sessions
  UNION ALL
  SELECT 'api_keys', COUNT(*) FROM api_keys;
"
```

### 7. 啟動完整服務

```bash
docker compose up -d
```

訪問 `http://<你的IP>:1241` 驗證服務正常。

---

## 回滾到 SQLite

如果需要回退：

1. 停止服務：`docker compose down`
2. 恢復備份：`cp projects/.arcreel.db.bak projects/.arcreel.db`
3. 移除 `.env` 中的 `POSTGRES_PASSWORD`，不使用 `docker-compose.yml` 中的 PostgreSQL 配置啟動
