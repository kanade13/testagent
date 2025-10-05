#!/usr/bin/env python3
# test_websocket_client.py
"""
WebSocket 客户端测试脚本
用于测试与testagent WebSocket接口的交互
"""
import asyncio
import websockets
import json

async def test_websocket_interaction():
    uri = "ws://localhost:8000/ws/case?api_key=ustc"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket连接已建立")
            #先发送auth消息

            # 1. 发送启动消息
            start_message = {
                "type": "start",
                "api_key": "ustc",  # 默认API密钥
                "case_name": "测试用例",
                "case_desc": "简单的测试用例描述",
                "model": "qwen-turbo",
                "max_retries": 3
            }
            await websocket.send(json.dumps(start_message))
            print("📤 已发送启动消息")
            
            # 2. 监听服务器消息并交互
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    print(f"\n📥 收到消息: {msg_type}")
                    print(f"内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    
                    if msg_type == "notify":
                        # 服务器通知消息，只需显示
                        print(f"[通知] {data.get('message', '')}")
                        
                    elif msg_type == "progress":
                        # 进度消息
                        stage = data.get("stage", "")
                        detail = data.get("detail", "")
                        print(f"[进度] {stage}: {detail}")
                        
                    elif msg_type == "ask":
                        # 服务器询问，需要用户回复
                        question = data.get("question", "")
                        key = data.get("key", "")
                        choices = data.get("choices", [])
                        default = data.get("default", "")
                        
                        print(f"\n❓ [询问] {question}")
                        if choices:
                            print(f"可选择: {choices}")
                        if default:
                            print(f"默认值: {default}")
                        
                        # 模拟用户输入（实际应用中可以从控制台读取）
                        if "stage1_command" in key:
                            user_answer = "confirm"  # 阶段1确认
                        elif "step_" in key and "_command" in key:
                            user_answer = "confirm"  # 步骤确认
                        else:
                            user_answer = default or "confirm"
                        
                        print(f"💬 用户回答: {user_answer}")
                        
                        # 发送回答
                        answer = {
                            "type": "answer",
                            "key": key,
                            "value": user_answer
                        }
                        await websocket.send(json.dumps(answer))
                        
                    elif msg_type == "confirm":
                        # 服务器要求确认
                        question = data.get("question", "")
                        key = data.get("key", "")
                        default = data.get("default", False)
                        
                        print(f"\n❓ [确认] {question} (y/n)")
                        
                        # 模拟用户确认
                        user_confirm = "y"  # 总是确认
                        print(f"💬 用户确认: {user_confirm}")
                        
                        # 发送确认
                        answer = {
                            "type": "answer",
                            "key": key,
                            "value": user_confirm
                        }
                        await websocket.send(json.dumps(answer))
                        
                    elif msg_type == "finished":
                        # 执行完成
                        print("✅ 测试执行完成!")
                        result_data = data.get("data", {})
                        print(f"结果: {json.dumps(result_data, ensure_ascii=False, indent=2)}")
                        break
                        
                    elif msg_type == "error":
                        # 执行错误
                        error_message = data.get("message", "未知错误")
                        print(f"❌ 执行错误: {error_message}")
                        break
                        
                    else:
                        print(f"⚠️  未知消息类型: {msg_type}")
                        
                except websockets.exceptions.ConnectionClosed:
                    print("🔌 WebSocket连接已关闭")
                    break
                except Exception as e:
                    print(f"❌ 处理消息时出错: {e}")
                    
    except Exception as e:
        print(f"❌ WebSocket连接失败: {e}")
        print("确保服务器正在运行在 http://localhost:8000")

if __name__ == "__main__":
    print("🚀 启动WebSocket客户端测试...")
    print("确保服务器正在运行: uvicorn app.main:app --host 0.0.0.0 --port 8000")
    asyncio.run(test_websocket_interaction())