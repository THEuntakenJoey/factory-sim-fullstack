import asyncio
import websockets
import json
import urllib.request
import urllib.parse
import time

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/simulation"

def http_get(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "TestClient"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def http_post(path, data):
    url = f"{BASE_URL}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "TestClient"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

async def main():
    print("=== LIVE FASTAPI SERVER COMPREHENSIVE VERIFICATION ===")
    
    # 1. Test Recipe Sync API
    print("\n1. Testing GET & POST /api/recipes/factory1 ...")
    recipes = http_get("/api/recipes/factory1")
    print(f"[OK] Fetched recipes count: {len(recipes.keys())} recipes: {list(recipes.keys())}")
    
    custom_recipes = {
        "Wafer_Type_A": {
            "id": "Wafer_Type_A",
            "name": "Live Test Flow",
            "steps": ["2", "1"]
        }
    }
    update_res = http_post("/api/recipes/factory1", custom_recipes)
    assert update_res.get("status") in ["success", "ok"], f"Expected status success or ok, got {update_res}"
    print(f"[OK] Recipe updated dynamically: {update_res}")
    
    # Verify GET returns updated
    recipes_after = http_get("/api/recipes/factory1")
    assert "Wafer_Type_A" in recipes_after, "Wafer_Type_A should be present in recipes"
    print(f"[OK] Verified updated recipe schema persisted: {list(recipes_after.keys())}")
    
    # 2. Test Re-init with Custom Recipe and Fleet Specs
    print("\n2. Testing POST /api/simulation/init with recipe & fleet specs ...")
    init_payload = {
        "project": "factory1",
        "map_filename": "map.json",
        "fleet_size": 4,
        "traffic_strategy": "zone",
        "routing_strategy": "dijkstra",
        "assignment_strategy": "fifo",
        "allocation_strategy": "round_robin",
        "idle_strategy": "cruising",
        "recipes": recipes_after,
        "oht_specs": {
            "length": 1.0,
            "safety_buffer": 0.5,
            "max_speed": 1.5,
            "acceleration": 0.8,
            "deceleration": 1.2
        }
    }
    init_res = http_post("/api/simulation/init", init_payload)
    assert init_res.get("status") in ["success", "ok"], f"Expected init success or ok, got {init_res}"
    print(f"[OK] Simulation reinitialized with recipes and specs: {init_res}")
    
    # 3. Test WebSocket frame arrival, server_time, and machine state distribution data
    print("\n3. Testing WebSocket /ws/simulation frame streams ...")
    async with websockets.connect(WS_URL) as ws:
        # Read 5 consecutive frames
        frames = []
        for i in range(5):
            msg = await ws.recv()
            data = json.loads(msg)
            frames.append(data)
            await asyncio.sleep(0.05)
            
        first_frame = frames[0]
        print(f"[OK] Received WebSocket frames. Keys: {list(first_frame.keys())}")
        
        # Verify server_time is present for 60fps continuous interpolation
        assert "server_time" in first_frame, "server_time MUST be in WebSocket frame for smooth rendering"
        print(f"[OK] server_time = {first_frame['server_time']}, sim_time = {first_frame['sim_time']:.3f}s")
        
        # Verify agents
        agents = first_frame.get("agents", [])
        assert len(agents) == 4, f"Expected 4 agents, got {len(agents)}"
        sample_agent = agents[0]
        for key in ["id", "x", "y", "heading", "speed", "state", "cargo"]:
            assert key in sample_agent, f"Missing key {key} in agent"
        print(f"[OK] Verified 4 agents streaming with position/heading/speed: Agent-0 at ({sample_agent['x']:.2f}, {sample_agent['y']:.2f})")
        
        # Verify machine state distribution data in metrics
        metrics = first_frame.get("metrics", {})
        machines_data = metrics.get("machines", [])
        assert len(machines_data) > 0, "Metrics must include machine list"
        sample_m = machines_data[0]
        print(f"[OK] Machine '{sample_m['id']}' state distribution: Active={sample_m['active_time']:.2f}s, Blocked={sample_m['blocked_time']:.2f}s, Starved={sample_m['starved_time']:.2f}s")
        assert "active_time" in sample_m and "blocked_time" in sample_m and "starved_time" in sample_m, "State durations must be present for SVG Donut chart"
        
    # 4. Test Headless Fast-Forward Benchmark
    print("\n4. Testing POST /api/simulation/fast_forward (60s benchmark) ...")
    t0 = time.time()
    ff_res = http_post("/api/simulation/fast_forward", {"duration": 60.0, "dt": 0.05})
    cpu_duration = time.time() - t0
    
    assert ff_res.get("status") in ["completed", "ok"], f"Expected completed or ok, got {ff_res}"
    print(f"[OK] Fast-forward executed in {cpu_duration:.3f}s CPU time!")
    print(f"  - Target Sim Time Reached: {ff_res['sim_time']:.1f}s")
    print(f"  - Total Steps Executed: {ff_res['steps_computed']}")
    print(f"  - Wall Execution Time: {cpu_duration:.4f}s (Speedup: {ff_res['duration_run'] / max(0.0001, cpu_duration):.1f}x real-time)")
    
    summary = ff_res.get("summary", {})
    print(f"  - KPI Throughput: {summary.get('throughput')} units")
    print(f"  - Fleet Avg Utilization: {summary.get('fleet_avg_utilization')}%")
    print(f"  - Machine Count: {len(summary.get('machines', []))}")
    print(f"  - Agent Count: {len(summary.get('agents', []))}")
    
    # Check machine donut data
    machs = summary.get('machines', [])
    tot_act = sum(m['active_time'] for m in machs)
    tot_blk = sum(m['blocked_time'] for m in machs)
    tot_stv = sum(m['starved_time'] for m in machs)
    print(f"[OK] Aggregate Machine State Times: Active={tot_act:.1f}s, Blocked={tot_blk:.1f}s, Starved={tot_stv:.1f}s")
    
    # 5. Check WebSocket after fast-forward to confirm live state jumped to >= 60s
    print("\n5. Checking WebSocket live state after fast-forward ...")
    async with websockets.connect(WS_URL) as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        print(f"[OK] Live WebSocket sim_time after fast forward: {data['sim_time']:.2f}s (sim is paused for user review: is_paused={data.get('is_paused')})")
        assert data['sim_time'] >= 60.0, f"Expected sim_time >= 60.0, got {data['sim_time']}"
        assert data.get('is_paused') == True, "Simulation should be automatically paused after reaching fast-forward target"
        
    print("\n=======================================================")
    print("ALL LIVE SERVER VERIFICATION CHECKS PASSED WITH 100% SUCCESS!")
    print("=======================================================")

if __name__ == "__main__":
    asyncio.run(main())
