from fastapi import APIRouter, Depends
from .schemas import CaseInput, ExecResult
from .services.adapter import run_plan
from .core.security import verify_api_key

router = APIRouter()

@router.post("/case/run", response_model=ExecResult, dependencies=[Depends(verify_api_key)])
async def api_run_case(payload: CaseInput):
    if not payload.context_json:
        from main_controler import CONTEXT_JSON
        payload.context_json = CONTEXT_JSON
    return run_plan(
        case_name=payload.case_name,
        case_desc=payload.case_desc,
        context_json=payload.context_json,
        model=payload.model,
        max_retries=payload.max_retries,
        context=payload.context
    )
@router.get("/healthz")
async def health_check():
    return {"status": "ok"}