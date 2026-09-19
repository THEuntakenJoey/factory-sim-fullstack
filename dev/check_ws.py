import asyncio
import websockets
import json

async def check():
    async with websockets.connect('ws://127.0.0.1:8000/ws/simulation') as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        print("Sim Time:", data.get("sim_time"))
        for a in data.get("agents", []):
            print(f"Agent {a['id']}: state={a['state']}, block={a['current_block']}, pos=({a['x']:.2f}, {a['y']:.2f}), heading={a['heading']:.1f}, speed={a['speed']:.2f}, cargo={a['cargo']}")

asyncio.run(check())
