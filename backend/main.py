import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
import json

from .core.state import FactoryState
from .core.engine import SimulationEngine

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
map_path = os.path.join(os.path.dirname(__file__), 'maps', 'map.json')
factory_state = FactoryState(map_path)
sim_engine = SimulationEngine(factory_state)

connected_clients = set()

@app.on_event("startup")
async def startup_event():
    # Start the simulation loop in the background
    asyncio.create_task(sim_engine.run())
    # Start the broadcast loop
    asyncio.create_task(broadcast_loop())

@app.on_event("shutdown")
async def shutdown_event():
    sim_engine.stop()

async def broadcast_loop():
    """Broadcasts the simulation state to all connected WebSocket clients at a fixed rate."""
    while True:
        if connected_clients:
            payload = json.dumps(factory_state.to_dict())
            disconnected = set()
            for client in connected_clients:
                try:
                    await client.send_text(payload)
                except Exception:
                    disconnected.add(client)
            
            connected_clients.difference_update(disconnected)
        
        # Broadcast rate: 30 FPS
        await asyncio.sleep(1 / 30)

@app.websocket("/ws/simulation")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            # We can receive commands from the frontend here (e.g. pause, set speed, dispatch manually)
            data = await websocket.receive_text()
            cmd = json.loads(data)
            if cmd.get("action") == "pause":
                sim_engine.time_scale = 0.0
            elif cmd.get("action") == "resume":
                sim_engine.time_scale = cmd.get("speed", 1.0)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

@app.get("/")
def read_root():
    return {"status": "ok"}

# Map Management Endpoints
MAPS_DIR = os.path.join(os.path.dirname(__file__), 'maps')
os.makedirs(MAPS_DIR, exist_ok=True)

@app.get("/api/maps")
def list_maps():
    files = [f for f in os.listdir(MAPS_DIR) if f.endswith('.json')]
    return {"maps": files}

@app.get("/api/maps/{filename}")
def load_map(filename: str):
    path = os.path.join(MAPS_DIR, filename)
    if not os.path.exists(path):
        return {"error": "File not found"}, 404
    with open(path, 'r') as f:
        return json.load(f)

@app.post("/api/maps/{filename}")
async def save_map(filename: str, req: dict = None):
    # Depending on how frontend sends it, we can read raw body
    from fastapi import Request
    # But since we use a route parameter, let's accept it as body dict.
    # To keep it simple, we'll parse the request body directly.
    pass

@app.post("/api/save_map/{filename}")
async def save_map_post(filename: str, request: Request):
    path = os.path.join(MAPS_DIR, filename)
    if not path.endswith('.json'):
        path += '.json'
    data = await request.json()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return {"status": "ok", "filename": os.path.basename(path)}

@app.get("/api/schemas/{project}")
def get_schemas(project: str):
    path = os.path.join(MAPS_DIR, f"{project}_schemas.json")
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)

@app.post("/api/schemas/{project}")
async def save_schemas(project: str, request: Request):
    path = os.path.join(MAPS_DIR, f"{project}_schemas.json")
    data = await request.json()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return {"status": "ok"}

@app.get("/api/recipes/{project}")
def get_recipes(project: str):
    path = os.path.join(MAPS_DIR, f"{project}_recipes.json")
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)

@app.post("/api/recipes/{project}")
async def save_recipes(project: str, request: Request):
    path = os.path.join(MAPS_DIR, f"{project}_recipes.json")
    data = await request.json()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return {"status": "ok"}
