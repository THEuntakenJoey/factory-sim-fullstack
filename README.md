# FactorySim Full Stack

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB.svg)](https://react.dev/)
[![WebSocket](https://img.shields.io/badge/RealTime-WebSocket-orange.svg)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
[![Package Manager](https://img.shields.io/badge/uv-Package%20Manager-2C8EBB.svg)](https://astral.sh/uv)

**FactorySim Full Stack** is a high-performance, full-stack digital twin and simulation platform for **Overhead Hoist Transport (OHT)** and **Automated Material Handling Systems (AMHS)** commonly deployed in semiconductor wafer fabs and automated manufacturing facilities.

It couples a continuous **second-order kinematic physics engine** with a **discrete-event simulation (DES) fab logistics layer**, an interactive **browser-based CAD track builder**, advanced **fleet dispatching & idle parking strategies**, and **real-time bottleneck / backpressure analytics**.

---

## Key Features

### 1. Hybrid Simulation Engine (Kinematics + Discrete Event Logistics)
- **Continuous 2nd-Order Kinematics**:
  - Realistic motion profiling with acceleration limits, deceleration profiles, maximum operational speeds, and turn-rate speed adjustments.
  - Dynamic distance headway following models to prevent collisions and simulate realistic bumper-to-bumper queueing.
  - Multi-segment trajectory calculation along straight segments and Bezier curves.
- **Fab Logistics & DES (Manufacturing Execution / Material Control)**:
  - Equipment modeling: `Source`, `Process`, `Sink`, and buffer stations.
  - Four-state machine tracking: `PROCESSING`, `STARVED`, `BLOCKED`, and `IDLE`.
  - Multi-stage manufacturing recipes with step-by-step carrier routing and lot lifecycle management.
  - Automated transfer hoist operations (pickup, dropoff, transfer delays).

### 2. Intelligent Fleet Dispatching & Idle Management
- **Smart Dispatcher**:
  - Distance-optimal Dijkstra shortest path routing.
  - Urgency-based task allocation prioritizing blocked upstream equipment and starved bottlenecks.
- **Dedicated Idle Bot Strategies**:
  - `STATIONARY_PARK`: Retain current position upon task completion.
  - `NEAREST_DEDICATED_STUB`: Automatically route idle OHT vehicles to designated off-mainline parking spurs, clearing main track throughput.
  - `DISTRIBUTED_DEPOT`: Disperse idle vehicles uniformly across available holding tracks.
  - `HEATMAP_ANTICIPATION`: Stage idle carriers near predicted high-demand pickup nodes.

### 3. Factory Analytics & Backpressure Diagnostics
- **Little's Law Metrics**:
  - Real-time throughput (units/hour), total production count, average transport cycle time, and Work-In-Progress (WIP).
- **Equipment Utilization Decomposition**:
  - Real-time time attribution: active processing vs. starved (upstream delays) vs. blocked (downstream or transport backpressure).
- **OHT Fleet Telemetry**:
  - Individual vehicle time distribution: loaded transport, empty dispatch traversal, queue waiting, and idle parking.
  - Cumulative distance traveled and individual operational efficiency.
- **Track Heatmaps & Jam Analytics**:
  - Traversal heatmaps and cumulative blockage duration overlay to instantly pinpoint congestion points and track pinch bottlenecks.
- **Headless Fast-Forward Engine**:
  - Execute headless batch simulations at **>5000x real-time speed** to quickly forecast long-term system performance and validate track layouts.

### 4. Interactive Web CAD Studio & Visualizer
- **Track Map Builder**:
  - Interactive HTML5 canvas with pan/zoom, grid snapping, node creation, segment routing, curve tension editing, and one-way directional flow toggles.
- **Machine Designer**:
  - Visual placement of machines, input/output load ports, process times, and stub connection assignments.
- **Recipe Manager**:
  - Dynamic configuration of wafer processing workflows, schema steps, and batch lot parameters.
- **Real-Time Simulation View**:
  - Bi-directional WebSocket synchronization streaming full vehicle states, machine statuses, and factory metrics at high frame rates.
  - Interactive camera tracking (Follow Bot mode, free pan, smooth zoom).
  - Variable playback speed (0.1x up to 10x) and instant headless fast-forwarding (1m, 5m, 15m, 30m).
  - Multi-project save, load, and JSON export capabilities.

---

## System Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend Web Application (React + Canvas + Tailwind)"]
        MB["Map Builder (CAD)"]
        MD["Machine Designer"]
        RM["Recipe Manager"]
        SIM["Simulation Canvas & Heatmaps"]
        DASH["Analytics Dashboard & Little's Law"]
        WS_C["WebSocket Client"]
        API_C["REST API Client"]
    end

    subgraph Backend["FastAPI Backend (Python 3.13+)"]
        API_S["REST API Server (/api/...)"]
        WS_S["WebSocket Hub (/ws/...)"]
        MM["Map & Project Manager"]
        
        subgraph SimEngine["Hybrid Simulation Engine"]
            SE["Engine Controller"]
            FS["Factory State & Clock"]
            PHYS["Kinematics & Collision Avoider"]
            DES["Discrete Event Machine & Lot Manager"]
            DISP["Fleet Dispatcher"]
            IDLE["Idle Parking Coordinator"]
            METRICS["Bottleneck & Jam Analytics Engine"]
        end
    end

    API_C <-->|Project Schemas, Config, Fast-Forward| API_S
    WS_C <-->|Live Telemetry (60Hz), Commands| WS_S
    API_S --> MM
    WS_S <--> SE
    SE --> PHYS
    SE --> DES
    SE --> DISP
    SE --> IDLE
    SE --> METRICS
    SE --> FS
```

---

## Directory Structure

```text
factory-sim-fullstack/
├── backend/
│   ├── main.py                     # FastAPI application & WebSocket server
│   ├── core/
│   │   ├── config.py               # Global simulation parameters & kinematics config
│   │   ├── engine.py               # Core step loop & headless fast-forward executor
│   │   ├── state.py                # Central FactoryState (vehicles, machines, lots, tracks)
│   │   └── map_manager.py          # Node/segment graph management & Dijkstra pathfinding
│   ├── models/
│   │   ├── vehicles.py             # OHT agent kinematics, motion profiles & sensors
│   │   └── devices.py              # Virtual machines, ports, lots, recipes & state machines
│   ├── routing/
│   │   ├── dispatcher.py           # OHT task assignment and priority queueing
│   │   ├── idle_strategies.py      # Dedicated stub & depot parking policies
│   │   ├── strategies.py           # Dispatch heuristics (nearest, urgent, balanced)
│   │   └── interfaces.py           # Routing protocol abstractions
│   ├── metrics/
│   │   └── analytics.py            # Bottleneck detector, utilization, Little's Law, heatmaps
│   └── projects/
│       └── factory1/               # Default factory project schemas
│           ├── maps/               # Track nodes & segments JSON
│           └── schema/             # Machines, ports, and recipe definitions JSON
├── frontend/
│   ├── index.html                  # Main SPA entry point & styling
│   └── js/
│       ├── api.js                  # REST & WebSocket communications client
│       └── components/
│           ├── App.jsx             # Root application & topbar navigation
│           ├── MapBuilderTab.jsx   # Track CAD layout designer
│           ├── MachineDesignerTab.jsx # Machine & port configuration
│           ├── RecipeManagerTab.jsx# Recipe workflow builder
│           ├── SimulationTab.jsx   # Live simulation, camera & analytics dashboard
│           └── CommonControls.jsx  # Reusable UI widgets
├── dev/
│   ├── test_event_analytics.py     # Automated unit test for bottleneck & Little's Law metrics
│   ├── test_recipe_and_fastforward.py # Benchmark for fast-forward speed & recipe fallback
│   ├── test_live_server_endpoints.py # Integration test for REST & WS endpoints
│   └── test_v1_architecture.py     # End-to-end simulation sanity test
├── pyproject.toml                  # Python package specifications & dependencies
├── README.md                       # Project documentation
└── uv.lock                         # Pinned dependency lockfile
```

---

## Getting Started

### Prerequisites
- **Python 3.13+** installed.
- **[uv](https://astral.sh/uv)** installed (recommended fast package installer).

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/THEuntakenJoey/factory-sim-fullstack.git
   cd factory-sim-fullstack
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

### Running the Application

Start the FastAPI server with hot-reload enabled:

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

Open your browser and navigate to:
```text
http://localhost:8000
```

---

## User Guide

### 1. Map Builder
- **Navigate Canvas**: Left-click and drag on empty canvas to pan; scroll wheel to zoom.
- **Add Nodes & Tracks**: Click **Add Node** to place intersection/station waypoints, or select a node and click **Extrude** to create connected track segments.
- **Curves & Stubs**: Select a segment to toggle curve handles or mark it as a **Dedicated Parking Stub** for idle vehicles.

### 2. Machine Designer
- Place **Source**, **Process**, and **Sink** tools on your layout.
- Bind input/output load ports to adjacent track nodes to enable OHT hoists to transfer carriers.
- Configure processing cycle times (mean & variance) for each equipment type.

### 3. Recipe Manager
- Formulate sequential wafer routing recipes (e.g. `Raw Wafer -> Lithography -> Etch -> Inspection -> Output Sink`).
- Assign equipment capabilities to schemas so the dispatch engine can dynamically route lots to available qualifying machines.

### 4. Simulation & Analytics Dashboard
- **Controls**: Press **Play / Pause**, adjust playback speed (0.1x to 10x), or click **Reset**.
- **Fast-Forward**: Use the fast-forward dropdown (`1m`, `5m`, `15m`, `30m`) to advance the factory state at >5000x real-time speed.
- **Follow Bot**: Click on any OHT vehicle in the viewport or in the fleet card to lock the viewport camera onto it.
- **Bottleneck Diagnostics**: View live Little's Law throughput, machine time breakdown (Active / Starved / Blocked), and toggle track traversal heatmaps to detect congestion hot spots.

---

## Testing & Benchmarks

Automated test scripts are provided in the `dev/` directory:

```bash
# Verify Little's Law metrics, machine states, and track jam accumulation
uv run python dev/test_event_analytics.py

# Benchmark the headless fast-forward simulation engine (>5000x real-time)
uv run python dev/test_recipe_and_fastforward.py

# Verify end-to-end full stack architecture
uv run python dev/test_v1_architecture.py
```

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.
