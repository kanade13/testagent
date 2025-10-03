from fastapi import APIRouter, HTTPException, status

router = APIRouter()

@router.post("/case/run")
async def api_run_case_unavailable():
    # 明确告诉调用方：必须用 WebSocket
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Interactive run requires WebSocket. Connect to /ws/case?api_key=YOUR_KEY"
    )

@router.get("/healthz")
async def health_check():
    return {"status": "ok"}
