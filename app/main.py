from fastapi import FastAPI
from .api import router as http_router
from .api_ws import router_ws as ws_router
from .core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# HTTP 路由
app.include_router(http_router, prefix=settings.API_V1_PREFIX)

# WebSocket 路由（无需前缀，或自行决定是否也加 /api/v1）
app.include_router(ws_router)
