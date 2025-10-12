from fastapi import APIRouter, Body, HTTPException
from typing import Any, Dict, Optional
from pydantic import BaseModel
import json

from .schemas import CaseInput
import main_controller as controller
import step

router_run = APIRouter()



CONTEXT_JSON=controller.CONTEXT_JSON
@router_run.post("/run/case/generate")
def generate_plan(case: CaseInput) -> Dict[str, Any]:
    """生成测试计划（单次请求），接收一个 CaseInput 对象"""
    try:
        plan,thinking_content = step.run_plan_chat(case_name=case.case_name,
                                  case_desc=case.case_desc,
                                  context_json=CONTEXT_JSON,
                                  model=case.model,
                                  max_retries=case.max_retries)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    ok, err = controller.validate_plan(plan, controller.PLAN_SCHEMA)
    if not ok:
        raise HTTPException(status_code=400, detail=f"生成的计划不符合 SCHEMA: {err}")
    return {"ok": True, "plan": plan,"thinking_content":thinking_content}


def _try_load_json(s: str):
    """尝试把字符串解析为 JSON，否则返回原始字符串"""
    try:
        return json.loads(s)
    except Exception:
        return s


@router_run.post("/run/case/parse_command")
def parse_command_endpoint(case:CaseInput) -> Dict[str, Any]:
    """接收单个字符串 text；若 text 为 JSON 对象，尝试解析为 {user_text, plan, current_step, context_json, model}，否则当作 user_text 并要求在返回中给出提示。"""
    payload= case.dict()
    client = controller.OpenAI()
    if isinstance(payload, dict):
        user_text = payload.get("user_text") 
        plan = payload.get("plan")
        current_step = payload.get("current_step", 0)
        context_json = payload.get("context_json")
        model = payload.get("model", "qwen3-235b-a22b-instruct-2507")
    try:
        #print("plan:", plan, flush=True)
        #print("user_text:", user_text, flush=True)
        cmd = controller.parse_command_with_llm(
            client=client,
            model=model,
            user_text=user_text,
            plan=plan,
            current_step=current_step,
            context_json=CONTEXT_JSON
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "cmd": cmd,"plan":plan,"user_text":user_text,"current_step":current_step}


@router_run.post("/run/case/answer")
def answer_endpoint(case:CaseInput) -> Dict[str, Any]:
    """接收单个字符串 text；若为 JSON 可包含 {question, plan, target_step, context_json, model}，否则当作 question 并使用默认 context。"""
    payload = case.dict()
    client = controller.OpenAI()
    if isinstance(payload, dict):
        question = payload.get("question") 
        plan = payload.get("plan")
        target_step = payload.get("target_step", None)
        context_json = payload.get("context_json")
        model = payload.get("model", "qwen3-235b-a22b-instruct-2507")
        user_text = payload.get("user_text", None)

    try:
        ans = controller.answer_user_question(
            client=client,
            model=model,
            question=user_text,
            plan=plan,
            context_json=CONTEXT_JSON,
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
def validate_plan_endpoint(case:CaseInput) -> Dict[str, Any]:
    payload= case.dict()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="validate_plan 需要 JSON 格式的 plan 对象字符串")
    ok, err = controller.validate_plan(payload, controller.PLAN_SCHEMA)
    return {"ok": ok, "error": err}
