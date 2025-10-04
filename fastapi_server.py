#!/usr/bin/env python3
"""
深度研究FastAPI服务端 - sent (已修复上下文管理)
提供WebSocket接口，为每个客户端维护独立的、有状态的对话会话。
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import asdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

# 从重构后的 api_interface 导入核心类
from api_interface import ResearchAPI, ResearchStatus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fastapi_server.log', mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('fastapi_server')

# 创建FastAPI应用
app = FastAPI(
    title="深度研究API服务（会话隔离版）",
    description="为每个WebSocket连接提供独立的、有状态的研究会话。",
    version="2.0.0"
)

# 全局状态管理
class ConnectionManager:
    """[已重构] 每个客户端都拥有一个独立的 ResearchAPI 实例"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        # ★★★ 核心: 此字典为每个 client_id 存储一个完全独立的 ResearchAPI 实例 ★★★
        self.client_apis: Dict[str, ResearchAPI] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        # ★★★ 核心: 为新连接创建一个全新的、隔离的 ResearchAPI 实例 ★★★
        self.client_apis[client_id] = ResearchAPI(client_id)
        logger.info(f"🔌 客户端 {client_id} 已连接，并已创建专属研究实例。")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.client_apis:
            del self.client_apis[client_id]
        logger.info(f"🔌 客户端 {client_id} 已断开，相关资源已清理。")
    
    async def send_personal_message(self, message: Dict[str, Any], client_id: str):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(json.dumps(message, ensure_ascii=False))
            except Exception as e:
                logger.error(f"❌ 发送消息给 {client_id} 失败: {e}")
    
    def get_client_api(self, client_id: str) -> Optional[ResearchAPI]:
        return self.client_apis.get(client_id)

manager = ConnectionManager()

# WebSocket接口
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            logger.info(f"📨 收到来自 {client_id} 的消息: {message.get('type', 'unknown')}")
            
            response = await process_websocket_message(message, client_id)
            
            await manager.send_personal_message(response, client_id)
            
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"❌ WebSocket {client_id} 发生未知错误: {e}", exc_info=True)
        # 发生错误时也确保断开连接和清理资源
        manager.disconnect(client_id)

async def process_websocket_message(message: Dict[str, Any], client_id: str) -> Dict[str, Any]:
    """[已重构] 将消息路由到客户端专属的ResearchAPI实例"""
    try:
        msg_type = message.get('type')
        
        # ★★★ 核心: 获取此客户端专属的API实例 ★★★
        client_api = manager.get_client_api(client_id)
        if not client_api:
            return {'type': 'error', 'message': '会话不存在或已过期', 'error': 'INVALID_SESSION'}

        # 事件监听器，用于将中间过程（思考过程）实时发送回客户端
        async def event_listener(status: ResearchStatus):
            event_data = {'type': 'research_event', 'data': asdict(status)}
            # 使用create_task确保事件发送不会阻塞主流程
            asyncio.create_task(manager.send_personal_message(event_data, client_id))
        
        client_api.add_event_listener(event_listener)
        
        response_obj = None
        try:
            if msg_type == 'start_research':
                question = message.get('question', '')
                logger.info(f"🔍 客户端 {client_id} 开始新研究: {question[:50]}...")
                response_obj = await client_api.start_research(question)
            
            elif msg_type == 'continue_research':
                clarification = message.get('clarification', '')
                logger.info(f"🔄 客户端 {client_id} 继续研究: {clarification[:50]}...")
                response_obj = await client_api.continue_research(clarification)
            
            elif msg_type == 'ping':
                return {'type': 'pong', 'timestamp': datetime.now().isoformat()}
            
            else:
                return {'type': 'error', 'message': f'未知消息类型: {msg_type}', 'error': 'UNKNOWN_MESSAGE_TYPE'}
        
        finally:
            # 确保每次调用后都移除监听器，避免重复添加
            client_api.remove_event_listener(event_listener)
        
        logger.info(f"✅ 客户端 {client_id} 交互完成: {response_obj.status}")
        
        # 将 dataclass 响应对象转换为字典，以便进行JSON序列化
        # 'type' 字段用于让 bridge_server 区分最终响应和事件
        final_response = asdict(response_obj)
        final_response['type'] = 'research_response'
        return final_response

    except Exception as e:
        logger.error(f"❌ 处理消息时出错: {e}", exc_info=True)
        return {'type': 'error', 'message': '处理消息时发生内部错误', 'error': str(e)}


if __name__ == "__main__":
    module_name = "fastapi_server" # 假设您的文件名是 fastapi_server.py
    
    import argparse
    parser = argparse.ArgumentParser(description='深度研究FastAPI服务端（会话隔离版）')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址 (默认: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=30052, help='监听端口 (默认: 30052)')
    parser.add_argument('--reload', action='store_true', help='开发模式，自动重载')
    args = parser.parse_args()
    
    logger.info(f"🚀 启动FastAPI服务端: {args.host}:{args.port}")
    
    uvicorn.run(
        f"{module_name}:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )