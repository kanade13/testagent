import json
import os
import tempfile
import contextlib
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from app.state import State, PlanStatus

# 基础路径：仅保留 current_plan 与 state
BASE_DIR = Path(os.environ.get("PLAN_STORAGE_DIR", "plans")).resolve()
CURRENT_PLAN = BASE_DIR / "current_plan.json"
STATE_FILE = BASE_DIR / "state.json"

def _atomic_write_json(path: Path, data: Any):
    """
    原子写入，避免半写坏文件。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(Exception):
            os.remove(tmp_path)
        raise

def load_state() -> State:
    if not STATE_FILE.exists():
        return State()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return State(**data)
    except Exception:
        # 状态损坏则重置为空
        return State()

def save_state(state: State):
    _atomic_write_json(STATE_FILE, json.loads(state.model_dump_json()))

def load_plan() -> Optional[dict]:
    if not CURRENT_PLAN.exists():
        return None
    try:
        return json.loads(CURRENT_PLAN.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_plan_and_bump(plan: dict, status: Optional[PlanStatus] = None, base_version: Optional[int] = None) -> State:
    """
    写入当前 plan，并更新状态与时间戳。
    """
    _atomic_write_json(CURRENT_PLAN, plan)

    state = load_state()
    if status is not None:
        state.status = status
    state.updated_at = datetime.utcnow()
    save_state(state)
    return state

def set_status(new_status: PlanStatus) -> State:
    state = load_state()
    state.status = new_status
    state.updated_at = datetime.utcnow()
    save_state(state)
    return state

def clear_all():
    """
    清空当前计划与状态：回到 EMPTY
    """
    with contextlib.suppress(FileNotFoundError):
        CURRENT_PLAN.unlink()
    with contextlib.suppress(FileNotFoundError):
        STATE_FILE.unlink()
    save_state(State())
