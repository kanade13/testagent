from fastapi import FastAPI
from app.routers.plan import router as plan_router

app = FastAPI()
app.include_router(plan_router, prefix="")

