from fastapi import Header, HTTPException, status, WebSocket
from .config import settings

async def verify_api_key(x_api_key: str | None = Header(default=None)):
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )

async def verify_ws_api_key(websocket: WebSocket) -> bool:
    """
    验证WebSocket连接的API密钥
    期望客户端在连接后发送 {"type": "auth", "api_key": "your_key"}
    """
    try:
        # 等待认证消息
        auth_msg = await websocket.receive_json()
        if auth_msg.get("type") != "auth":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth")
            return False
        
        api_key = auth_msg.get("api_key")
        if settings.API_KEY and api_key != settings.API_KEY:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid API Key")
            return False
        
        return True
    except Exception:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Auth failed")
        return False
