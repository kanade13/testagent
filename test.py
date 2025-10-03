# ws_client.py
import asyncio
import json
import websockets  # pip install websockets

from main_controller import CONTEXT_JSON
from dotenv import load_dotenv
load_dotenv()  # 自动加载 .env 文件
API_KEY = "ustc"
WS_URL = f"ws://localhost:8000/ws/case?api_key={API_KEY}"

async def run():
    async with websockets.connect(WS_URL) as ws:
        # 1) 发送 start
        start = {
            "type": "start",
            "case_name": "",
            "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
            "context_json": CONTEXT_JSON,
            "model": "qwen-plus",
            "max_retries": 2,
            "context": None
        }
        await ws.send(json.dumps(start))

        # 2) 持续收消息并按需作答
        while True:
            msg = json.loads(await ws.recv())
            t = msg.get("type")
            print("<<", msg)

            if t in {"ask", "confirm"}:
                key = msg["key"]
                question = msg["question"]
                # 这里可以接入你的 UI；示例里直接用 input()
                value = input(f"{question} > ")
                await ws.send(json.dumps({"type": "answer", "key": key, "value": value}))
            elif t in {"notify", "progress"}:
                # 展示即可
                pass
            elif t in {"finished", "error"}:
                break

if __name__ == "__main__":
    asyncio.run(run())




