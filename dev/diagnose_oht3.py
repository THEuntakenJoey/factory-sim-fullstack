import asyncio
import websockets
import json

async def check():
    async with websockets.connect('ws://127.0.0.1:8000/ws/simulation') as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        for a in data.get("agents", []):
            if a["id"] in ("OHT_03", "OHT_02", "OHT_01", "OHT_05"):
                print(f"=== {a['id']} ===")
                for k, v in a.items():
                    print(f"  {k}: {v}")

asyncio.run(check())
