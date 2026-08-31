# OHT-Kinematic

**OHT-Kinematic** is a Python-based kinematic simulation environment designed to model, visualize, and test the behavior of Overhead Hoist Transport (OHT) systems. These systems are commonly deployed in automated factories and semiconductor fabrication plants (Fabs) for material handling.

This project simulates bot movement along a track network, collision avoidance, speed control, and higher-level dispatching logic through simulated Manufacturing Execution Systems (MES) and Material Control Systems (MCS).

## Requirements
- Python >= 3.13
- Dependencies: `matplotlib`, `numpy` (Managed via `uv` / `pyproject.toml`)

## Project Structure

### Core Simulation
- **`main.py`**: The primary entry point. Launches a basic simulation with an agent navigating the track.
- **`agent.py`**: Defines the physical and logical behavior of the OHT bots (`OHTAgent`), including path traversal (`GraphWalker`) and velocity control (`SpeedController`).
- **`map_manager.py`**: Loads and manages the factory track layout (nodes, segments, and waypoints) parsed from JSON maps.
- **`virtual_objects.py`**: Defines factory-specific entities that interact with the bots, such as `Lot` (materials), `Container`, `MachinePort`, and `VirtualMachine`.

### Control Systems & Logistics
- **`systems.py`**: Contains higher-level coordination logic:
  - `VirtualMES`: Simulates the Manufacturing Execution System to generate transport requests.
  - `VirtualMCS`: Simulates the Material Control System to assign tasks and coordinate bot dispatching.
- **`traffic.py`**: Handles traffic management (`TrafficRegistry`) to prevent collisions and coordinate multiple bots on the track.

### Visualization & Testing
- **`map_drawer.py` & `track_viewer.py`**: Utilize `matplotlib` to render the track map, waypoints, gradients, and animate agent movements.
- **`sandbox.py`**: A playground script featuring a `DashboardApp` for interactive monitoring and complex simulation testing.
- **`test_scenarios.py`**: Defines and runs specific scenario tests (e.g., `AdvancedScenarioRunner`) to validate logic under various load conditions.

### Data & Configuration
- **`map.json` / `map_v0.json`**: Graph data structures defining the track layouts.
- **`scenarios.json`**: Defines test scenarios and load conditions.
- **`machine_schema.json` / `machine_types.csv`**: Schema and configurations for the virtual machines.

## Usage

Run the basic visualization by passing a map JSON file to `main.py`:

```bash
python main.py map.json
```

**Optional Arguments:**
- `--start_id <ID>`: Specify a starting node ID.
- `--end_id <ID>`: Specify a destination node ID.
- `--debug`: Enable slow-motion mode.
