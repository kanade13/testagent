import os 
import json
import time
import pathlib
from typing import Dict, Any, List

from openai import OpenAI
from jsonschema import validate, ValidationError
from dotenv import load_dotenv


env_path = pathlib.Path(__file__).parent / ".env"
#print("加载路径:", env_path)
load_dotenv(dotenv_path=env_path)

#print("API_KEY=", os.getenv("OPENAI_API_KEY"))


client = OpenAI()  # 默认从环境变量读取 key / base_url

CTX_PATH = pathlib.Path("./context.json")

# 是否自动修复 steps.order 连续性
AUTO_FIX_ORDER = True

SYSTEM_PROMPT = """
你是一名“测试执行规划器（Test Planner）”。你只能依据“上下文JSON”中的**事实**来规划步骤，
但你应尽量让步骤具备**可迁移性与泛化性**。禁止编造上下文之外**不存在**的工具或参数值。
另外,当你找到可能有关联的上下文时,注意查看其步骤数目,因为**很可能**该上下文是针对类似case的规划,你可以参考其步骤数目来规划你的步骤数目.
【角色与目标】
- 你的任务是把一个“Case（case_name, case_desc）”转换为一组**可执行、可迁移**的步骤（steps）。
- 当 case 的描述与上下文中的示例不完全一致时，应进行**语义对齐**与**抽象化**：
  - 只在上下文里选择**已存在**的工具；若 case 使用了工具别名或近义说法，请**映射到**上下文中最相近的工具，
    并在 `note` 中写明“映射：<原称呼> -> <上下文工具名>”，同时写明选择理由（1 句话）。
  - 动作尽量写成**环境无关**与**可参数化**的形式（优先 CLI/脚本/配置项，而不是像素坐标或机型特定按钮）。
  - 当存在多种可行方案时，**优先选择鲁棒方案**（无 UI、可重试、可校验）。

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
# ===================== 新的 System Prompt 结束 =====================

# JSON Schema：用于程序端严格校验（保持不变）
PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_name": {"type": "string"},
        "case_desc": {"type": "string"},
        "type": {"type": "integer", "enum": [1, 2]},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer", "minimum": 1},
                    "action": {"type": "string"},
                    "tool": {"type": "string"},
                    "params": {"type": "string"},
                    "note": {"type": "string"}
                },
                "required": ["order", "action", "tool", "params", "note"]
            },
            "minItems": 1
        }
    },
    "required": ["case_name", "case_desc", "steps"]
}

def load_context_json(path: pathlib.Path=pathlib.Path("./context.json")) -> str:
    if not path.exists():
        raise FileNotFoundError(f"未找到上下文文件：{path}")
    return path.read_text(encoding="utf-8")

def check_order_continuity(steps: List[Dict[str, Any]]) -> bool:
    orders = [s.get("order") for s in steps]
    return orders == list(range(1, len(orders) + 1))

def fix_orders_inplace(steps: List[Dict[str, Any]]) -> None:
    for idx, step in enumerate(steps, start=1):
        step["order"] = idx

def run_plan_chat(case_name: str,
                  case_desc: str,
                  context_json: str,
                  model: str = "qwen-max",
                  max_retries: int = 3) -> Dict[str, Any]:
    
    print(f"🤖 调用LLM生成测试计划...")
    print(f"   - 模型: {model}")
    print(f"   - 端点: {client.base_url}")

    user_context = "【上下文JSON】\n" + context_json
    task = json.dumps({"cmd": case_name, "cmd_desc": case_desc}, ensure_ascii=False)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "在不牺牲真实性的前提下，优先输出可迁移、可参数化、可复现的步骤。"},
        {"role": "user", "content": user_context},
        {"role": "user", "content": task}
    ]

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,   # ★略升温以提升泛化
                #top_p=0.9          # ★配合采样，仍受系统约束
            )
            txt = resp.choices[0].message.content  
            data = json.loads(txt)
            print(f"模型输出：{json.dumps(data, ensure_ascii=False, indent=2)}")
            validate(instance=data, schema=PLAN_SCHEMA)

            if not check_order_continuity(data["steps"]):
                if AUTO_FIX_ORDER:
                    data["steps"].sort(
                        key=lambda s: (s.get("order")
                                       if isinstance(s.get("order"), int)
                                       else 10**9)
                    )
                    fix_orders_inplace(data["steps"])
                else:
                    raise ValidationError(
                        f"order 不连续: {[s['order'] for s in data['steps']]}")
            return data

        except Exception as e:
            last_err = e
            print(f"❌ 第 {attempt}/{max_retries} 次失败：{e}")
            time.sleep(1)

    raise RuntimeError(f"重试后仍失败：{last_err}")

def save_plan_to_json(plan: Dict[str, Any], path: pathlib.Path) -> None:
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    context_json_str = load_context_json(CTX_PATH)
    case_name = "Batterylife_Jeita_VPBTest_100_to_3"
    case_desc = """利用BatteryCapacityDetectControl工具记录电脑通过播放本地视频将电池电量从100%放电到10%所用的总时间并上传到测试平台"""
    result = run_plan_chat(
        case_name=case_name,
        case_desc=case_desc,
        context_json=context_json_str,
        model="qwen-plus",
        max_retries=3
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
