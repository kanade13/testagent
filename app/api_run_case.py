from fastapi import APIRouter, Body, HTTPException
from typing import Any, Dict, Optional
from pydantic import BaseModel
import json
import schemas
from schemas import CaseInput
import main_controller as controller
import step
router_run = APIRouter()




@router_run.post("/run/case/generate")
def generate_plan(case: CaseInput) -> Dict[str, Any]:
    """生成测试计划（单次请求），接收一个 CaseInput 对象"""
    try:
        plan = step.run_plan_chat(case_name=case.case_name,
                                  case_desc=case.case_desc,
                                  context_json=case.context_json,
                                  model=case.model
                                  max_retries=case.max_retries)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    ok, err = controller.validate_plan(plan, controller.PLAN_SCHEMA)
    if not ok:
        raise HTTPException(status_code=400, detail=f"生成的计划不符合 SCHEMA: {err}")
    return {"ok": True, "plan": plan}


def _try_load_json(s: str):
    """尝试把字符串解析为 JSON，否则返回原始字符串"""
    try:
        return json.loads(s)
    except Exception:
        return s


@router_run.post("/run/case/parse_command")
def parse_command_endpoint(text: str = Body(...)) -> Dict[str, Any]:
    """接收单个字符串 text；若 text 为 JSON 对象，尝试解析为 {user_text, plan, current_step, context_json, model}，否则当作 user_text 并要求在返回中给出提示。"""
    payload = _try_load_json(text)
    client = controller.OpenAI()
    if isinstance(payload, dict):
        user_text = payload.get("user_text") or payload.get("text")
        plan = payload.get("plan")
        current_step = payload.get("current_step", 1)
        context_json = payload.get("context_json")
        model = payload.get("model", "qwen3-235b-a22b-instruct-2507")
    else:
        user_text = payload
        plan = {}
        current_step = 1
        context_json = controller.CONTEXT_JSON
        model = "qwen3-235b-a22b-instruct-2507"

    try:
        cmd = controller.parse_command_with_llm(
            client=client,
            model=model,
            user_text=user_text,
            plan=plan,
            current_step=current_step,
            context_json=context_json,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "cmd": cmd}


@router_run.post("/run/case/answer")
def answer_endpoint(text: str = Body(...)) -> Dict[str, Any]:
    """接收单个字符串 text；若为 JSON 可包含 {question, plan, target_step, context_json, model}，否则当作 question 并使用默认 context。"""
    payload = _try_load_json(text)
    client = controller.OpenAI()
    if isinstance(payload, dict):
        question = payload.get("question") or payload.get("text")
        plan = payload.get("plan")
        target_step = payload.get("target_step")
        context_json = payload.get("context_json")
        model = payload.get("model", "qwen3-235b-a22b-instruct-2507")
    else:
        question = payload
        plan = {}
        target_step = None
        context_json = controller.CONTEXT_JSON
        model = "qwen3-235b-a22b-instruct-2507"

    try:
        ans = controller.answer_user_question(
            client=client,
            model=model,
            question=question,
            plan=plan,
            context_json=context_json,
            target_step=target_step,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "answer": ans}


@router_run.post("/run/case/execute_step")
def execute_step_endpoint(text: str = Body(...)) -> Dict[str, Any]:
    """接收单个字符串 text；若为 JSON 则解析为 step_obj 并执行，否则返回错误"""
    payload = _try_load_json(text)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="execute_step 需要 JSON 格式的 step 对象字符串")
    try:
        ok = controller.execute_step(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "success": bool(ok)}


@router_run.post("/run/case/validate_plan")
def validate_plan_endpoint(text: str = Body(...)) -> Dict[str, Any]:
    payload = _try_load_json(text)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="validate_plan 需要 JSON 格式的 plan 对象字符串")
    ok, err = controller.validate_plan(payload, controller.PLAN_SCHEMA)
    return {"ok": ok, "error": err}
