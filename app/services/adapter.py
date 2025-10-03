from typing import Dict, Any, Optional
import main_controller   
from main_controller import CONTEXT_JSON
def run_plan(
    case_desc: str,
    context_json: str=CONTEXT_JSON,
    model: str = "qwen3-235b-a22b-instruct-2507",
    max_retries: int = 3,
    context: Optional[Dict[str, Any]] = None,
    case_name: str=None
) -> Dict[str, Any]:
    """
    适配 API 调用到 main_controler.run_test_case
    返回一个 dict，方便 API 统一返回 JSON
    """
    try:
        result = main_controller.run_test_case(
            case_name=case_name,
            case_desc=case_desc,
            context_json=context_json,
            model=model,
            max_retries=max_retries,
            context=context
        )
        return {"ok": True, "data": result}
    except Exception as e:
        return {"ok": False, "msg": str(e)}
