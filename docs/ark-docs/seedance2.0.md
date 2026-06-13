# Seedance 影片生成模型特性與 Python 開發指南

Seedance 模型具備出色的語義理解能力，可根據使用者輸入的文字、圖片、影片、音訊等多模態內容，快速生成優質的影片片段。本文為您介紹影片生成模型的通用基礎能力，並指導您使用 Python 呼叫 Video Generation API 生成影片。

## 1. 模型能力概覽

本表格展示所有 Seedance 模型支援的能力，方便您對比和選型。

| **能力項**              | **Seedance 2.0**             | **Seedance 2.0 fast**             | **Seedance 1.5 pro**             | **Seedance 1.0 pro**             | **Seedance 1.0 pro fast**             | **Seedance 1.0 lite i2v**             | **Seedance 1.0 lite t2v**             |
| ----------------------- | ---------------------------- | --------------------------------- | -------------------------------- | -------------------------------- | ------------------------------------- | ------------------------------------- | ------------------------------------- |
| **Model ID**            | `doubao-seedance-2-0-260128` | `doubao-seedance-2-0-fast-260128` | `doubao-seedance-1-5-pro-251215` | `doubao-seedance-1-0-pro-250528` | `doubao-seedance-1-0-pro-fast-251015` | `doubao-seedance-1-0-lite-i2v-250428` | `doubao-seedance-1-0-lite-t2v-250428` |
| **文生影片**            | ✅                           | ✅                                | ✅                               | ✅                               | ✅                                    | ✅                                    | ✅                                    |
| **圖生影片-首幀**       | ✅                           | ✅                                | ✅                               | ✅                               | ✅                                    | ✅                                    | -                                     |
| **圖生影片-首尾幀**     | ✅                           | ✅                                | ✅                               | ✅                               | -                                     | ✅                                    | -                                     |
| **多模態參考(圖/影片)** | ✅                           | ✅                                | -                                | -                                | -                                     | ✅ (僅圖片)                           | -                                     |
| **編輯/延長影片**       | ✅                           | ✅                                | -                                | -                                | -                                     | -                                     | -                                     |
| **生成有聲影片**        | ✅                           | ✅                                | ✅                               | -                                | -                                     | -                                     | -                                     |
| **聯網搜尋增強**        | ✅                           | ✅                                | -                                | -                                | -                                     | -                                     | -                                     |
| **樣片模式(Draft)**     | -                            | -                                 | ✅                               | -                                | -                                     | -                                     | -                                     |
| **返回影片尾幀**        | ✅                           | ✅                                | ✅                               | ✅                               | ✅                                    | ✅                                    | ✅                                    |
| **輸出解析度**          | 480p, 720p                   | 480p, 720p                        | 480p, 720p, 1080p                | 480p, 720p, 1080p                | 480p, 720p, 1080p                     | 480p, 720p, 1080p                     | 480p, 720p, 1080p                     |
| **輸出時長(秒)**        | 4~15                         | 4~15                              | 4~12                             | 2~12                             | 2~12                                  | 2~12                                  | 2~12                                  |
| **線上推理 RPM**        | 600                          | 600                               | 600                              | 600                              | 600                                   | 300                                   | 300                                   |
| **併發數**              | 10                           | 10                                | 10                               | 10                               | 10                                    | 5                                     | 5                                     |
| **離線推理(Flex)**      | -                            | -                                 | ✅ (5000億 TPD)                  | ✅ (5000億 TPD)                  | ✅ (5000億 TPD)                       | ✅ (2500億 TPD)                       | ✅ (2500億 TPD)                       |

_(注：✅ 表示支援，- 表示不支援或功能未開放)_

## 2. 新手入門流程

> **提示**：呼叫 API 前，請確保已安裝 Python SDK：`pip install 'volcengine-python-sdk[ark]'`，並配置好環境變數 `ARK_API_KEY`。

影片生成是一個**非同步過程**：

1. 成功呼叫建立介面後，API 返回任務 ID (`task_id`)。
2. 輪詢查詢介面，直到任務狀態變為 `succeeded`（或使用 Webhook 接收通知）。
3. 任務完成後，提取 `content.video_url` 下載 MP4 檔案。

### 步驟 1: 建立影片生成任務

```
import os
from volcenginesdkarkruntime import Ark

client = Ark(api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    resp = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128",
        content=[
            {
                "type": "text",
                "text": "女孩抱著狐狸，女孩睜開眼，溫柔地看向鏡頭，狐狸友善地抱著，鏡頭緩緩拉出，女孩的頭髮被風吹動，可以聽到風聲"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png](https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png)"
                }
            }
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=False,
    )
    print(f"Task Created: {resp.id}")
```

### 步驟 2: 查詢任務狀態

```
import os
from volcenginesdkarkruntime import Ark

client = Ark(api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    # 替換為您建立任務時返回的 ID
    resp = client.content_generation.tasks.get(task_id="cgt-2025****")
    print(resp)

    if resp.status == "succeeded":
        print(f"Video URL: {resp.content.video_url}")
```

## 3. 場景開發實戰 (Python)

### 3.1 純文字生成影片 (Text-to-Video)

根據使用者輸入的提示詞生成影片，結果具有較大的隨機性，可用於激發創作靈感。

```
import os
import time
from volcenginesdkarkruntime import Ark

client = Ark(api_key=os.environ.get("ARK_API_KEY"))

create_result = client.content_generation.tasks.create(
    model="doubao-seedance-2-0-260128",
    content=[
        {
            "type": "text",
            "text": "寫實風格，晴朗的藍天之下，一大片白色的雛菊花田，鏡頭逐漸拉近，最終定格在一朵雛菊花的特寫上，花瓣上有幾顆晶瑩的露珠"
        }
    ],
    ratio="16:9",
    duration=5,
    watermark=True,
)

# 輪詢獲取結果
task_id = create_result.id
while True:
    get_result = client.content_generation.tasks.get(task_id=task_id)
    if get_result.status == "succeeded":
        print(f"任務成功! 影片下載地址: {get_result.content.video_url}")
        break
    elif get_result.status == "failed":
        print(f"任務失敗: {get_result.error}")
        break
    else:
        print(f"處理中 ({get_result.status})... 等待 10 秒")
        time.sleep(10)
```

### 3.2 圖生影片 - 基於首幀 (Image-to-Video)

指定影片的首幀圖片，模型基於該圖片生成連貫影片。設定 `generate_audio=True` 可同步生成音訊。

```
# 構建 content 列表
content = [
    {
        "type": "text",
        "text": "女孩抱著狐狸，鏡頭緩緩拉出，頭髮被風吹動，可以聽到風聲"
    },
    {
        "type": "image_url",
        "image_url": {
            "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png](https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png)"
        }
    }
]

create_result = client.content_generation.tasks.create(
    model="doubao-seedance-2-0-260128",
    content=content,
    generate_audio=True, # 開啟音訊生成
    ratio="adaptive",
    duration=5,
    watermark=True,
)
```

### 3.3 圖生影片 - 基於首尾幀

透過指定影片的起始和結束圖片，生成流暢銜接首、尾幀的影片。

```
content = [
    {
        "type": "text",
        "text": "圖中女孩對著鏡頭說'茄子'，360度環繞運鏡"
    },
    {
        "type": "image_url",
        "image_url": {
            "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_first_frame.jpeg](https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_first_frame.jpeg)"
        },
        "role": "first_frame" # 指定角色為首幀
    },
    {
        "type": "image_url",
        "image_url": {
            "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_last_frame.jpeg](https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_last_frame.jpeg)"
        },
        "role": "last_frame"  # 指定角色為尾幀
    }
]

create_result = client.content_generation.tasks.create(
    model="doubao-seedance-2-0-260128",
    content=content,
    ratio="adaptive",
    duration=5
)
```

### 3.4 圖生影片 - 基於參考圖

模型能精準提取參考圖片（支援輸入 1-4 張）中各類物件的關鍵特徵，並依據這些特徵在影片生成過程中高度還原物件的形態、色彩和紋理等細節，確保生成的影片與參考圖的視覺風格一致。

```
content = [
    {
        "type": "text",
        "text": "[圖1]戴著眼鏡穿著藍色T恤的男生和[圖2]的柯基小狗，坐在[圖3]的草坪上，影片卡通風格"
    },
    {
        "type": "image_url",
        "image_url": {
            "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/seelite_ref_1.png](https://ark-project.tos-cn-beijing.volces.com/doc_image/seelite_ref_1.png)"
        },
        "role": "reference_image" # 指定為參考圖
    },
    {
        "type": "image_url",
        "image_url": {
            "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/seelite_ref_2.png](https://ark-project.tos-cn-beijing.volces.com/doc_image/seelite_ref_2.png)"
        },
        "role": "reference_image"
    },
    {
        "type": "image_url",
        "image_url": {
            "url": "[https://ark-project.tos-cn-beijing.volces.com/doc_image/seelite_ref_3.png](https://ark-project.tos-cn-beijing.volces.com/doc_image/seelite_ref_3.png)"
        },
        "role": "reference_image"
    }
]

create_result = client.content_generation.tasks.create(
    # 注意：需選擇支援該功能的模型，例如 Seedance 1.0 lite i2v
    model="doubao-seedance-1-0-lite-i2v-250428",
    content=content,
    ratio="16:9",
    duration=5
)
```

### 3.5 影片任務管理

**查詢任務列表：**

```
resp = client.content_generation.tasks.list(
    page_size=3,
    status="succeeded",
)
print(resp)
```

**刪除或取消任務：**

```
client.content_generation.tasks.delete(task_id="cgt-2025****")
```

## 4. 提示詞建議

為了獲得更優質、更符合預期的生成結果，推薦遵循以下提示詞編寫原則：

- **核心公式：提示詞 = 主體 + 運動 + 背景 + 運動 + 鏡頭 + 運動 ...** \* **直白準確**：用簡潔準確的自然語言寫出你想要的效果，將抽象描述換成具象描述。
- **分步走策略**：如果有較為明確的效果預期，建議先用生圖模型生成符合預期的圖片，再用**圖生影片**進行影片片段的生成。
- **主次分明**：注意刪除不重要的部分，將重要內容前置。
- **利用隨機性**：純文生影片會有較大的結果隨機性，非常適合用於激發創作靈感。
- **輸入質量**：圖生影片時請儘量上傳高畫質高質量的圖片，上傳圖片的質量對生成的最終影片效果影響極大。

## 5. 高階開發特性

### 5.1 輸出規格引數 (Request Body 控制)

強校驗模式下，建議直接在 Request Body 傳入以下引數控制影片規格：

| **引數**       | **說明**   | **支援取值示例**                                        |
| -------------- | ---------- | ------------------------------------------------------- |
| `resolution`   | 輸出解析度 | `480p`, `720p`, `1080p`                                 |
| `ratio`        | 影片寬高比 | `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `21:9`, `adaptive` |
| `duration`     | 時長(秒)   | 整數型別，例如 `5`                                      |
| `frames`       | 生成幀數   | 優先使用 duration。若用 frames，須滿足 `25 + 4n` 格式   |
| `seed`         | 隨機種子   | 整數值，用於復現生成效果                                |
| `camera_fixed` | 鎖定鏡頭   | `true` 或 `false`                                       |
| `watermark`    | 是否帶水印 | `true` 或 `false`                                       |

### 5.2 離線推理 (Flex Tier)

對於非實時場景，配置 `service_tier="flex"` 可以將呼叫價格降低 50%。

> ⚠️ **注意**：離線推理 (`service_tier: flex`) 僅 Seedance 1.5 Pro 及其以前版本支援，**Seedance 2.0 系列（包括 Fast 版）完全不支援此參數**。若對 2.0 模型發送 `service_tier` 參數將會引發 404/Invalid 錯誤。

```
create_result = client.content_generation.tasks.create(
    model="doubao-seedance-1-5-pro-251215",
    content=[...], # 略
    execution_expires_after=172800,  # 設定任務超時時間
)
```

### 5.3 樣片模式 (Draft Mode)

幫助低成本驗證 prompt 意圖、鏡頭排程等。（_注：目前僅 Seedance 1.5 pro 支援_）

**第一步：生成低成本樣片**

```
create_result = client.content_generation.tasks.create(
    model="doubao-seedance-1-5-pro-251215",
    content=[...],
    seed=20,
    duration=6,
    draft=True # 開啟樣片模式
)
# 獲取返回的 draft_task_id: "cgt-2026****-pzjqb"
```

**第二步：基於樣片生成正式影片**

確認樣片滿意後，利用 draft task id 生成高畫質完整版：

```
create_result = client.content_generation.tasks.create(
    model="doubao-seedance-1-5-pro-251215",
    content=[
        {
            "type": "draft_task",
            "draft_task": {"id": "cgt-2026****-pzjqb"} # 引用樣片任務
        }
    ],
    resolution="720p",
    watermark=False
)
```

### 5.4 Webhook 狀態回撥通知

透過設定 `callback_url`，可以避免輪詢造成的資源浪費。下方是一個接收方舟 Webhook 的簡單 Flask 服務示例：

```
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/webhook/callback', methods=['POST'])
def video_task_callback():
    callback_data = request.get_json()
    if not callback_data:
        return jsonify({"code": 400, "msg": "Invalid data"}), 400

    task_id = callback_data.get('id')
    status = callback_data.get('status')

    logging.info(f"Task Callback | ID: {task_id} | Status: {status}")

    if status == 'succeeded':
        # 此處可以觸發業務邏輯，入庫或透過API抓取內容
        pass

    return jsonify({"code": 200, "msg": "Success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 6. 使用限制與裁剪規則

### 6.1 多模態輸入限制

- **圖片**: 單張 $<30$ MB。支援 jpeg, png, webp 等。尺寸比在 `(0.4, 2.5)` 之間，長度 `300 ~ 6000` px。
- **影片**: 單個 $<50$ MB。支援 mp4, mov。時長 `2~15` 秒。幀率 `24~60` FPS。
- **音訊**: 單個 $<15$ MB。支援 wav, mp3。時長 `2~15` 秒。

### 6.2 自動圖片裁剪規則 (Crop Rule)

當您指定的 `ratio` (影片比例) 與實際傳入的圖片比例不一致時，服務會觸發 **居中裁剪** 邏輯：

1. 若原圖比目標更 "窄高"（原始寬高比 < 目標寬高比），則 **以寬為準**，上下裁切居中。
2. 若原圖比目標更 "寬扁"（原始寬高比 > 目標寬高比），則 **以高為準**，左右裁切居中。

> **建議**：儘量傳入與目標 `ratio` 比例接近的高畫質圖片，以獲得最佳成片效果，避免關鍵主體被裁剪。

### 6.3 任務生命週期

任務資料（如狀態、影片下載連結）**僅保留 24 小時**，超時將自動清除。請在回撥或輪詢確認成功後，儘快將產物下載轉存至您的 OSS 等儲存空間。

---

## 7. 官方 API 參數與常見錯誤參考

### 7.1 模型支援能力對照

| 功能 | Seedance 2.0 & 2.0 Fast | Seedance 1.5 Pro | Seedance 1.0 Pro | 1.0 Pro Fast |
| :--- | :--- | :--- | :--- | :--- |
| **Text to video** | ✅ | ✅ | ✅ | ✅ |
| **Image to video (首幀)** | ✅ | ✅ | ✅ | ✅ |
| **Image to video (首尾幀)** | ✅ | ✅ | ✅ | — |
| **多模態參考 (圖+影片+音訊+文)** | ✅ | — | — | — |
| **樣片模式 (`draft: true`)** | ❌ **不支援** | ✅ | — | — |
| **樣片任務強化 (`draft_task`)** | ❌ **不支援** | ✅ | — | — |
| **音訊生成 (`generate_audio`)** | ✅ | ✅ | — | — |
| **離線推理 (`service_tier: flex`)** | ❌ **不支援** | ✅ | ✅ | ✅ |

### 7.2 Request Body 關鍵欄位補充說明

* **`model`** (string, required): 模型 ID 或 Endpoint ID（以 `ep-` 開頭，生產環境必須使用以 `ep-` 開頭的接入點 ID）。
* **`draft`** (boolean, default: false): 僅 Seedance 1.5 Pro 支援。設為 `true` 會生成 480p 樣片，確認後可在下一個任務傳入 `{"type": "draft_task", "draft_task": {"id": "<樣片任務 ID>"}}` 生成正式版。
* **`service_tier`** (string, default: "default"): **Seedance 2.0 系列不支援**。可用於 1.5 Pro / 1.0 Pro 的 Flex 離線推理。

### 7.3 常見錯誤代碼與解決方法

| 錯誤訊息 | 原因 | 解決方式 |
| :--- | :--- | :--- |
| `draft_task content cannot be mixed with other content types` | `draft_task` 欄位與其他內容類型同時出現在 content 中 | `draft_task` 必須是 content 陣列中唯一的元素。 |
| `task_type draft_task does not support model dreamina-seedance-2-0` | 使用 Seedance 2.0 系列模型發送 `draft_task` | 請改用 Seedance 1.5 Pro 模型 (`seedance-1-5-pro-251215`)。 |
| `InvalidParameter: content` | content 多模態組合不符合規則（如音訊單獨發送） | 音訊不可單獨發送，請至少搭配一張圖片或一部影片，並確認組合符合官方支援規則。 |
| `InvalidEndpointOrModel.NotFound` | 調用時直接使用了原生模型名稱，或者 Endpoint ID 無效/無權限 | 在火山引擎 Ark 平台，調用時必須使用在控制台部署後取得的以 `ep-` 開頭的 Endpoint ID（接入點 ID），請確認「全域設定 -> 模型選擇」配置是否正確。 |

## 8. BytePlus ModelArk 境外版 API 參考 (BytePlus API Reference)

對於使用 **BytePlus ModelArk**（火山引擎海外版）的用戶，其 API 端點及模型 ID 命名規則與國內火山引擎方舟平台略有不同。

* **API Endpoint**: `POST https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks`

### 8.1 常用模型 ID 對照
在海外版 BytePlus ModelArk 中，常用模型 ID 命名一般為 `dreamina-` 開頭：
* `dreamina-seedance-2-0`（Seedance 2.0）
* `dreamina-seedance-2-0-fast`（Seedance 2.0 Fast）
* `dreamina-seedance-1-5-pro`（Seedance 1.5 Pro）
* `dreamina-seedance-1-0-pro`（Seedance 1.0 Pro）

> ⚠️ **重要**：在實際調用時，必須使用在 BytePlus 控制台部署該模型後所生成的以 `ep-` 開頭的 **Endpoint ID**（接入點 ID），直接傳入原生模型 ID 會返回 `InvalidEndpointOrModel.NotFound` 錯誤。

### 8.2 多模態輸入結構 (`content` 欄位)
`content` 欄位為一個陣列（Array），用於傳遞多模態輸入內容。可以包含文本、圖像、影片、音訊或樣片任務：

#### 1. 文本描述 (Text)
* `type`: `"text"`
* `text`: 影片畫面的文字提示詞描述。

#### 2. 首幀圖像 (First Frame Image)
* `type`: `"image_url"`
* `image_url.url`: TOS 或公網可訪問的 HTTP 連結。
* `role`: `"first_frame"`

#### 3. 尾幀圖像 (Last Frame Image)
* `type`: `"image_url"`
* `image_url.url`: TOS 或公網可訪問的 HTTP 連結。
* `role`: `"last_frame"`

#### 4. 參考圖像 (Reference Image)
* `type`: `"image_url"`
* `image_url.url`: TOS 或公網可訪問的 HTTP 連結。
* `role`: `"reference_image"`

#### 5. 影片參考 (Video Reference)
* `type`: `"video_url"`
* `video_url.url`: 影片檔案的 HTTP 連結。
* `role`: `"reference_video"`（例如作為動態或風格參考）

#### 6. 音訊參考 (Audio Reference)
* `type`: `"audio_url"`
* `audio_url.url`: 音訊檔案的 HTTP 連結。
* `role`: `"reference_audio"`（目前僅 Seedance 2.0 系列支持多模態音訊參考）

#### 7. 樣片任務 (Draft Task)
* `type`: `"draft_task"`
* `draft_task.id`: 用於二次強化的 `draft_task_id`（樣片任務 ID）。

### 8.3 狀態碼與常見錯誤說明

* **`400 InvalidParameter`**: 參數格式錯誤、超出限制或多模態組合不支持。
* **`404 InvalidEndpointOrModel.NotFound`**: Endpoint ID 不存在、拼寫錯誤或當前租戶無訪問權限。
* **`413 RequestEntityTooLarge`**: 傳入的圖片或媒體連結之檔案大小超出上限。

