import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.state import FactoryState

project_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'projects', 'factory1')
state = FactoryState(project_dir, "map.json", fleet_size=4)

print("--- Graph Adjacency List ---")
for u, edges in state.map_mgr.graph.items():
    if edges:
        edge_str = ", ".join(f"->{v} ({seg})" for v, seg, w in edges)
        print(f"Node {u} (pos {state.map_mgr.nodes[u][:2]}): {edge_str}")
    else:
        print(f"Node {u} (pos {state.map_mgr.nodes[u][:2]}): DEAD END (no outgoing edges)")
