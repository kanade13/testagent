#!/usr/bin/env python3
# test_client.py
"""
测试客户端：测试 FastAPI 的各个 /run/case/* 路由。
用法：
    python test_client.py all
    python test_client.py generate
    python test_client.py parse_command
    python test_client.py respond_command
    python test_client.py answer
    python test_client.py execute_step
    python test_client.py validate_plan
"""

import requests
import json
import sys
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from main_controller import CONTEXT_JSON
class CaseInput(BaseModel):
    case_name: str = Field(None, description="测试用例名称")
    case_desc: str = Field(..., description="测试用例描述")
    context_json: str = Field(CONTEXT_JSON, description="上下文 JSON 字符串")
    model: str = Field("qwen3-235b-a22b-instruct-2507", description="使用的模型")
    max_retries: int = Field(3, description="最大重试次数")
    context: Optional[Dict[str, Any]] = Field(None, description="可选上下文信息")
    user_command: Optional[str] = Field(None, description="用户命令")
ENDPOINT_GENERATE = "/run/case/generate"
ENDPOINT_PARSE = "/run/case/parse_command"
ENDPOINT_RESPOND = "/run/case/respond_command"
ENDPOINT_ANSWER = "/run/case/answer"
ENDPOINT_EXECUTE = "/run/case/execute_step"
ENDPOINT_VALIDATE = "/run/case/validate_plan"
HEADERS = {"Content-Type": "application/json"}
def start_test():
    BASE_URL="http://112.29.111.158:20307/api/v1/"

    print("请输入case_name(可选),case_desc,model(可选),max_retries(可选)")
    case_name = input("case_name: ").strip() or ""
    case_desc = input("case_desc: ").strip()
    model = input("model: ").strip() or "qwen3-235b-a22b-instruct-2507"
    max_retries = input("max_retries: ").strip()
    max_retries = int(max_retries) if max_retries.isdigit() else 3
    #包装为caseinput类
    
    case_input = CaseInput(
        case_name=case_name,
        case_desc=case_desc,
        context_json=CONTEXT_JSON,
        model=model,
        max_retries=max_retries,
        user_command=""
    )

    # 生成测试计划
    payload = case_input or SAMPLE_CASEINPUT
    plan = requests.post(url(ENDPOINT_GENERATE), headers=HEADERS, json=payload, timeout=60)
    print("生成的测试计划：", plan.json())

if __name__ == "__main__":
    start_test()
