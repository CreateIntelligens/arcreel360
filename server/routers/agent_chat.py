"""
同步 Agent 對話端點

封裝現有 SSE 流式助手為同步請求-響應模式，供 OpenClaw 等外部 Agent 呼叫。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.agent_runtime.runtime_provider import ProviderUnavailableError, UnsupportedCapabilityError
from server.agent_runtime.service import AssistantService
from server.agent_runtime.session_manager import SessionCapacityError
from server.auth import CurrentUser
from server.routers.assistant import get_assistant_service

logger = logging.getLogger(__name__)

router = APIRouter()

SYNC_CHAT_TIMEOUT = 120  # 秒


class AgentChatRequest(BaseModel):
    project_name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    message: str = Field(min_length=1)
    session_id: str | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    reply: str
    status: str  # "completed" | "timeout" | "error"


def _extract_text_from_assistant_message(msg: dict) -> str:
    """從 assistant 型別訊息中提取純文字內容。"""
    content = msg.get("content", [])
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if text and isinstance(text, str):
            parts.append(text)
    return "".join(parts)


TERMINAL_RUNTIME_STATUSES = {"idle", "completed", "error", "interrupted"}


async def _collect_reply(
    service: AssistantService,
    session_id: str,
    timeout: float,
) -> tuple[str, str]:
    """訂閱會話佇列，收集 assistant 回覆直到完成或超時。

    Returns:
        (reply_text, status) — status 為 "completed" / "timeout" / "error"
    """
    queue = await service.session_manager.subscribe(session_id, replay_buffer=True)
    try:
        reply_parts: list[str] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                status = "timeout"
                break

            try:
                message = await asyncio.wait_for(queue.get(), timeout=min(remaining, 5.0))
            except TimeoutError:
                # 檢查會話是否已完成
                live_status = await service.session_manager.get_status(session_id)
                if live_status and live_status != "running":
                    status = "completed" if live_status in {"idle", "completed"} else live_status
                    break
                # 檢查是否超時
                if loop.time() >= deadline:
                    status = "timeout"
                    break
                continue

            msg_type = message.get("type", "")

            if msg_type == "assistant":
                text = _extract_text_from_assistant_message(message)
                if text:
                    reply_parts.append(text)

            elif msg_type == "result":
                # 終結訊息：提取最後一條 assistant 回覆（如果還沒有從佇列裡收到）
                subtype = str(message.get("subtype") or "").lower()
                is_error = bool(message.get("is_error"))
                if is_error or subtype.startswith("error"):
                    status = "error"
                else:
                    status = "completed"
                break

            elif msg_type == "runtime_status":
                runtime_status = str(message.get("status") or "").strip()
                if runtime_status in TERMINAL_RUNTIME_STATUSES and runtime_status != "running":
                    status = "completed" if runtime_status in {"idle", "completed"} else runtime_status
                    break

            elif msg_type == "_queue_overflow":
                # 佇列溢位，中斷
                status = "error"
                break

        return "".join(reply_parts), status

    finally:
        await service.session_manager.unsubscribe(session_id, queue)


@router.post("/agent/chat")
async def agent_chat(
    body: AgentChatRequest,
    _user: CurrentUser,
) -> AgentChatResponse:
    """同步 Agent 對話端點。

    - 若不傳 session_id，則新建會話
    - 若傳入 session_id，則在該會話上下文中繼續對話
    - 內部對接 AssistantService，收集完整響應後返回
    - 超過 120 秒返回已收集的部分響應，status 為 "timeout"
    """
    service = get_assistant_service()

    # 驗證專案是否存在
    try:
        service.pm.get_project_path(body.project_name)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail=f"專案 '{body.project_name}' 不存在")

    # 若傳入 session_id，先校驗會話歸屬
    if body.session_id:
        session = await service.get_session(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"會話 '{body.session_id}' 不存在")
        if session.project_name != body.project_name:
            raise HTTPException(
                status_code=400,
                detail=f"會話 '{body.session_id}' 屬於專案 '{session.project_name}'，與請求專案 '{body.project_name}' 不符",
            )

    # 統一透過 send_or_create 建立或複用會話併傳送訊息。
    # 依賴 replay_buffer=True 緩衝已傳送的訊息，不會產生競爭條件。
    try:
        result = await service.send_or_create(
            body.project_name,
            body.message,
            session_id=body.session_id,
        )
        session_id = result["session_id"]
    except SessionCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="SDK 會話建立超時")
    except UnsupportedCapabilityError as exc:
        raise HTTPException(status_code=409, detail=exc.as_detail())
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # 收集回覆（帶超時）
    reply, status = await _collect_reply(service, session_id, SYNC_CHAT_TIMEOUT)

    # 若未收到文字但有快照，從 snapshot 提取最新助手回覆
    if not reply:
        try:
            snapshot = await service.get_snapshot(session_id)
            turns = snapshot.get("turns", [])
            for turn in reversed(turns):
                if turn.get("role") == "assistant":
                    blocks = turn.get("content", [])
                    text_parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
                    reply = "".join(text_parts)
                    if reply:
                        break
        except Exception as exc:
            logger.warning("獲取快照失敗 session_id=%s: %s", session_id, exc)

    return AgentChatResponse(
        session_id=session_id,
        reply=reply,
        status=status,
    )
