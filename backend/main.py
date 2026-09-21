import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

# Project Management Endpoints
PROJECTS_DIR = os.path.join(os.path.dirname(__file__), 'projects')
os.makedirs(PROJECTS_DIR, exist_ok=True)

def get_project_dir(project: str):
    path = os.path.join(PROJECTS_DIR, project)
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(path, 'maps'), exist_ok=True)
    os.makedirs(os.path.join(path, 'schema'), exist_ok=True)
    return path

# Global instances
default_proj_dir = get_project_dir("factory1")
factory_state = FactoryState(default_proj_dir, "map.json")
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
    """Broadcasts the simulation state to all connected WebSocket clients at 30 FPS."""
    import time
    while True:
        if connected_clients:
            try:
                state_dict = factory_state.to_dict(sim_engine.sim_time)
                state_dict["server_time"] = time.time()
                state_dict["is_paused"] = (sim_engine.time_scale == 0.0)
                state_dict["time_scale"] = sim_engine.time_scale
                payload = json.dumps(state_dict)
                disconnected = set()
                for client in connected_clients:
                    try:
                        await client.send_text(payload)
                    except Exception:
                        disconnected.add(client)
                connected_clients.difference_update(disconnected)
            except Exception as e:
                pass
        
        await asyncio.sleep(1 / 30)

@app.websocket("/ws/simulation")
async def websocket_endpoint(websocket: WebSocket):
    global factory_state, sim_engine
    await websocket.accept()
    connected_clients.add(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            action = cmd.get("action")
            if action == "pause":
                sim_engine.time_scale = 0.0
            elif action == "play" or action == "resume":
                sim_engine.time_scale = float(cmd.get("speed", 1.0))
            elif action == "step":
                sim_engine.step(float(cmd.get("dt", 0.1)))
            elif action == "reset":
                current_time_scale = sim_engine.time_scale
                sim_engine.stop()
                factory_state = FactoryState(
                    project_dir=factory_state.project_dir,
                    map_filename=factory_state.map_filename,
                    fleet_size=factory_state.fleet_size,
                    strategies=factory_state.strategies
                )
                sim_engine = SimulationEngine(factory_state)
                sim_engine.time_scale = current_time_scale
                asyncio.create_task(sim_engine.run())
            elif action == "set_speed":
                sim_engine.time_scale = float(cmd.get("speed", 1.0))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        connected_clients.discard(websocket)

# Simulation REST API
@app.post("/api/simulation/init")
async def simulation_init(request: Request):
    """Initializes or reloads simulation from a specific project, map, and strategy configuration."""
    global factory_state, sim_engine
    body = await request.json()
    project = body.get("project", "factory1")
    map_filename = body.get("map_filename", "map.json")
    fleet_size = int(body.get("fleet_size", 5))
    strategies = body.get("strategies", {})
    recipes = body.get("recipes", None)

    proj_dir = get_project_dir(project)
    
    # Pause existing engine
    sim_engine.stop()
    
    # Create new factory state
    factory_state = FactoryState(
        project_dir=proj_dir,
        map_filename=map_filename,
        fleet_size=fleet_size,
        strategies=strategies,
        recipes=recipes
    )
    sim_engine = SimulationEngine(factory_state)
    asyncio.create_task(sim_engine.run())

    return {
        "status": "ok",
        "project": project,
        "map_filename": map_filename,
        "fleet_size": fleet_size,
        "strategies": factory_state.strategies,
        "recipes": factory_state.recipes
    }

@app.post("/api/simulation/control")
async def simulation_control(request: Request):
    """Controls simulation playback: play, pause, step, reset, set_speed."""
    global factory_state, sim_engine
    body = await request.json()
    action = body.get("action")
    if action == "pause":
        sim_engine.time_scale = 0.0
    elif action in ("play", "resume"):
        sim_engine.time_scale = float(body.get("speed", 1.0))
    elif action == "step":
        sim_engine.step(float(body.get("dt", 0.1)))
    elif action == "reset":
        current_time_scale = sim_engine.time_scale
        sim_engine.stop()
        factory_state = FactoryState(
            project_dir=factory_state.project_dir,
            map_filename=factory_state.map_filename,
            fleet_size=factory_state.fleet_size,
            strategies=factory_state.strategies
        )
        sim_engine = SimulationEngine(factory_state)
        sim_engine.time_scale = current_time_scale
        asyncio.create_task(sim_engine.run())
    elif action == "set_speed":
        sim_engine.time_scale = float(body.get("speed", 1.0))
    return {
        "status": "ok",
        "action": action,
        "time_scale": sim_engine.time_scale,
        "sim_time": sim_engine.sim_time
    }

@app.post("/api/simulation/config")
async def simulation_config(request: Request):
    """Updates modular strategies, fleet size, or OHT specs in real time."""
    body = await request.json()
    if "strategies" in body:
        factory_state.update_strategies(body["strategies"])
    if "fleet_size" in body:
        factory_state.set_fleet_size(int(body["fleet_size"]))
    if "oht_specs" in body:
        from .core.config import update_oht_specs
        update_oht_specs(body["oht_specs"])
    from .core.config import get_oht_specs
    return {
        "status": "ok",
        "strategies": factory_state.strategies,
        "fleet_size": factory_state.fleet_size,
        "oht_specs": get_oht_specs()
    }

@app.get("/api/simulation/oht_specs")
async def get_simulation_oht_specs():
    from .core.config import get_oht_specs
    return get_oht_specs()


@app.get("/api/simulation/strategies")
def get_strategies_list():
    """Returns available modular strategy options."""
    return {
        "pathfinding": ["dijkstra", "congestion_aware"],
        "traffic": ["block_reservation", "kinematic_merge"],
        "vehicle_assignment": ["nearest", "fifo"],
        "machine_allocation": ["least_loaded", "closest", "round_robin"],
        "idle_strategy": ["stay_and_nudge", "cruising"]
    }

@app.get("/api/simulation/export_metrics")
def export_metrics(format: str = "json"):
    """Exports metrics summary as JSON or CSV."""
    from fastapi.responses import Response
    summary = factory_state.analytics.get_summary(
        sim_engine.sim_time,
        factory_state.machines,
        factory_state.agents
    )
    if format.lower() == "csv":
        csv_data = factory_state.analytics.export_csv(summary)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=simulation_metrics.csv"}
        )
    return summary

@app.post("/api/simulation/fast_forward")
async def simulation_fast_forward(request: Request):
    """
    Executes discrete-event simulation in headless turbo mode at maximum CPU speed.
    Runs until duration has elapsed, pauses, and returns the complete analytical summary.
    """
    global factory_state, sim_engine
    body = await request.json()
    duration = float(body.get("duration", 60.0))
    dt = float(body.get("dt", 0.05))
    reset_first = bool(body.get("reset_first", False))

    if reset_first:
        sim_engine.reset()
        target_sim_time = duration
    else:
        target_sim_time = sim_engine.sim_time + duration

    # Pause real-time progression during turbo stepping
    sim_engine.time_scale = 0.0

    # Fast-forward stepping loop
    max_steps = int(duration / dt) + 1000
    steps = 0
    while sim_engine.sim_time < target_sim_time and steps < max_steps:
        step_dt = min(dt, target_sim_time - sim_engine.sim_time)
        if step_dt <= 0.0001:
            break
        sim_engine.step(step_dt)
        steps += 1

    sim_engine.time_scale = 0.0

    # Retrieve full analytics summary
    summary = factory_state.analytics.get_summary(
        sim_engine.sim_time,
        factory_state.machines,
        factory_state.agents
    )

    return {
        "status": "ok",
        "sim_time": round(sim_engine.sim_time, 2),
        "duration_run": duration,
        "steps_computed": steps,
        "summary": summary
    }

@app.get("/api/health")
def read_health():
    return {"status": "ok"}

import re

@app.get("/api/maps/{project}")
def list_maps(project: str):
    maps_dir = os.path.join(get_project_dir(project), 'maps')
    maps = [f for f in os.listdir(maps_dir) if f.endswith('.json')]
    if not maps and project == "factory1":
        # Check if default map.json exists in backend/maps
        src = os.path.join(os.path.dirname(__file__), 'maps', 'map.json')
        if os.path.exists(src):
            dst = os.path.join(maps_dir, 'map.json')
            try:
                with open(src, 'r') as sf, open(dst, 'w') as df:
                    df.write(sf.read())
                maps = ['map.json']
            except Exception:
                pass
    return {"maps": maps}

@app.get("/api/maps/{project}/{filename}")
def load_map(project: str, filename: str):
    if not filename.endswith('.json'): filename += '.json'
    path = os.path.join(get_project_dir(project), 'maps', filename)
    if not os.path.exists(path):
        if project == "factory1" and filename == "map.json":
            src = os.path.join(os.path.dirname(__file__), 'maps', 'map.json')
            if os.path.exists(src):
                with open(src, 'r') as sf, open(path, 'w') as df:
                    df.write(sf.read())
                with open(path, 'r') as f:
                    return json.load(f)
        return {"error": "File not found"}, 404
    with open(path, 'r') as f:
        return json.load(f)

@app.post("/api/save_map/{project}/{filename}")
async def save_map_post(project: str, filename: str, request: Request):
    if not filename.endswith('.json'): filename += '.json'
    path = os.path.join(get_project_dir(project), 'maps', filename)
    data = await request.json()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return {"status": "ok", "filename": filename}

@app.get("/api/schemas/{project}")
def get_schemas(project: str):
    path = os.path.join(get_project_dir(project), 'schema', 'machineAndSchema.json')
    if not os.path.exists(path):
        if project == "factory1":
            src = os.path.join(os.path.dirname(__file__), 'maps', 'map_schemas.json')
            if os.path.exists(src):
                with open(src, 'r') as sf, open(path, 'w') as df:
                    df.write(sf.read())
                with open(path, 'r') as f:
                    return json.load(f)
        return {}
    with open(path, 'r') as f:
        return json.load(f)

@app.post("/api/schemas/{project}")
async def save_schemas(project: str, request: Request):
    path = os.path.join(get_project_dir(project), 'schema', 'machineAndSchema.json')
    data = await request.json()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return {"status": "ok"}

@app.get("/api/recipes/{project}")
def get_recipes(project: str):
    path = os.path.join(get_project_dir(project), 'schema', 'recipes.json')
    if not os.path.exists(path):
        if project == "factory1":
            src = os.path.join(os.path.dirname(__file__), 'maps', 'map_recipes.json')
            if os.path.exists(src):
                with open(src, 'r') as sf, open(path, 'w') as df:
                    df.write(sf.read())
                with open(path, 'r') as f:
                    return json.load(f)
        return {}
    with open(path, 'r') as f:
        return json.load(f)

@app.post("/api/recipes/{project}")
async def save_recipes(project: str, request: Request):
    path = os.path.join(get_project_dir(project), 'schema', 'recipes.json')
    data = await request.json()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    global factory_state
    factory_state.recipes = data
    return {"status": "ok"}

@app.post("/api/projects/{project}/save")
async def save_project(project: str, request: Request):
    data = await request.json()
    proj_dir = get_project_dir(project)
    saved = {}

    # Save map if present
    if "map" in data and data["map"] is not None:
        map_filename = data.get("map_filename", "map.json")
        if not map_filename.endswith('.json'):
            map_filename += '.json'
        map_path = os.path.join(proj_dir, 'maps', map_filename)
        with open(map_path, 'w') as f:
            json.dump(data["map"], f, indent=2)
        saved["map"] = map_filename

    # Save schemas if present
    if "schemas" in data and data["schemas"] is not None:
        schema_path = os.path.join(proj_dir, 'schema', 'machineAndSchema.json')
        with open(schema_path, 'w') as f:
            json.dump(data["schemas"], f, indent=2)
        saved["schemas"] = True

    # Save recipes if present
    if "recipes" in data and data["recipes"] is not None:
        recipe_path = os.path.join(proj_dir, 'schema', 'recipes.json')
        with open(recipe_path, 'w') as f:
            json.dump(data["recipes"], f, indent=2)
        saved["recipes"] = True

    # Auto-reload running simulation with the newly saved map, schema, and recipes data
    try:
        global factory_state, sim_engine
        current_time_scale = sim_engine.time_scale
        sim_engine.stop()
        map_fn = data.get("map_filename", "map.json")
        if not map_fn.endswith('.json'): map_fn += '.json'
        factory_state = FactoryState(
            project_dir=proj_dir,
            map_filename=map_fn,
            fleet_size=factory_state.fleet_size,
            strategies=factory_state.strategies,
            recipes=data.get("recipes")
        )
        sim_engine = SimulationEngine(factory_state)
        sim_engine.time_scale = current_time_scale
        asyncio.create_task(sim_engine.run())
        saved["simulation_reloaded"] = True
    except Exception as e:
        print(f"Notice: could not auto-reload simulation on project save: {e}")

    return {"status": "ok", "project": project, "saved": saved}

@app.post("/api/projects/create")
async def create_project(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"error": "Project name is required"}, 400
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    if not clean_name:
        return {"error": "Invalid project name. Use alphanumeric characters, dashes, or underscores."}, 400
    
    proj_dir = get_project_dir(clean_name)
    # Seed initial empty map, schemas, recipes if not existing
    map_path = os.path.join(proj_dir, 'maps', 'map.json')
    if not os.path.exists(map_path):
        with open(map_path, 'w') as f:
            json.dump({"nodes": {}, "tracks": [], "machines": []}, f, indent=2)
    schema_path = os.path.join(proj_dir, 'schema', 'machineAndSchema.json')
    if not os.path.exists(schema_path):
        with open(schema_path, 'w') as f:
            json.dump({}, f, indent=2)
    recipe_path = os.path.join(proj_dir, 'schema', 'recipes.json')
    if not os.path.exists(recipe_path):
        with open(recipe_path, 'w') as f:
            json.dump({}, f, indent=2)

    return {"status": "ok", "project": clean_name}

@app.get("/api/projects")
def list_projects():
    projects = []
    if os.path.exists(PROJECTS_DIR):
        for f in os.listdir(PROJECTS_DIR):
            if os.path.isdir(os.path.join(PROJECTS_DIR, f)):
                projects.append(f)
    if not projects:
        projects = ["factory1"] # default
        get_project_dir("factory1")
    return {"projects": projects}

# Mount Frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
