from fastapi import WebSocket, status
from .config import settings

async def verify_ws_api_key(ws: WebSocket) -> bool:
    # WebSocket 不能像 HTTP 路由那样直接用 Depends，所以用 query 参数校验
    api_key = ws.query_params.get("api_key")
    if settings.API_KEY and api_key != settings.API_KEY:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)  # 1008: policy violation
        return False
    return True
