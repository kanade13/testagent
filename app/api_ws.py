# app/api_ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from .core.security import verify_ws_api_key
from .services.prompt_to import WebSocketPromptIO
import main_controller

router_ws = APIRouter()

@router_ws.websocket("/ws/case")
async def ws_case(ws: WebSocket):
    await ws.accept()
    
    try:
        # 客户端首先发送启动参数（包含API密钥验证）
        start_msg = await ws.receive_json()
        if start_msg.get("type") != "start":
            await ws.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # 简化：在start消息中包含api_key验证
        from .core.config import settings
        api_key = start_msg.get("api_key")
        if settings.API_KEY and api_key != settings.API_KEY:
            await ws.send_json({"type": "error", "message": "Invalid API Key"})
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        case_name = start_msg.get("case_name")
        case_desc = start_msg.get("case_desc", "")
        context_json = start_msg.get("context_json", "{}")
        model = start_msg.get("model", "qwen-plus")
        max_retries = int(start_msg.get("max_retries", 3))
        context = start_msg.get("context")

        prompt_io = WebSocketPromptIO(ws)  # ← 注入交互通道

        # 直接 await 异步总控
        try:
            result = await main_controller.run_test_case_async(
                case_name=case_name,
                case_desc=case_desc,
                context_json=context_json,
                model=model,
                max_retries=max_retries,
                context=context,
                prompt_io=prompt_io,   # ← 必填
            )
            await prompt_io.finished(ok=True, data=result)
        except WebSocketDisconnect:
            # 用户断连
            return
        except Exception as e:
            await prompt_io.finished(ok=False, message=str(e))

    except WebSocketDisconnect:
        return
