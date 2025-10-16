from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, ValidationError
from typing import Optional

from step import PLAN_SCHEMA

from jsonschema import validate, ValidationError
from app.state import EditRequest, PlanResponse, PlanResponseWithState, PlanStatus
from app.storage import load_plan, save_plan_and_bump, load_state, set_status, clear_all
from app.llm import generate_or_edit_full_plan
from utils import validate_plan
router = APIRouter()

class FallbackPlan(BaseModel):
    model_config = ConfigDict(extra="allow")  # 允许任意字段
#health 检查
@router.get("/healthz")
def health_check():
    return {"status": "ok"}
@router.post("/plan", response_model=PlanResponse)
def create_or_edit_plan(payload: EditRequest):
    """
    统一入口：状态 EMPTY → 创建；否则 → 修改。
    仅返回 plan（不返回 meta/patch/action）。
    """
    state = load_state()
    current = load_plan()
    '''
    if state.status == PlanStatus.ACCEPTED:
        # 已锁定需先解锁
        raise HTTPException(status_code=423, detail="Plan is ACCEPTED (locked). Use /plan/unlock to modify.")
    '''
    new_plan,thinking= generate_or_edit_full_plan(current_plan=current,case_desc=payload.case_desc)
    # 校验
    validate_plan(new_plan)

    # 保存 + 版本自增 + 状态置 DRAFT
    try:
        save_plan_and_bump(plan=new_plan, status=PlanStatus.DRAFT, base_version=payload.base_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))  # 版本冲突（If-Match 失败）

    return {"plan":new_plan,"thinking":thinking}

@router.get("/plan", response_model=PlanResponse | PlanResponseWithState)
def get_plan(include_state: bool = Query(default=False, description="调试用途：附带状态")):
    plan = load_plan()
    if plan is None:
        raise HTTPException(status_code=404, detail="No current plan")
    if include_state:
        return PlanResponseWithState(plan=plan, state=load_state())
    return PlanResponse(plan=plan)

@router.post("/plan/accept")
def accept_plan():
    """
    用户确认：DRAFT → ACCEPTED
    """
    plan = load_plan()
    if plan is None:
        raise HTTPException(status_code=400, detail="No plan to accept")
    st = set_status(PlanStatus.ACCEPTED)
    return {"ok": True, "status": st.status}

@router.post("/plan/unlock")
def unlock_plan():
    """
    允许继续修改：ACCEPTED → DRAFT
    """
    plan = load_plan()
    if plan is None:
        raise HTTPException(status_code=400, detail="No plan to unlock")
    state = load_state()
    if state.status != PlanStatus.ACCEPTED:
        return {"ok": True, "status": state.status}
    st = set_status(PlanStatus.DRAFT)
    return {"ok": True, "status": st.status}

@router.post("/plan/clear")
def clear_plan():
    """
    清空当前计划与状态：回到 EMPTY（历史保留）
    """
    clear_all()
    return {"ok": True, "status": "EMPTY"}
