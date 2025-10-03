# runner.py
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

from utils import json_pretty, now_ts, extract_first_json_blob, check_json_format,validate_plan,write_log

CTX_PATH = pathlib.Path("./context.json")
CONTEXT_JSON = load_context_json(CTX_PATH)
# ----------- Command Parser Agent -----------
# 解析人类自然语言指令为结构化命令
CMD_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["confirm", "edit", "skip", "goto", "stop", "ask"]},
        "target_step": {"type": "integer", "minimum": 0},
        "edits": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "tool": {"type": "string"},
                "params": {"type": "string"},
                "note": {"type": "string"}
            }
        },
        "message": {"type": "string"}
    },
    "required": ["op"]
}

def parse_command_with_llm(client: OpenAI, model: str, user_text: str, plan: Dict[str, Any], current_step: int,context_json:str) -> Dict[str, Any]:
    """
    使用 LLM 将自然语言 user_text 解析为结构化命令，遵循 CMD_SCHEMA。
    """
    SYSTEM_PROMPT = (
        """你是一个命令解析器，将用户的自然语言转换为严格的 JSON 命令，用于控制测试计划执行器。仅输出一个符合 CMD_SCHEMA 的单一 JSON 对象
        接下来是你需要了解的上下文信息：
        """
    )
    if context_json:
        SYSTEM_PROMPT += f"\n当前可用的上下文信息：\n{context_json}\n"
    USER_PROMPT = f"""
用户输入（自然语言）：
{user_text}

当前步骤序号（1-based）：{current_step}

计划概要（供理解，不必复述）：
case_name: {plan.get('case_name')}
steps_count: {len(plan.get('steps', []))}

请只输出一个 JSON，字段含义：
- op:  ["confirm", "edit", "skip", "goto", "stop", "ask"]的其中一个
- target_step: integer, 当用户想跳转,编辑指定步骤或者询问指定步骤时需要,当用户询问或操作整个case时取值0

- edits: 当 op="edit" 时可能包含的字段 {{action|tool|params|note}}.
请注意理解用户的意思,对于 "params" 字段，必须保持为 **工具实际参数字符串**（例如 "/S 3" → "/S 2"），不要翻译成自然语言。不要增加解释性文字，只能直接修改对应的命令参数。
如果用户输入模糊，不能确定确切参数值，请保留原值，并在 "message" 中说明问题。
当 op="edit" 且用户修改了 action（包括更换场景/benchmark 名称）时：
1) 你**必须**同时给出与该 action 匹配的完整 edits，至少包含 {{action, tool, params, note}} 四个字段；
2) 如果信息不足以确定 tool/params/note，请不要返回不完整的 edits；改为输出 {{"op":"ask","message":"需要提供X（例如场景文件/Job名称等）"}}；
3) **禁止**只返回 {{action}} 这种不完整更新。
- message: 当 op="ask" 时，用于转述/澄清用户问题；或当其他操作需要携带说明时
- action：一句话命令式描述，避免含糊（如“启动测试并设置时长 240min”）。
- tool：必须是**上下文JSON里列出的合法工具名**（若语义映射，请用被映射后的**上下文工具名**）。
- params：必须是**单一字符串**。严禁输出数组或对象。若需要多个参数，用空格连接；示例："--duration 240m --fullscreen true"。
若缺参请置为 "" 并在 note 说明“参数未在文档中给出”。
- note：请注意note应当被适度修改,写明与上下文的**对应关系/证据**（引用你依据的上下文条目标题或片段关键词），以及：
  - 如果使用的工具用到的参数不同于上下文条目中提到的工具参数的信息,请注意适度修改note参数.例如"Perf_3DMark_2cycles"改为"Perf_3DMark_5cycles"之后,"note": "对应上下文条目：测试3DMark_SpeedWay_2cycles"应修改为      "note": "对应上下文条目：测试3DMark_SpeedWay_5cycles"若做了合理默认/推断（例如把“时长=240min”对齐为工具支持的 `--duration 240m`），请说明“推断：…（可被覆盖）”
  - 若做了工具名映射，注明“映射：A->B，理由：…”
  - 若缺少参数，注明“参数未在文档中给出”
示例：
{{"op":"confirm"}}
{{"op":"skip"}}
{{"op":"goto","target_step":3}}
{{"op":"edit","target_step":2,"edits":{{"params":"--brightness 60"}}}}
{{"op":"ask","target_step":5,"message":"为何第五步要设置亮度为88？"}}
{{"op":"ask","target_step":0,"message":"为什么要这样安排步骤?"}}


严格输出 JSON，不要多余文本。
"""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        temperature=0
    )
    txt = resp.choices[0].message.content
    cmd = extract_first_json_blob(txt) 

    if not check_json_format(cmd, CMD_SCHEMA):
        print(f"[警告] LLM 输出的 JSON 不符合 CMD_SCHEMA，原始输出：{txt}")
        cmd = {"op": "ask", "message": "无法解析，请重说一遍"}
    print(f"解析结果：{json.dumps(cmd, ensure_ascii=False)}")
    return cmd

# ----------- 问答 Agent（当用户 ask 时）-----------
def answer_user_question(
    client: OpenAI,
    model: str,
    question: str,
    plan: Dict[str, Any],
    context_json:str,
    target_step: Optional[int]  # 这里的 target_step 约定为“步骤号(order)”，而非列表索引
) -> str:
    SYSTEM_PROMPT = "你是一个经验丰富的测试助手，请耐心且详细地回答问题,包括解释计划和计划的依据等。你需要基于提供的测试计划和上下文信息来回答。"
    if context_json:
        SYSTEM_PROMPT += f"\n当前可用的上下文信息：\n{context_json}\n"

    # 基础上下文
    USER_PROMPT = (
        "请直接回答问题，若涉及参数意义或修改建议，请给出明确理由和可选值。\n"
        f"用户问题：{question}\n\n"
        "参考上下文：\n"
        f"- Case：{plan.get('case_name')}\n"
        f"- Desc：{plan.get('case_desc')}\n"
    )

    # 若提供了目标步骤号，则追加该步骤的详细信息
    if target_step is not None:
        # 按 order 查找该步骤（推荐做法）
        idx = _find_step_index_by_order(plan, target_step)
        if idx is not None:
            step_obj = plan["steps"][idx]
            USER_PROMPT += "- 询问目标步骤（按 order 匹配）：\n"
            USER_PROMPT += json.dumps(step_obj, ensure_ascii=False, indent=2) + "\n"
        else:
            USER_PROMPT += f"- 询问目标步骤：未找到 order={target_step} 的步骤\n"

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

# ----------- 执行占位 -----------------------------
def execute_step(step_obj: Dict[str, Any]) -> bool:
    print("\n[执行中] ↓↓↓")
    print(json_pretty(step_obj))
    # TODO: 在这里对接真实工具链 / 命令执行
    # 返回 True 代表成功，False 代表失败（可扩展重试逻辑）
    time.sleep(0.5)
    print("[完成]\n")
    return True

# ----------- 阶段1：原样输出计划并等待确认/修改 -----------
def stage1_show_and_confirm(client: OpenAI, model: str, plan: Dict[str, Any],log_path:pathlib.Path,context_json:str) -> Dict[str, Any]:
    print("\n===== 阶段1：原样输出测试执行计划（等待确认/修改） =====")
    print(json_pretty(plan))
    print("\n请输入指令：\n"
          " - 直接回车：视为 confirm\n"
          " - 自然语言说明：例如“第2步把亮度改成60再说”、“跳到第3步看看”、“先别执行，我有问题：XXX”\n"
          " - 关键词也行：confirm/skip/goto/edit/stop/ask\n")

    while True:
        user_text = input("你的指令（阶段1）：").strip()
        write_log(log_path, "USER_INPUT_STAGE1", user_text if user_text else "<confirm>")
        if user_text == "":
            return plan  # 视为确认

        cmd = parse_command_with_llm(client, model, user_text, plan,current_step=1,context_json=context_json)
        op = cmd["op"]

        if op == "confirm":
            return plan

        elif op == "stop":
            raise KeyboardInterrupt("用户停止执行。")

        elif op == "ask":
            # 可能带有 target_step（按步骤号），也可能没有
            t = cmd.get("target_step")  # None 或 int
            ans = answer_user_question(
                client=client,
                model=model,
                question=cmd.get("message", ""),
                plan=plan,
                context_json=context_json,
                target_step=t
            )
            print(f"[答复] {ans}")

        elif op == "edit":
            t = cmd.get("target_step", 0)
            edits = cmd.get("edits", {})
            # 简化：阶段1允许编辑任意步骤（按 order 定位）
            idx = _find_step_index_by_order(plan, t)
            if idx is None:
                print(f"[警告] 未找到步骤 {t}")
                continue
            plan["steps"][idx].update({k: v for k, v in edits.items() if v is not None})
            ok, err = validate_plan(plan,PLAN_SCHEMA)
            if not ok:
                print(f"[校验失败] {err}")
            else:
                print("[已修改并通过校验]")
                print(json_pretty(plan["steps"][idx]))

        elif op in ("skip", "goto"):
            print("[提示] 阶段1仅用于确认/总体编辑，不进行逐步控制。若要跳过/跳转，请进入阶段2后处理。")

        else:
            print("[提示] 请输入更明确的意图（confirm/edit/ask/stop）。")


def _find_step_index_by_order(plan: Dict[str, Any], order: int) -> Optional[int]:
    for i, s in enumerate(plan.get("steps", [])):
        if s.get("order") == order:
            return i
    return None

# ----------- 阶段2：逐步执行（每步前等待确认/可编辑/跳过/跳转/问答/停止）-----------
def stage2_stepwise_execute(client: OpenAI, model: str, plan: Dict[str, Any],log_path:pathlib.Path,context_json:str) -> None:
    print("\n===== 阶段2：逐步执行 =====")
    # 确保 steps 按 order 升序
    plan["steps"].sort(key=lambda x: x["order"])
    i = 0
    n = len(plan["steps"])

    while 0 <= i < n:
        step = plan["steps"][i]
        order = step["order"]

        print("\n--- 即将执行的步骤 ---")
        print(json_pretty(step))
        print("\n请输入指令（回车=confirm）")

        user_text = input(f"你的指令（当前步骤{order}）：").strip()
        write_log(log_path, f"USER_INPUT_STEP{order}", user_text if user_text else "<confirm>")
        if user_text == "":
            # 直接确认执行
            ok = execute_step(step)
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"success={ok}")
            if not ok:
                print("[失败] 执行失败")
                write_log(log_path, f"EXEC_RESULT_STEP{order}", f"success={ok}")
                continue
            i += 1
            continue

        # 解析自然语言为命令
        cmd = parse_command_with_llm(client, model, user_text, plan, current_step=order,context_json=context_json)
        op = cmd["op"]

        if op == "confirm":
            ok = execute_step(step)
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"success={ok}")
            if ok:
                i += 1
            continue

        if op == "stop":
            print("[已停止] 用户要求终止")
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户暂停")
            return

        if op == "skip":
            print(f"[跳过] 步骤 {order}")
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户跳过")
            i += 1
            continue

        if op == "goto":
            t = cmd.get("target_step")
            if not isinstance(t, int):
                print("[提示] 请提供要跳转的目标步骤号 target_step")
                write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户跳转失败，未提供目标步骤号")
                continue
            idx = _find_step_index_by_order(plan, t)
            if idx is None:
                print(f"[警告] 未找到步骤 {t}")
                write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户跳转失败，未找到步骤 {t}")
                continue
            i = idx
            print(f"[跳转] 到步骤 {t}")
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户跳转到 {t}")
            continue

        if op == "ask":
            q = cmd.get("message", "")
            ans = answer_user_question(client, model, q, plan, step, context_json=context_json)
            print(f"[答复] {ans}")
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户询问：{q}\n答复：{ans}")
            continue

        if op == "edit":
            t = cmd.get("target_step", order)
            idx = _find_step_index_by_order(plan, t)
            if idx is None:
                print(f"[警告] 未找到步骤 {t}")
                write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户编辑失败，未找到步骤 {t}")
                continue
            edits = cmd.get("edits", {})
            before = deepcopy(plan["steps"][idx])
            plan["steps"][idx].update({k: v for k, v in edits.items() if v is not None})
            ok, err = validate_plan(plan)
            if not ok:
                print(f"[校验失败] {err}\n[回滚] 还原修改。")
                write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户编辑步骤 {t} 失败，错误：{err}")
                plan["steps"][idx] = before
                continue
            # 保存修改后的计划（带时间戳）
            #_backup_and_save(plan, save_path)
            #print("[已修改并保存] 当前步骤内容：")
            #print(json_pretty(plan["steps"][idx]))
            # 修改后一般仍停留在同一步，等待用户再次确认或继续
            write_log(log_path, f"EXEC_RESULT_STEP{order}", f"用户编辑步骤 {t}，修改内容：{json.dumps(edits, ensure_ascii=False)}")
            continue

    print("\n===== 阶段2结束：已到达计划末尾 =====")
    
def _backup_and_save(plan: Dict[str, Any], save_path: pathlib.Path) -> None:
    if save_path.exists():
        backup = save_path.with_name(save_path.stem + f".bak.{now_ts()}" + save_path.suffix)
        backup.write_text(save_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[备份] 已备份到 {backup.name}")
    save_plan_to_json(plan, save_path)
    print(f"[保存] 已写回 {save_path.name}")

# ----------- 总控入口 -----------
def run_test_case(
    case_name: str,
    case_desc: str,
    context_json:str,
    model: str = "qwen3-235b-a22b-instruct-2507",
    max_retries: int = 3,
    context: Optional[Dict[str, Any]] = None) -> None:
    #我服了我怎么定义了两个context
    client = OpenAI()
    # 上下文
    context = context or load_context_json()
    context_json_str = json.dumps(context, ensure_ascii=False)

    #日志文件
    if case_name == "":
        case_name = f"case"
    log_path = pathlib.Path(f"{case_name}_{now_ts()}_log.txt")
    #print(165)
    # 1) 生成计划
    plan = run_plan_chat(
        case_name=case_name,
        case_desc=case_desc,
        context_json=context_json_str,
        model=model,
        max_retries=max_retries
    )
    #print(165)
    # 2) 校验 & 保存
    ok, err = validate_plan(plan,PLAN_SCHEMA)
    if not ok:
        print("[错误] 生成的计划不符合 SCHEMA：")
        print(err)
        return

    write_log(log_path, "INIT_PLAN", json_pretty(plan))

    # 3) 阶段1：展示计划并等待确认/编辑
    plan = stage1_show_and_confirm(client, model, plan,log_path,context_json=context_json_str)
    #_backup_and_save(plan, save_path)
    #将type改为2
    plan["type"]=2
    write_log(log_path, "EDITED_PLAN_AFTERSTAGE1", json_pretty(plan))
    print("\n[信息] 进入阶段2：逐步执行")


    # 4) 阶段2：逐步执行
    stage2_stepwise_execute(client, model, plan, log_path,context_json=context_json_str)

# ---- 直接运行示例 ----
if __name__ == "__main__":
    CTX_PATH = pathlib.Path("./context.json")
    context_json = load_context_json(CTX_PATH)
    run_test_case(
        case_name="",
        case_desc="利用BatteryCapacityDetectControl工具记录电脑通过播放本地视频将电池电量从100%放电到10%所用的总时间并上传到测试平台",
        context_json=context_json,
        model="qwen3-235b-a22b-instruct-2507"
    )
#qwen-plus