from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from main_controller import CONTEXT_JSON
# ========== 请求模型 ==========
class CaseInput(BaseModel):
    case_name: str = Field(None, description="测试用例名称")
    case_desc: str = Field(..., description="测试用例描述")
    context_json: str = Field(CONTEXT_JSON, description="上下文 JSON 字符串")
    model: str = Field("qwen3-235b-a22b-instruct-2507", description="使用的模型")
    max_retries: int = Field(3, description="最大重试次数")
    context: Optional[Dict[str, Any]] = Field(None, description="可选上下文信息")

# ========== 响应模型 ==========
class ExecResult(BaseModel):
    ok: bool = Field(..., description="是否执行成功")
    data: Any = Field(None, description="返回的数据，可以是执行结果或中间输出")
    msg: str = Field("", description="错误信息或提示")
