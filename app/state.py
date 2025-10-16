from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional,Dict,Any
from datetime import datetime

class PlanStatus(str, Enum):
    EMPTY = "EMPTY"
    DRAFT = "DRAFT"
    ACCEPTED = "ACCEPTED"
    EXECUTING = "EXECUTING"
    DONE = "DONE"

class State(BaseModel):

    status: PlanStatus = PlanStatus.EMPTY
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class EditRequest(BaseModel):
    case_name:Optional[str]
    case_desc:str
    user_input: Optional[str]
    base_version: Optional[int] = None

class PlanResponse(BaseModel):
    plan: Dict[str, Any]
    thinking: Optional[str] = None

class PlanResponseWithState(BaseModel):
    # 可选地返回状态（调试/后端查看）
    plan: dict
    state: State
