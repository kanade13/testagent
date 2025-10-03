from __future__ import annotations
from typing import Any, Optional, List, Dict
from fastapi import WebSocket
import asyncio

class NeedUserInput(Exception):
    def __init__(self, question: str, key: str, choices: Optional[List[str]] = None, default: Any = None):
        self.question = question
        self.key = key
        self.choices = choices
        self.default = default
        super().__init__(question)

class AsyncPromptIO:
    async def ask(self, question: str, key: str, *, choices: Optional[List[str]] = None, default: Any = None) -> Any:
        raise NotImplementedError

    async def confirm(self, question: str, key: str, default: bool = False) -> bool:
        raise NotImplementedError

    async def notify(self, message: str) -> None:
        pass

class WebSocketPromptIO(AsyncPromptIO):
    """
    与前端通过 WebSocket 以 JSON 消息交互。
    协议：
      服务端 -> 客户端:
        {"type":"ask","key":..., "question":..., "choices":[...]|null, "default":...}
        {"type":"confirm","key":..., "question":..., "default":true|false}
        {"type":"notify","message":...}
        {"type":"progress","stage":..., "detail":...}
        {"type":"finished","ok":true,"data":...} 或 {"type":"error","message":...}

      客户端 -> 服务端:
        {"type":"answer","key":..., "value":...}
        {"type":"abort"}   # 可选，用户主动中断
    """
    def __init__(self, ws: WebSocket, timeout_sec: Optional[float] = None):
        self.ws = ws
        self.timeout = timeout_sec

    async def _send_json(self, payload: Dict[str, Any]) -> None:
        await self.ws.send_json(payload)

    async def _recv_json(self) -> Dict[str, Any]:
        if self.timeout:
            return await asyncio.wait_for(self.ws.receive_json(), timeout=self.timeout)
        return await self.ws.receive_json()

    async def ask(self, question: str, key: str, *, choices: Optional[List[str]] = None, default: Any = None) -> Any:
        await self._send_json({"type": "ask", "key": key, "question": question, "choices": choices, "default": default})
        msg = await self._recv_json()
        if msg.get("type") == "abort":
            raise asyncio.CancelledError("User aborted.")
        if msg.get("type") != "answer" or msg.get("key") != key:
            raise ValueError(f"Unexpected message: {msg}")
        return msg.get("value", default)

    async def confirm(self, question: str, key: str, default: bool = False) -> bool:
        await self._send_json({"type": "confirm", "key": key, "question": question, "default": default})
        msg = await self._recv_json()
        if msg.get("type") == "abort":
            raise asyncio.CancelledError("User aborted.")
        if msg.get("type") != "answer" or msg.get("key") != key:
            raise ValueError(f"Unexpected message: {msg}")
        v = str(msg.get("value", default)).lower()
        return v in {"y", "yes", "true", "1"}

    async def notify(self, message: str) -> None:
        await self._send_json({"type": "notify", "message": message})

    # 可选：对外暴露一个进度接口
    async def progress(self, stage: str, detail: Any = None) -> None:
        await self._send_json({"type": "progress", "stage": stage, "detail": detail})

    async def finished(self, ok: bool, data: Any = None, message: str = "") -> None:
        if ok:
            await self._send_json({"type": "finished", "ok": True, "data": data})
        else:
            await self._send_json({"type": "error", "message": message})
