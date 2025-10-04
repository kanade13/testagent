# api.py
import asyncio
import json
import pathlib
import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from .schemas import CaseInput, ExecResult
from .core.security import verify_api_key


import main_controller  # ← 统一用这个拼写


# 异步工具与阶段逻辑
from .async_async_ops import (
    CaseRunnerCtx,
    send_event,
    a_run_plan_chat,
    a_parse_command_with_llm,
    a_validate_plan,
    a_execute_step,
    a_answer_user_question,
    a_write_log,
    stage1_show_and_confirm_ws,
    stage2_stepwise_execute_ws,
)

router = APIRouter()


@router.get("/healthz")
async def health_check():
    return {"status": "ok"}


@router.post("/case/run", response_model=ExecResult, dependencies=[Depends(verify_api_key)])
async def api_run_case(payload: CaseInput):
    # 兼容 REST 触发
    if not payload.context_json:
        from main_controller import CONTEXT_JSON  # 注意：统一拼写
        payload.context_json = CONTEXT_JSON

    # 这里复用你原来的同步执行入口（若有）
    # 或者直接返回一个简要应答，引导用户使用 /ws/case 做实时交互
    return {
        "status": "accepted",
        "message": "Use WebSocket /ws/case for interactive run.",
    }


def nowz() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


class CaseRunner:
    """把计划生成、阶段1、阶段2串起来；WebSocket 事件在阶段函数里发。"""

    def __init__(self, ws: WebSocket, case: CaseInput, log_path: pathlib.Path):
        self.ws = ws
        self.case = case
        self._text_queue: asyncio.Queue[str] = asyncio.Queue()
        self.total_steps = 0
        self.step_idx = 0
        self._stopped = False
        self.plan: Dict[str, Any] = {}
        self.log_path = log_path

    async def push_text(self, text: str):
        await self._text_queue.put(text)

    async def wait_text(self, timeout: float = 300.0) -> str:
        return await asyncio.wait_for(self._text_queue.get(), timeout=timeout)

    async def run(self):
        # 构造上下文
        ctx = CaseRunnerCtx(
            ws=self.ws,
            client=None,  # 如果需要 LLM client，可在此构造；否则 main_controller 内部管理
            model=self.case.model,
            log_path=self.log_path,
            context_json=self.case.context_json,
            read_text=self.wait_text
        )

        # 1) 生成初始计划（可能耗时，用线程池）
        plan = await a_run_plan_chat(
            case_name=self.case.case_name or "",
            case_desc=self.case.case_desc,
            context_json=self.case.context_json,
            model=self.case.model,
            max_retries=self.case.max_retries,
        )

        # 2) 阶段1：确认/整体编辑
        plan = await stage1_show_and_confirm_ws(ctx, plan, PLAN_SCHEMA=None)

        # 保存到实例
        plan["type"] = 2
        self.plan = plan

        await ctx.log(f"最终执行计划: {json.dumps(plan, indent=2, ensure_ascii=False)}")

        # 3) 阶段2：逐步执行
        await stage2_stepwise_execute_ws(ctx, plan)


@router.websocket("/ws/case")
async def ws_case(websocket: WebSocket):
    await websocket.accept()

    runner: CaseRunner | None = None
    runner_task: asyncio.Task | None = None

    try:
        # 1) 逐步收参数
        await send_event(websocket, "ask", {"prompt": "请输入 case_name (可选，可直接回车跳过):"})
        case_name = (await websocket.receive_text()).strip() or ""

        case_desc = ""
        while not case_desc:
            await send_event(websocket, "ask", {"prompt": "请输入 case_desc (必填):"})
            case_desc = (await websocket.receive_text()).strip()
            if not case_desc:
                await send_event(websocket, "error", {"message": "case_desc 不能为空，请重新输入"})

        # 2) 组装 CaseInput
        from main_controller import CONTEXT_JSON  # 统一拼写
        case = CaseInput(
            case_name=case_name,
            case_desc=case_desc,
            context_json=CONTEXT_JSON,
            model="qwen3-235b-a22b-instruct-2507",
            max_retries=3,
        )

        # 3) 启动 Runner（可将日志打到固定目录）
        log_path = pathlib.Path("./logs/ws_case.log")
        runner = CaseRunner(websocket, case, log_path=log_path)
        runner_task = asyncio.create_task(runner.run())

        # 4) 后续用户的所有输入都推给 runner（自然语言）
        while True:
            msg = await websocket.receive()
            if "text" in msg:
                text = msg["text"].strip()
                if runner:
                    await runner.push_text(text)
            elif "bytes" in msg:
                # 如有二进制输入需求在此处理
                pass

    except WebSocketDisconnect:
        if runner_task and not runner_task.done():
            runner_task.cancel()