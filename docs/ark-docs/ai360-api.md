# ai360 Video Studio — 外部串接完整指南

Base URL：`https://your-domain.com`
Swagger 測試介面：`https://your-domain.com/api/docs`

---

## 基本資訊

| 項目 | 說明 |
|------|------|
| 請求格式 | JSON（`Content-Type: application/json`），上傳除外 |
| 回應格式 | JSON，成功回應均包含 `"ok": true` |
| 錯誤格式 | `{"ok": false, "error": "...", "details": ...}` |
| 認證方式 | JWT Bearer Token（每次請求帶 `Authorization: Bearer <token>`） |

---

## 串接流程總覽

```
1. POST /api/auth/login          → 拿 JWT token（30 天有效，過期收到 401 需重新登入）
2. GET  /api/projects            → 拿到 project_id
3. GET  /api/assets              → 確認現有素材與 token（可選）
   DELETE /api/assets/{id}       → 封存不需要的素材（可選）
   POST /api/assets/upload       → 上傳參考素材（可選）
4. POST /api/video/create        → 建立生成任務，拿到 historyId
5. GET  /api/history/{historyId} → 輪詢直到 status=succeeded
6.                                  取 task.videoUrl 或 outputs[].url 顯示影片
```

---

## Step 1 — 登入取得 Token

### `POST /api/auth/login`

```http
POST /api/auth/login
Content-Type: application/json
```

**Request：**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**Response：**
```json
{
  "ok": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "your_username",
    "role": "user"
  }
}
```

Token 有效期 **30 天**。之後所有請求帶：

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Step 2 — 取得 Project ID

### `GET /api/projects`

```http
GET /api/projects
Authorization: Bearer <token>
```

**Response：**
```json
{
  "ok": true,
  "projects": [
    {
      "id": 42,
      "name": "我的專案",
      "taskCount": 10,
      "assetCount": 3,
      "lastTaskAt": "2026-06-01T08:00:00Z",
      "createdAt": "2026-05-01T00:00:00Z"
    }
  ]
}
```

記下 `projects[0].id`。之後所有需要專案的請求帶：

```http
X-Project-Id: 42
```

---

## Step 3 — 上傳參考素材（可選）

### `POST /api/assets/upload`

```http
POST /api/assets/upload?kind=image
Authorization: Bearer <token>
X-Project-Id: 42
Content-Type: multipart/form-data
```

**Query 參數：**

| 參數 | 必填 | 值 |
|------|------|-----|
| `kind` | ✓ | `image` / `video` / `audio` |

**上傳限制：**

| 種類 | 數量上限 | 格式 | 其他限制 |
|------|---------|------|---------|
| image | 9 | PNG / JPG / WEBP / GIF | — |
| video | 3 | MP4 / MOV | 2–15 秒，解析度 ≥16×16，寬高為偶數 |
| audio | 3 | MP3 / WAV | 單檔 1.8–15 秒、單檔 ≤15MB，累計總時長 ≤15 秒 |

**Response：**
```json
{
  "ok": true,
  "uploadedIds": [7],
  "assets": {
    "counts": { "image": 1, "video": 0, "audio": 0 },
    "items": {
      "image": [
        {
          "id": 7,
          "kind": "image",
          "name": "cat.jpg",
          "token": "@圖片1",
          "index": 1,
          "previewUrl": "https://your-domain.com/media/uuid_cat.jpg"
        }
      ],
      "video": [],
      "audio": []
    }
  }
}
```

上傳後素材保留在專案中，下次生成可直接引用，不需要重新上傳。

---

### 查看目前專案的素材與 Token

每次生成前，先呼叫這個端點確認目前有哪些素材、各自對應的 token：

```http
GET /api/assets
Authorization: Bearer <token>
X-Project-Id: 42
```

**Response：**
```json
{
  "ok": true,
  "assets": {
    "counts": { "image": 2, "video": 1, "audio": 0 },
    "items": {
      "image": [
        { "id": 7,  "token": "@圖片1", "name": "cat.jpg",    "previewUrl": "https://your-domain.com/media/uuid_cat.jpg" },
        { "id": 12, "token": "@圖片2", "name": "sunset.png",  "previewUrl": "https://your-domain.com/media/uuid_sunset.png" }
      ],
      "video": [
        { "id": 9,  "token": "@影片1", "name": "clip.mp4",   "previewUrl": "https://your-domain.com/media/uuid_clip.mp4" }
      ],
      "audio": []
    },
    "archivedItems": {
      "image": [
        { "id": 5, "name": "old.jpg", "previewUrl": "..." }
      ],
      "video": [], "audio": []
    }
  }
}
```

- `items` 裡的素材才是「作用中」的，會被計入 token 順序和數量上限
- `archivedItems` 是已封存的素材，不佔用配額、不出現在生成任務中
- **token 由各種類的上傳順序決定**：`items.image[0]` → `@圖片1`，`items.image[1]` → `@圖片2`，以此類推

---

### 封存不需要的素材

不需要的素材應封存（軟刪除），避免佔用配額或被誤引用：

```http
DELETE /api/assets/{asset_id}
Authorization: Bearer <token>
X-Project-Id: 42
```

封存後該素材移入 `archivedItems`，不再佔用數量上限，也不會出現在生成任務中。**token 會重新編號**（例如封存 `@圖片1` 後，原本的 `@圖片2` 會變成 `@圖片1`）。

若要永久刪除（同時清除本機與 888box 檔案）：

```http
DELETE /api/assets/{asset_id}/permanent
Authorization: Bearer <token>
X-Project-Id: 42
```

---

**Prompt 引用 token 規則：**

| 種類 | Token 格式 | 數量上限 |
|------|-----------|---------|
| 圖片 | `@圖片1`、`@圖片2`、... | 最多 9 |
| 影片 | `@影片1`、`@影片2`、... | 最多 3 |
| 音訊 | `@聲音1`、`@聲音2`、... | 最多 3，累計 ≤15 秒 |

**建議的素材管理流程：**
```
每次生成前：
1. GET /api/assets              → 確認當前作用中素材與 token
2. DELETE /api/assets/{id}      → 封存不需要的舊素材
3. POST /api/assets/upload      → 上傳這次要用的新素材
4. 確認 GET /api/assets 的 token 對應正確後再生成
```

---

## Step 4 — 建立生成任務

### `POST /api/video/create`

```http
POST /api/video/create
Authorization: Bearer <token>
X-Project-Id: 42
Content-Type: application/json
```

**Request（最簡）：**
```json
{
  "prompt": "一隻貓在草原上奔跑，電影質感，黃金時刻光線"
}
```

**Request（帶參考素材）：**
```json
{
  "prompt": "@圖片1 這個人物走進咖啡廳，環境光，寫實風格"
}
```

**Request（完整欄位）：**
```json
{
  "prompt": "一隻貓在草原上奔跑",
  "duration": 8,
  "ratio": "16:9",
  "resolution": "720p",
  "generateAudio": true,
  "watermark": false,
  "returnLastFrame": true
}
```

**欄位說明：**

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `prompt` | string | 必填 | 生成提示詞，可含 `@圖片N` 等 token |
| `duration` | integer | **5** | 生成秒數（4–15），或 `-1` 讓系統自動決定 |
| `ratio` | string | `16:9` | `16:9` / `9:16` / `1:1` / `4:3` / `3:4` / `21:9` / `adaptive` |
| `resolution` | string | `720p` | `480p` / `720p` / `1080p` |
| `generateAudio` | boolean | **false** | 是否生成音訊（true 會增加生成時間與費用） |
| `watermark` | boolean | false | 是否加浮水印 |
| `returnLastFrame` | boolean | **false** | 是否返回最後一幀圖片 |

**Response：**
```json
{
  "ok": true,
  "historyId": 123,
  "task": {
    "taskId": "cgt-20260601xxxxxx",
    "status": "submitted"
  }
}
```

儲存 `historyId`（本地記錄 ID），下一步輪詢使用。

---

## Step 5 — 輪詢任務狀態

### `GET /api/history/{historyId}`

建議每 **5 秒**輪詢一次，使用 Step 4 回傳的 `historyId`（本地記錄 ID）。

```http
GET /api/history/123
Authorization: Bearer <token>
X-Project-Id: 42
```

**Response（進行中）：**
```json
{
  "ok": true,
  "task": {
    "id": 123,
    "status": "running",
    "prompt": "一隻貓在草原上奔跑..."
  }
}
```

**Response（完成）：**
```json
{
  "ok": true,
  "task": {
    "id": 123,
    "status": "succeeded",
    "prompt": "一隻貓在草原上奔跑...",
    "videoUrl": "/generated/videos/task_123_video_abc.mp4",
    "lastFrameUrl": "/generated/frames/task_123_frame_abc.jpg",
    "outputs": [
      {
        "id": 1,
        "kind": "video",
        "url": "/generated/videos/task_123_video_abc.mp4",
        "sourceUrl": "https://cdn.byteplus.com/...",
        "mimeType": "video/mp4",
        "sizeBytes": 5242880
      },
      {
        "id": 2,
        "kind": "frame",
        "url": "/generated/frames/task_123_frame_abc.jpg",
        "sourceUrl": "https://cdn.byteplus.com/...",
        "mimeType": "image/jpeg",
        "sizeBytes": 102400
      }
    ]
  }
}
```

**Response（失敗）：**
```json
{
  "ok": true,
  "task": {
    "id": 123,
    "status": "failed",
    "errorMessage": "[InvalidParam] 提示詞不符合規範"
  }
}
```

**status 值：**

| 值 | 說明 |
|----|------|
| `submitted` | 已送出，等待佇列 |
| `running` | 生成中 |
| `succeeded` | 完成 ✅ |
| `failed` | 失敗 ❌ |
| `cancelled` | 已取消 |

---

## Step 6 — 取得結果 URL

`task.videoUrl` 或 `outputs[].url` 加上 Base URL 即為可直接存取的公開連結：

```
https://your-domain.com/generated/videos/task_123_video_abc.mp4
https://your-domain.com/generated/frames/task_123_frame_abc.jpg
```

這些 URL **無需認證**，可直接嵌入前端：

```html
<video src="https://your-domain.com/generated/videos/task_123_video_abc.mp4" controls></video>
<img src="https://your-domain.com/generated/frames/task_123_frame_abc.jpg" />
```

---

## 其他常用端點

### 取消任務

```http
POST /api/video/cancel/{taskId}
Authorization: Bearer <token>
Content-Type: application/json

{}
```

**Response：**
```json
{
  "ok": true,
  "task": { "taskId": "...", "status": "cancelled" }
}
```

---

### 查詢歷史紀錄

```http
GET /api/history?limit=20&offset=0
Authorization: Bearer <token>
X-Project-Id: 42
```

**Query 參數：**

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `limit` | 每頁筆數（最大 50） | 20 |
| `offset` | 分頁偏移 | 0 |
| `search` | 關鍵字搜尋 prompt | — |

**Response：**
```json
{
  "ok": true,
  "tasks": [
    {
      "id": 123,
      "status": "succeeded",
      "prompt": "一隻貓在草原上奔跑...",
      "videoUrl": "/generated/videos/task_123_video_abc.mp4",
      "createdAt": "2026-06-01T08:00:00Z"
    }
  ],
  "total": 30
}
```

---

### 查詢當前使用者

```http
GET /api/auth/me
Authorization: Bearer <token>
```

**Response：**
```json
{
  "ok": true,
  "user": {
    "id": 1,
    "username": "your_username",
    "role": "user"
  }
}
```

---

## 錯誤處理

所有錯誤回應格式一致：

```json
{
  "ok": false,
  "error": "錯誤說明",
  "details": { ... }
}
```

**常見 HTTP 狀態碼：**

| 狀態碼 | 說明 |
|--------|------|
| `400` | 請求參數錯誤（如缺少 X-Project-Id、素材超限） |
| `401` | 未登入或 token 無效/過期 |
| `403` | 無權限存取該資源 |
| `404` | 資源不存在 |
| `500` | 伺服器錯誤 |

---

## 注意事項

- **Token 有效期 30 天**。過期後所有 API 請求會回傳 `401`，此時需重新呼叫 `POST /api/auth/login` 取得新 token 後繼續。
- **輪詢間隔建議 5 秒**，生成通常需要 1–3 分鐘。
- **生成結果 URL 為公開連結**，任何拿到 URL 的人都可以直接存取。
- **素材上傳後保留在專案中**，可跨任務重複引用；不需要的素材請封存以免影響 token 編號。
- **Swagger UI** 可在 `https://your-domain.com/api/docs` 直接測試（點 Authorize 填入 token）。

## 參考API文件
- http://nurse.5gao.ai:3778/api/docs
