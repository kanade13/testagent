from fastapi import FastAPI
from .api import router
from .core.config import settings
from .api_ws import router_ws
app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(router, prefix=settings.API_V1_PREFIX)
app.include_router(router_ws, prefix=settings.API_V1_PREFIX)