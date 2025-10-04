#!/usr/bin/env python3
"""
桥梁服务 (Bridge Server) - 持久化会话最终版
- 对接 Streamlit 前端 (提供 SSE 流式 HTTP 接口)
- 对接 研究后端 (管理持久化的 WebSocket 客户端连接)
- [核心改造] 为每个 job_id/client_id 维护一个长期存活的 WebSocket 连接，真正实现有状态的多轮对话。
- [新] 增加了会话超时自动清理机制，防止资源泄漏。
- 将日志同时输出到控制台和 bridge_server.log 文件
"""
import asyncio
import json
import logging
import sys
import uuid
from typing import Dict, Any, List, Union
from datetime import datetime, timedelta

import websockets
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bridge_server.log', mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('bridge_server')


# --- [已重构] WebSocket 客户端逻辑 (支持持久化连接) ---
class PersistentResearchClient:
    """
    为每个会话（job_id）管理一个到研究后端的持久 WebSocket 连接。
    """
    def __init__(self, client_id: str, host='localhost', port=30052):
        self.client_id = client_id
        self.ws_url = f"ws://{host}:{port}/ws/{self.client_id}"
        self.websocket: websockets.WebSocketClientProtocol = None
        self.connected = False
        # 每个HTTP请求都有自己的队列，以接收来自共享WebSocket的响应
        self.response_queues: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._listener_task: asyncio.Task = None
        self.last_activity = datetime.utcnow()

    async def connect(self):
        """建立并维持一个到研究后端的WebSocket连接，并启动监听器。"""
        if self.connected:
            return
        try:
            # 设置更长的 ping 超时以保持连接
            self.websocket = await websockets.connect(self.ws_url, open_timeout=10, ping_interval=20, ping_timeout=60)
            self.connected = True
            self._listener_task = asyncio.create_task(self._listen_for_messages())
            logger.info(f"🔌 [{self.client_id}] 持久化 WebSocket 已连接: {self.ws_url}")
        except Exception as e:
            logger.error(f"❌ [{self.client_id}] WebSocket 连接失败: {e}")
            self.connected = False
            await self._broadcast_error(f"无法连接到研究后端: {e}")

    async def _listen_for_messages(self):
        """[核心] 长期运行的任务，持续从 WebSocket 接收消息并分发到所有等待的请求队列中。"""
        try:
            while self.connected:
                try:
                    message_data = await self.websocket.recv()
                    message = json.loads(message_data)
                    logger.info(f"📨 [{self.client_id}] 从后端收到消息: {message_data[:300]}")
                    self.last_activity = datetime.utcnow()
                    await self._broadcast(message)
                    # 如果是最终响应，则标记本次交互完成
                    if message.get('type') == 'research_response':
                         await self._broadcast({"type": "done_interaction"})
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"🔌 [{self.client_id}] 后端 WebSocket 连接已关闭: {e}")
                    await self._broadcast_error("与研究后端的连接已意外关闭。")
                    break
        except Exception as e:
            logger.error(f"❌ [{self.client_id}] 监听任务异常: {e}", exc_info=True)
            await self._broadcast_error(f"处理消息时发生错误: {e}")
        finally:
            self.connected = False

    async def send_message(self, message: Dict[str, Any]) -> asyncio.Queue:
        """发送消息到研究后端，并返回一个队列以接收本次请求的响应。"""
        async with self._lock:
            if not self.connected:
                await self.connect()

            if not self.connected:
                 # 如果连接失败，返回一个已经包含错误的队列
                error_queue = asyncio.Queue()
                await error_queue.put({"type": "error", "message": "无法与研究后端建立连接。"})
                return error_queue

            # 为这个特定的HTTP请求创建一个新的响应队列
            queue = asyncio.Queue()
            self.response_queues.append(queue)
            
            try:
                await self.websocket.send(json.dumps(message, ensure_ascii=False))
                self.last_activity = datetime.utcnow()
                logger.info(f"📤 [{self.client_id}] 发送到研究后端: {json.dumps(message, ensure_ascii=False)}")
            except Exception as e:
                logger.error(f"❌ [{self.client_id}] 发送消息失败: {e}")
                await queue.put({"type": "error", "message": f"发送消息失败: {e}"})

            return queue

    def remove_queue(self, queue: asyncio.Queue):
        """当一个HTTP请求结束后，移除其对应的响应队列。"""
        if queue in self.response_queues:
            self.response_queues.remove(queue)

    async def _broadcast(self, message: Dict[str, Any]):
        """将从WebSocket收到的消息放入所有当前活动的请求队列中。"""
        for queue in self.response_queues:
            await queue.put(message)

    async def _broadcast_error(self, error_message: str):
        """广播错误信息并结束所有等待的请求。"""
        error_payload = {"type": "error", "message": error_message}
        await self._broadcast(error_payload)
        await self._broadcast({"type": "done_interaction"})


    async def disconnect(self):
        """安全地断开WebSocket连接并停止监听任务。"""
        if self.connected and self.websocket:
            self.connected = False
            await self.websocket.close()
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
        logger.info(f"🔌 [{self.client_id}] 持久化 WebSocket 已断开。")

# --- FastAPI 应用定义 ---
app = FastAPI(title="Streamlit Bridge Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# [核心] 全局会话管理器，存储持久化的客户端实例
client_sessions: Dict[str, PersistentResearchClient] = {}
SESSION_TIMEOUT = timedelta(minutes=30) # 30分钟无活动则清理会话

def format_sse_from_backend_response(backend_response: Dict[str, Any]) -> Union[Dict, List[Dict], None]:
    """将从研究后端收到的【任何】响应格式化为前端期望的一个或多个SSE事件"""
    response_type = backend_response.get("type")
    
    if response_type == 'research_event':
        data = backend_response.get("data", {})
        state = data.get("current_state", "状态更新")
        
        if "search_queries" in data and data.get("search_queries"):
            # 专用于搜索日志
            return {"type": "search_log", "state": state, "queries": data["search_queries"]}
        else:
            # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
            # ★★★               核心修复：传递 web_pages 数据              ★★★
            # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
            # 默认为状态更新事件
            sse_event = {
                "type": "state_update",
                "state": state,
                "message": data.get("current_message", "")
            }
            # 如果原始数据中存在 web_pages，将其添加到要发往前端的事件中
            if "web_pages" in data and data.get("web_pages"):
                sse_event["web_pages"] = data["web_pages"]
            return sse_event
    
    if response_type == 'research_response':
        status = backend_response.get("status")
        if status == "success":
            report = backend_response.get("final_report", "")
            return [{"type": "final_report_chunk", "content": report[i:i+20]} for i in range(0, len(report), 20)] if report else []
        elif status == "clarification_needed":
            data = backend_response.get("data", {})
            return {"type": "clarification_needed", "message": data.get("current_message", "请提供更多信息。")}
        elif status == "error":
            return {"type": "error", "message": backend_response.get("error") or backend_response.get("message", "后端返回未知错误。")}
    
    if response_type == "error":
        return backend_response
        
    return None


@app.post("/research")
async def research_endpoint(request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"type": "error", "message": "无效的JSON请求体"})
        
    logger.info(f"收到前端请求: {payload}")
    job_id = payload.get("job_id")
    if not job_id:
        return JSONResponse(status_code=400, content={"type": "error", "message": "请求中缺少 job_id"})

    client = client_sessions.get(job_id)
    if not client:
        logger.info(f"✨ 为 job_id '{job_id}' 创建新的持久化会话实例")
        client = PersistentResearchClient(client_id=job_id)
        client_sessions[job_id] = client

    clarification_history = payload.get("clarification_history", [])
    if len(clarification_history) <= 1:
        backend_message = {'type': 'start_research', 'question': payload.get("query")}
    else:
        backend_message = {'type': 'continue_research', 'clarification': payload.get("clarification")}
    
    response_queue = await client.send_message(backend_message)

    async def stream_generator():
        try:
            while True:
                backend_response = await response_queue.get()
                
                if backend_response.get("type") == "done_interaction":
                    break
                
                sse_events = format_sse_from_backend_response(backend_response)
                if sse_events:
                    if not isinstance(sse_events, list): sse_events = [sse_events]
                    for event in sse_events:
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        if event.get("type") == "final_report_chunk": await asyncio.sleep(0.02)
        
        except asyncio.CancelledError:
            logger.warning(f"Frontend for job {job_id} disconnected. Cleaning up.")
            if job_id in client_sessions:
                await client_sessions[job_id].disconnect()
                del client_sessions[job_id]
                logger.info(f"✅ 会话 {job_id} 已因前端断开而清理。")
        finally:
            client.remove_queue(response_queue)

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

async def cleanup_inactive_sessions():
    """定期清理不活跃的会话以释放资源。"""
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        inactive_sessions = []
        for job_id, client in client_sessions.items():
            if now - client.last_activity > SESSION_TIMEOUT:
                inactive_sessions.append(job_id)
        
        for job_id in inactive_sessions:
            logger.info(f"⌛ 会话 {job_id} 因长时间不活跃而被清理。")
            client = client_sessions.pop(job_id, None)
            if client:
                await client.disconnect()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive_sessions())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)