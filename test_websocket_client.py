#!/usr/bin/env python3
"""
WebSocket 客户端测试脚本（连接公网服务器）
服务器部署在 112.29.111.158:20307，对应内网 10.0.105.4:24000。
"""
import asyncio
import websockets
import json

async def test_websocket_interaction():
    # ✅ 直接连接公网映射端口
    uri = "ws://112.29.111.158:20307/api/v1/ws/case"

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
            print(f"✅ 已连接到 {uri}")

            # 1. 发送启动消息
            start_message = {
                "type": "start",
                "api_key": "ustc",
                "case_name": "",
                "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
                "model": "qwen3-235b-a22b-instruct-2507",
                "max_retries": 3
            }
            await websocket.send(json.dumps(start_message, ensure_ascii=False))
            print("📤 已发送启动消息")

            # 2. 监听服务器消息并交互
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    msg_type = data.get("type")

                    print(f"\n📥 收到消息类型: {msg_type}")
                    print(f"内容: {json.dumps(data, ensure_ascii=False, indent=2)}")

                    if msg_type == "notify":
                        print(f"[通知] {data.get('message', '')}")
                    elif msg_type == "progress":
                        print(f"[进度] {data.get('stage', '')}: {data.get('detail', '')}")
                    elif msg_type == "ask":
                        question = data.get("question", "")
                        key = data.get("key", "")
                        choices = data.get("choices", [])
                        default = data.get("default", "")
                        print(f"\n❓ [询问] {question}")
                        if choices:
                            print(f"可选择: {choices}")
                        if default:
                            print(f"默认值: {default}")
                        user_answer = input("请输入你的回答 (回车使用默认值): ").strip()
                        if not user_answer:
                            user_answer = default or "confirm"
                        await websocket.send(json.dumps({
                            "type": "answer",
                            "key": key,
                            "value": user_answer
                        }, ensure_ascii=False))
                    elif msg_type == "confirm":
                        question = data.get("question", "")
                        key = data.get("key", "")
                        default = data.get("default", False)
                        print(f"\n❓ [确认] {question} (y/n)")
                        user_confirm = input("请输入 y 或 n (回车默认 y): ").strip().lower() or "y"
                        while user_confirm not in ["y", "n"]:
                            user_confirm = input("请输入 y 或 n: ").strip().lower()
                        await websocket.send(json.dumps({
                            "type": "answer",
                            "key": key,
                            "value": user_confirm
                        }, ensure_ascii=False))
                    elif msg_type == "finished":
                        print("✅ 测试执行完成!")
                        print("结果:\n", json.dumps(data.get("data", {}), ensure_ascii=False, indent=2))
                        break
                    elif msg_type == "error":
                        print(f"❌ 执行错误: {data.get('message', '未知错误')}")
                        break
                except websockets.exceptions.ConnectionClosed:
                    print("🔌 WebSocket连接已关闭")
                    break
                except Exception as e:
                    print(f"❌ 处理消息时出错: {e}")
                    break
    except Exception as e:
        print(f"❌ 无法连接服务器: {e}")
        print("💡 请确认服务器 112.29.111.158:20307 正在运行并开放访问")

if __name__ == "__main__":
    print("🚀 启动 WebSocket 客户端测试（公网模式）...")
    asyncio.run(test_websocket_interaction())
