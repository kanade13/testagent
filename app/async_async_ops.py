# async_async_ops.py
import asyncio
import json
import datetime
import pathlib
from typing import Any, Dict, Optional

from fastapi import WebSocket

import main_controller

from utils import (
    validate_plan,
    write_log,
)
def nowz() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


# 统一的 Server→Client 事件发送
async def send_event(ws: WebSocket, typ: str, data: dict):
    await ws.send_json({"type": typ, "ts": nowz(), "data": data})


class CaseRunnerCtx:
    """在阶段函数间传递上下文"""
    def __init__(self, ws: WebSocket, client, model: str, log_path: pathlib.Path, context_json: str):
        self.ws = ws
        self.client = client
        self.model = model
        self.log_path = log_path
        self.context_json = context_json
        self.read_text = read_text  # <- 新增

    async def log(self, msg: str, level="info"):
        await send_event(self.ws, "log", {"message": msg, "level": level})


# ========== 异步包装器（线程池） ==========
async def a_run_plan_chat(case_name, case_desc, context_json, model, max_retries):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: main_controller.run_plan_chat(
            case_name=case_name, case_desc=case_desc,
            context_json=context_json, model=model, max_retries=max_retries
        )
    )

async def a_parse_command_with_llm(client, model, user_text, plan, context_json, current_step: Optional[int] = None):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: parse_command_with_llm(
            client=client, model=model, user_text=user_text,
            plan=plan, context_json=context_json, current_step=current_step
        )
    )

async def a_validate_plan(plan: Dict[str, Any], schema=None):
    loop = asyncio.get_running_loop()
    if schema is None:
        return await loop.run_in_executor(None, lambda: validate_plan(plan))
    return await loop.run_in_executor(None, lambda: validate_plan(plan, schema))

async def a_execute_step(step: Dict[str, Any]) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: execute_step(step))

async def a_answer_user_question(client, model, question, plan, context_json, target_step=None):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: answer_user_question(
            client=client, model=model, question=question,
            plan=plan, context_json=context_json, target_step=target_step
        )
    )

async def a_write_log(log_path: pathlib.Path, tag: str, text: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: write_log(log_path, tag, text))


# ========== 阶段1 ==========
def _find_step_index_by_order(plan: Dict[str, Any], order: int) -> Optional[int]:
    for i, s in enumerate(plan.get("steps", [])):
        if s.get("order") == order:
            return i
    return None

async def stage1_show_and_confirm_ws(ctx: CaseRunnerCtx, plan: Dict[str, Any], PLAN_SCHEMA=None) -> Dict[str, Any]:
    await ctx.log("===== 阶段1：原样输出测试执行计划（等待确认/修改） =====")
    await send_event(ctx.ws, "step", {"step": 0, "action": "ShowPlan", "tool": "planner", "params": {"preview": True}})
    await send_event(ctx.ws, "plan", {"preview": plan})

    async def prompt_again():
        await send_event(ctx.ws, "ask", {
            "prompt": "请输入指令（回车=confirm）。示例：确认/停止/第2步把亮度改成60/跳到第3步/我有问题：XXX"
        })

    await prompt_again()
    await ctx.log(f"11111111111111111111111111111111111111111")
    while True:
        # 建议加超时防“真空等待”
        try:
            user_text = (await asyncio.wait_for(ctx.read_text(), timeout=300)).strip()
            await ctx.log(f"2222222222222222222222222222222222222222")
        except asyncio.TimeoutError:
            await ctx.log(f"33333333333333333333333333333333333333333")
            await ctx.log("等待输入超时，仍在监听。你可以继续输入。", "warn")
            await prompt_again()
            continue
        await ctx.log(f"[用户输入1] {user_text}")
        await a_write_log(ctx.log_path, "USER_INPUT_STAGE1", user_text if user_text else "<confirm>")

        if user_text == "":
            return plan
        await ctx.log(f"[用户输入2] {user_text}")
        cmd = await a_parse_command_with_llm(
            client=ctx.client, model=ctx.model,
            user_text=user_text, plan=plan, context_json=ctx.context_json
        )
        #显示给用户看
        await send_event(ctx.ws, "parsed_command", {"step": order, "command": cmd})
        op = cmd.get("op")

        if op == "confirm":
            return plan

        elif op == "stop":
            await ctx.log("用户停止执行。", "warn")
            raise KeyboardInterrupt("用户停止执行。")

        elif op == "ask":
            t = cmd.get("target_step")
            ans = await a_answer_user_question(
                client=ctx.client, model=ctx.model,
                question=cmd.get("message", ""), plan=plan,
                context_json=ctx.context_json, target_step=t
            )
            await ctx.log(f"[答复] {ans}")
            await send_event(ctx.ws, "qa", {"question": cmd.get("message", ""), "answer": ans})
            await prompt_again()
            continue

        elif op == "edit":
            t = cmd.get("target_step", 0)
            idx = _find_step_index_by_order(plan, t)
            if idx is None:
                warn = f"[警告] 未找到步骤 {t}"
                await ctx.log(warn, "warn")
                await send_event(ctx.ws, "error", {"message": warn})
                await prompt_again()
                continue

            edits = cmd.get("edits", {})
            plan["steps"][idx].update({k: v for k, v in edits.items() if v is not None})
            ok, err = await a_validate_plan(plan, PLAN_SCHEMA)
            if not ok:
                await ctx.log(f"[校验失败] {err}", "error")
                await send_event(ctx.ws, "error", {"message": str(err)})
            else:
                await ctx.log("[已修改并通过校验]")
                await send_event(ctx.ws, "plan_step", {"step": t, "content": plan["steps"][idx]})
            await prompt_again()
            continue

        elif op in ("skip", "goto"):
            tip = "[提示] 阶段1仅用于确认/总体编辑，不进行逐步控制。若要跳过/跳转，请在阶段2处理。"
            await ctx.log(tip)
            await send_event(ctx.ws, "status", {"phase": "stage1", "note": tip})
            await prompt_again()
            continue

        else:
            await ctx.log("[提示] 请输入更明确的意图（confirm/edit/ask/stop）。")
            await prompt_again()
            continue



# ========== 阶段2 ==========
async def stage2_stepwise_execute_ws(
    ctx: CaseRunnerCtx,
    plan: Dict[str, Any]
) -> None:
    await ctx.log("===== 阶段2：逐步执行 =====")
    plan["steps"].sort(key=lambda x: x["order"])
    i = 0
    n = len(plan["steps"])

    while 0 <= i < n:
        step = plan["steps"][i]
        order = step["order"]

        await send_event(ctx.ws, "step", {
            "step": order, "action": step.get("action"),
            "tool": step.get("tool"), "params": step.get("params", {})
        })
        await ctx.log("即将执行的步骤预览：")
        await send_event(ctx.ws, "plan_step", {"step": order, "content": step})

        await send_event(ctx.ws, "ask", {"prompt": f"请输入指令（回车=confirm），当前步骤 {order}："})

        user_text = (await ctx.ws.receive_text()).strip()
        await a_write_log(ctx.log_path, f"USER_INPUT_STEP{order}", user_text if user_text else "<confirm>")

        if user_text == "":
            ok = await a_execute_step(step)
            await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"success={ok}")
            if not ok:
                await ctx.log("[失败] 执行失败", "error")
                await send_event(ctx.ws, "error", {"message": f"步骤 {order} 执行失败"})
                continue
            i += 1
            continue

        cmd = await a_parse_command_with_llm(
            client=ctx.client, model=ctx.model, user_text=user_text,
            plan=plan, current_step=order, context_json=ctx.context_json
        )

        op = cmd.get("op")

        if op == "confirm":
            ok = await a_execute_step(step)
            await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"success={ok}")
            if ok:
                i += 1
            else:
                await send_event(ctx.ws, "error", {"message": f"步骤 {order} 执行失败"})
            continue

        if op == "stop":
            await ctx.log("[已停止] 用户要求终止", "warn")
            await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", "用户暂停")
            return

        if op == "skip":
            await ctx.log(f"[跳过] 步骤 {order}")
            await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", "用户跳过")
            i += 1
            continue

        if op == "goto":
            t = cmd.get("target_step")
            if not isinstance(t, int):
                tip = "[提示] 请提供要跳转的目标步骤号 target_step"
                await ctx.log(tip)
                await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", "用户跳转失败，未提供目标步骤号")
                continue
            idx = _find_step_index_by_order(plan, t)
            if idx is None:
                warn = f"[警告] 未找到步骤 {t}"
                await ctx.log(warn, "warn")
                await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"用户跳转失败，未找到步骤 {t}")
                continue
            i = idx
            await ctx.log(f"[跳转] 到步骤 {t}")
            await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"用户跳转到 {t}")
            continue

        if op == "ask":
            q = cmd.get("message", "")
            ans = await a_answer_user_question(
                client=ctx.client, model=ctx.model, question=q,
                plan=plan, context_json=ctx.context_json, target_step=order
            )
            await ctx.log(f"[答复] {ans}")
            await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"用户询问：{q}\n答复：{ans}")
            await send_event(ctx.ws, "qa", {"question": q, "answer": ans})
            continue

        if op == "edit":
            t = cmd.get("target_step", order)
            idx = _find_step_index_by_order(plan, t)
            if idx is None:
                warn = f"[警告] 未找到步骤 {t}"
                await ctx.log(warn, "warn")
                await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"用户编辑失败，未找到步骤 {t}")
                continue

            edits = cmd.get("edits", {})
            before = json.loads(json.dumps(plan["steps"][idx], ensure_ascii=False))  # 深拷贝
            plan["steps"][idx].update({k: v for k, v in edits.items() if v is not None})

            ok, err = await a_validate_plan(plan)
            if not ok:
                await ctx.log(f"[校验失败] {err}\n[回滚] 还原修改。", "error")
                await a_write_log(ctx.log_path, f"EXEC_RESULT_STEP{order}", f"用户编辑步骤 {t} 失败，错误：{err}")
                plan["steps"][idx] = before
                continue

            await a_write_log(
                ctx.log_path, f"EXEC_RESULT_STEP{order}",
                f"用户编辑步骤 {t}，修改内容：{json.dumps(edits, ensure_ascii=False)}"
            )
            await send_event(ctx.ws, "plan_step", {"step": t, "content": plan["steps"][idx]})
            continue

        await ctx.log("[提示] 请输入更明确的意图（confirm/skip/goto/edit/stop/ask）。")
