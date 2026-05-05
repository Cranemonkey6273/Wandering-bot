import asyncio
import websockets
import json
import os

NITRADO_TOKEN = os.getenv("NITRADO_TOKEN")

WS_URL = f"wss://websocket.nitrado.net/?token={NITRADO_TOKEN}"

async def listen():
    async with websockets.connect(WS_URL) as ws:
        print("✅ Connected to Nitrado WebSocket")

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)

                # Debug everything first
                print("LIVE EVENT:", data)

                # You will filter events here later
                if "type" in data:
                    print("EVENT TYPE:", data["type"])

            except Exception as e:
                print("❌ Error:", e)
                await asyncio.sleep(5)

if name == "main":
    asyncio.run(listen())
