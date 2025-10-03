# ws_client.py
import asyncio
import json
import websockets  # pip install websockets

from main_controller import CONTEXT_JSON
API_KEY = "ustc"
WS_URL = f"ws://localhost:8000/ws/case?api_key={API_KEY}"


async def ask_user(prompt: str) -> str:
    loop = asyncio.get_running_loop()
    # 在线程池里执行同步 input，避免阻塞事件循环
    return await loop.run_in_executor(None, lambda: input(prompt))

async def run():
    # 调高 ping 参数，避免弱网场景下误判超时（可选）
    async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({
            "type": "start",
            "case_name": "",
            "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
            "context_json": CONTEXT_JSON,
            "model": "qwen-plus",
            "max_retries": 2,
            "context": None
        }))

        while True:
            msg = json.loads(await ws.recv())
            t = msg.get("type")
            print("<<", msg)

            if t in {"ask", "confirm"}:
                key = msg["key"]
                question = msg["question"]
                value = await ask_user(f"{question} > ")   # ← 非阻塞获取输入
                await ws.send(json.dumps({"type": "answer", "key": key, "value": value}))
            elif t in {"notify", "progress"}:
                pass
            elif t in {"finished", "error"}:
                break

if __name__ == "__main__":
    asyncio.run(run())
