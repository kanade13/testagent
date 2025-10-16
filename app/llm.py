# app/llm.py
from __future__ import annotations

import os
import json
from typing import Optional, Dict, Any, Tuple

import step
from step import run_plan_chat, CONTEXT_JSON,edit_plan_chat
from .storage import load_plan
# 可用环境变量覆盖默认模型名
DEFAULT_MODEL = os.getenv("TESTAGENT_MODEL_NAME", "qwen3-235b-a22b-thinking-2507")
DEFAULT_MAX_RETRIES = int(os.getenv("TESTAGENT_MAX_RETRIES", "3"))


def generate_or_edit_full_plan(current_plan:Optional[Dict],case_desc:str)-> tuple[dict[str, Any], str]:
    """
    统一对接层：
    - current_plan 为 None → 首次“生成完整 plan”
    - current_plan 不为 None → “基于当前计划的修改”，但仍要求模型输出“完整新 plan”
    返回值：严格为完整的 plan（dict），不包含 meta/patch/action
    """
    model = DEFAULT_MODEL
    max_retries = DEFAULT_MAX_RETRIES
    #如果当前没有计划,说明是要生成新的计划
    if current_plan is None:
        print("生成新计划")
        plan, thinking = run_plan_chat(
            case_name="",
            case_desc=case_desc,
            context_json=CONTEXT_JSON,
            model=model,
            max_retries=max_retries,
        )
        return plan,thinking
    else:
        # 否则是要修改当前计划
        print("修改当前计划")
        current_plan=load_plan()
         # print("current_plan=",current_plan)
        user_input=case_desc
        plan,thinking=edit_plan_chat(
            case_name="",
            case_desc="",
            user_request=user_input,
            current_plan=current_plan,
            context_json=CONTEXT_JSON,
            model=model,
            max_retries=max_retries,
        )
        return plan,thinking

