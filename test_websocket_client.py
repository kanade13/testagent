#!/usr/bin/env python3
"""
WebSocket 客户端测试脚本（交互版）
用户可通过命令行输入回答服务器的询问或确认。
"""
import asyncio
import websockets
import json

async def test_websocket_interaction():
    uri = "ws://localhost:8000/api/v1/ws/case"

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket连接已建立")

            # 1. 发送启动消息
            start_message = {
                "type": "start",
                "api_key": "ustc",  # 默认API密钥
                "case_name": "",
                "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
                "model": "qwen3-235b-a22b-instruct-2507",
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
                        print(f"[通知] {data.get('message', '')}")

                    elif msg_type == "progress":
                        stage = data.get("stage", "")
                        detail = data.get("detail", "")
                        print(f"[进度] {stage}: {detail}")

                    elif msg_type == "ask":
                        # 🔸服务器询问用户输入
                        question = data.get("question", "")
                        key = data.get("key", "")
                        choices = data.get("choices", [])
                        default = data.get("default", "")

                        print(f"\n❓ [询问] {question}")
                        if choices:
                            print(f"可选择: {choices}")
                        if default:
                            print(f"默认值: {default}")

                        user_answer = input("请输入你的回答 (直接回车使用默认值): ").strip()
                        if not user_answer:
                            user_answer = default or "confirm"

                        print(f"💬 用户回答: {user_answer}")

                        answer = {
                            "type": "answer",
                            "key": key,
                            "value": user_answer
                        }
                        await websocket.send(json.dumps(answer))

                    elif msg_type == "confirm":
                        question = data.get("question", "")
                        key = data.get("key", "")
                        default = data.get("default", False)

                        print(f"\n❓ [确认] {question} (y/n)")
                        user_confirm = input("请输入 y 或 n (回车使用默认 y): ").strip().lower()
                        if not user_confirm:
                            user_confirm = "y"
                        while user_confirm not in ["y", "n"]:
                            user_confirm = input("请输入 y 或 n: ").strip().lower()

                        print(f"💬 用户确认: {user_confirm}")

                        answer = {
                            "type": "answer",
                            "key": key,
                            "value": user_confirm
                        }
                        await websocket.send(json.dumps(answer))

                    elif msg_type == "finished":
                        print("✅ 测试执行完成!")
                        result_data = data.get("data", {})
                        print(f"结果: {json.dumps(result_data, ensure_ascii=False, indent=2)}")
                        break

                    elif msg_type == "error":
                        error_message = data.get("message", "未知错误")
                        print(f"❌ 执行错误: {error_message}")
                        break

                    else:
                        print(f"⚠️ 未知消息类型: {msg_type}")

                except websockets.exceptions.ConnectionClosed:
                    print("🔌 WebSocket连接已关闭")
                    break
                except Exception as e:
                    print(f"❌ 处理消息时出错: {e}")

    except Exception as e:
        print(f"❌ WebSocket连接失败: {e}")
        print("确保服务器正在运行在 http://localhost:8000")

if __name__ == "__main__":
    print("🚀 启动 WebSocket 客户端测试 (命令行交互版)...")
    print("确保服务器正在运行: uvicorn app.main:app --host 0.0.0.0 --port 8000")
    asyncio.run(test_websocket_interaction())
