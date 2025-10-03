import os
import re
import json
import time
import pathlib
from copy import deepcopy
from typing import Dict, Any, List, Optional, Tuple

from openai import OpenAI
from jsonschema import validate, ValidationError
from step import run_plan_chat,save_plan_to_json, load_context_json, CTX_PATH, PLAN_SCHEMA
# ----------- 通用工具 -----------
def validate_plan(plan: Dict[str, Any],plan_schema:Dict[str,Any]=PLAN_SCHEMA) -> Tuple[bool, Optional[str]]:
    try:
        validate(instance=plan, schema=plan_schema)
        return True, None
    except ValidationError as e:
        return False, str(e)

def now_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())

def json_pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

def extract_first_json_blob(text: str) -> Optional[Dict[str, Any]]:
    """
    从模型回复中提取第一段 {...} JSON。
    """
    try:
        # 粗暴但实用：匹配最外层花括号
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            blob = text[start:end+1]
            return json.loads(blob)
    except Exception:
        pass
    return None

def check_json_format(target_text:Dict[str,Any],format:Dict[str,Any]) -> bool:
    """
    检查目标文本是否符合指定的JSON格式。
    """
    try:
        validate(instance=target_text, schema=format)
        return True
    except ValidationError:
        print("JSON格式不符合要求。")
        return False

def _find_step_index_by_order(plan: Dict[str, Any], order: int) -> Optional[int]:
    for i, s in enumerate(plan.get("steps", [])):
        if s.get("order") == order:
            return i
    return None


# ---------- 日志工具 ----------
def write_log(log_path: pathlib.Path, tag: str, content: str) -> None:
    """向日志文件追加一条记录"""
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n[{now_ts()}] {tag}\n")
        f.write(content.strip() + "\n")