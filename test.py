import asyncio, json
import websockets

WS_URL = "ws://localhost:8000/api/v1/ws/case"
API_KEY = "ustc"

async def main():
    async with websockets.connect(
        WS_URL,
        additional_headers=[("X-API-Key", API_KEY)],  # ← v15 正确写法
        ping_interval=20,
        ping_timeout=20,
        proxy=None,  # 本地开发常见代理坑，建议关掉自动代理
    ) as ws:
        print("✅ connected")
        async def recv():
            async for msg in ws:
                try:
                    print("[SERVER]", json.dumps(json.loads(msg), ensure_ascii=False, indent=2))
                except Exception:
                    print("[SERVER TEXT]", msg)

        async def send():
            while True:
                line = await asyncio.to_thread(input, "> ")
                if line.strip().lower() in {"/quit", "/exit"}:
                    await ws.close(code=1000, reason="client quit")
                    break
                await ws.send(line)

        await asyncio.wait({asyncio.create_task(recv()), asyncio.create_task(send())},
                           return_when=asyncio.FIRST_COMPLETED)

if __name__ == "__main__":
    asyncio.run(main())
