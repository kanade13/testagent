from fastapi import APIRouter, HTTPException, Query
import json
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from typing import Optional

from step import PLAN_SCHEMA

from jsonschema import validate, ValidationError
from app.state import EditRequest, PlanResponse, PlanResponseWithState, PlanStatus
from app.storage import load_plan, save_plan_and_bump, load_state, set_status, clear_all
from app.llm import generate_or_edit_full_plan, DEFAULT_MODEL, DEFAULT_MAX_RETRIES
import step
from step import client as llm_client, CONTEXT_JSON
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

@router.post("/plan_stream")
def create_or_edit_plan(payload: EditRequest):
    """
    统一入口（流式）：
    - 状态 EMPTY → 走“生成计划”提示词
    - 否则 → 走“编辑计划”提示词
    以 text/event-stream 流式返回模型输出的 JSON 文本；
    完成后解析/校验并保存，最后输出一个保存完成的事件。
    """
    state = load_state()
    current = load_plan()

    def event_stream():
        model = DEFAULT_MODEL
        max_retries = DEFAULT_MAX_RETRIES
        user_context = "【上下文JSON】\n" + CONTEXT_JSON
        attempt_err: Exception | None = None

        # 区分新建/编辑，准备 messages 与系统提示词
        if current is None:
            # 生成计划
            task = json.dumps({"case_name": "", "case_desc": payload.case_desc}, ensure_ascii=False)
            messages = [
                {"role": "system", "content": step.SYSTEM_PROMPT},
                {"role": "system", "content": "在不牺牲真实性的前提下，优先输出可迁移、可参数化、可复现的步骤。"},
                {"role": "user", "content": user_context},
                {"role": "user", "content": task},
            ]
            editor_mode = False
        else:
            # 编辑计划：拷贝编辑提示词（与 step.edit_plan_chat 一致）
            EDIT_SYSTEM_PROMPT = """
你是一名“测试计划修改器（Test Planner, Editor）”。
你的输入将包含三个部分：
【上下文JSON】：工具清单、示例用法、通用约束；
【当前计划】：一份“完整的现有计划（JSON）”；
 user_request中的 【修改需求】：用户希望对计划做出的变更（可能是参数修改、新增若干步骤、删除若干步骤、或三者的任意组合）。
你的任务：在严格遵循“上下文JSON”的事实与工具集合的前提下，基于当前计划执行最小必要修改，输出“完整的新计划（JSON）”。
严禁凭空发明上下文之外的工具或参数键名；严禁无故改写未涉及的步骤内容。
**如果【修改需求】user_request中没有任何修改需求或者用户表示对当前计划的肯定和进入执行阶段的需求(如"好","可以","执行吧","没问题","开始测试"),请将当前计划中的type字段直接改为2并返回计划.**
【编辑总原则｜Minimal-Diff】

只改需要改的：未被修改需求波及的步骤，其 action/tool/params/note 保持逐字不变。
参数修改优先：修改请求仅涉及参数时，尽量只改动对应步骤的 params 与 note 的必要部分，避免改写 action/tool。
新增/删除：
新增步骤时，选择最合理的插入位置（遵循 Setup → Run → Monitor/Log → Validate → Collect/Upload → Cleanup 的骨架），并保证 order 连续。即注意更改后续步骤的 order。

删除步骤时，仅删除被明确点名或确实冗余的步骤，随后重排 order 以保持从 1 连续。

顺序与稳定性：除非用户明确要求或为满足骨架/依赖关系确有必要，不要随意重排现有步骤顺序。

步数参考：当【上下文JSON】中存在与本 case 高相似度的条目，可参考其步骤数量与结构；但不得牺牲 minimal-diff 原则。



【输出格式（严格 JSON，UTF-8、无注释、无多余文本）】
{
  "case_name": string,
  "case_desc": string,
  "type": integer ∈ {1,2},
  "steps": [
    { "order": integer>=1, "action": string, "tool": string, "params": string, "note": string }
  ]
}

【字段要求】
- steps.type：1 表示计划阶段（当前不调用工具，供人在环确认/修改），2 表示已获确认、将实际调用工具。
默认全部填 1（规划阶段不直接下发执行）。
若 case_desc 明确要求“必须立即执行”的预检/清理，可标记为 2，并在 note 里说明依据。
- steps.order：从 1 开始连续递增，并与步骤排列顺序一致。
- action：一句话命令式描述，避免含糊（如“启动测试并设置时长 240min”）。
- tool：必须是**上下文JSON里列出的合法工具名**（若语义映射，请用被映射后的**上下文工具名**）。
- params：必须是**单一字符串**。严禁输出数组或对象。若需要多个参数，用空格连接；示例："--duration 240m --fullscreen true"。
若缺参请置为 "" 并在 note 说明“参数未在文档中给出”。
- note：请注意note应当被适度修改,写明与上下文的**对应关系/证据**（引用你依据的上下文条目标题或片段关键词），以及：
  - 如果使用的工具用到的参数不同于上下文条目中提到的工具参数的信息,请注意适度修改note参数.例如"Perf_3DMark_2cycles"改为"Perf_3DMark_5cycles"之后,"note": "对应上下文条目：测试3DMark_SpeedWay_2cycles"应修改为      "note": "对应上下文条目：测试3DMark_SpeedWay_5cycles"若做了合理默认/推断（例如把“时长=240min”对齐为工具支持的 `--duration 240m`），请说明“推断：…（可被覆盖）”
  - 若做了工具名映射，注明“映射：A->B，理由：…”
  - 若缺少参数，注明“参数未在文档中给出”

【抽象化与泛化准则】
1) **Setup → Run → Monitor/Log → Validate → Collect/Upload → Cleanup** 的通用骨架优先（缺项可省略）。
2) 尽量避免：
   - 仅靠界面像素坐标/截图匹配的步骤；
   - 机型/系统版本强绑定的措辞（若上下文确有此限制，需在 note 里标明“受限条件：…”）。
3) 若 case 要求的功能在上下文中被多个工具覆盖，选择**覆盖度最高且参数更稳定**的工具，并在 note 中简述取舍。
4) 失败/重试逻辑可凝练为“稳定用法”描述（例如“若返回码非 0，则重试 ≤3 次、间隔 30s”），但**不得发明**上下文中不存在的具体指令或参数名。

【当信息缺失时】
- 绝不编造工具或虚构参数字段名。
- 允许给出**占位**参数（""），并在 note 中写明“参数未在文档中给出，需由执行端补全”。
- 若 case_desc 中出现上下文未覆盖的具体名词（例如某子场景或测试项名称），
  只进行**语义对齐**到最接近的已知功能，不得发明新功能；在 note 说明“近似对齐项：…”。

【质量检查清单（自检，体现到最终输出，但不额外输出解释文本）】
- [✓] tool 均在上下文工具列表内（或已说明别名→正式名的映射）。
- [✓] params 仅使用上下文中存在/示例化的参数键；否则置空并在 note 标注缺参。
- [✓] 步骤顺序连续且不重复；动作语义原子、可复现。
- [✓] 有最少量但关键的校验/日志/上传步骤（若上下文提及）。
- [✓] 不出现与具体 UI 像素绑定的表述（除非上下文明确要求并给出方法）。

仅输出符合上述结构与规则的 JSON。
""".strip()
            messages = [
                {"role": "system", "content": EDIT_SYSTEM_PROMPT},
                {"role": "system", "content": "【当前计划为】\n" + json.dumps(current, ensure_ascii=False, indent=2)},
                {"role": "user", "content": user_context},
                {"role": "user", "content": "【修改需求】\n" + payload.case_desc},
            ]
            editor_mode = True

        # 流式调用 + 累积文本
        full_txt = ""
        think_full_txt = ""
        yield f"event: start\n\n"

        for attempt in range(1, max_retries + 1):
            try:
                with llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                    stream=True,
                ) as stream_obj:
                    for chunk in stream_obj:
                        try:
                            choice0 = chunk.choices[0]
                        except Exception:
                            continue
                        delta = getattr(choice0, "delta", None)
                        if delta is None:
                            continue
                        piece = getattr(delta, "content", None)
                        think_piece = getattr(delta, "reasoning_content", None)
                        if piece:
                            full_txt += piece
                            # 以 SSE 的 data 行输出片段
                            # yield f"data: {piece}\n\n"
                        if think_piece:
                            # thinking_buf.append(think_piece)
                            think_full_txt += think_piece
                             # 以 SSE 的 data 行输出片段
                            yield f"thinking: {think_piece}"
                attempt_err = None
                break
            except Exception as e:
                attempt_err = e
                # 向客户端报告重试，但不中断
                yield f"event: retry 第 {attempt}/{max_retries} 次失败：{str(e)}\n\n"
        if attempt_err is not None:
            # 全部失败
            yield f"event: error 重试后仍失败：{str(attempt_err)}\n\n"
            return

        # 尝试解析 JSON
        try:
            data = json.loads(full_txt)
        except Exception:
            yield f"event: error JSON解析失败：{str(e)}\n\n"
            return

        # 校验与修复
        try:
            validate_plan(data)
        except Exception as e:
            yield f"event: warn 计划校验警告/错误：{str(e)}\n\n"
        # 保存
        try:
            save_plan_and_bump(plan=data, status=PlanStatus.DRAFT, base_version=payload.base_version)
            yield "event: saved 计划已保存为DRAFT\n\n"
        except ValueError as e:
            yield f"event: error 保存失败（版本冲突）：{str(e)}\n\n"
            return
        # 输出最终结果
        if data:
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            # 输出thinking（如有）
            yield f"think: {think_full_txt}\n\n"
        yield "event: end\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
