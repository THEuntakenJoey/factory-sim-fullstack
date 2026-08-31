import argparse
import random
from matplotlib.animation import FuncAnimation
import matplotlib.pyplot as plt

from map_manager import MapManager
from agent import OHTAgent
from map_drawer import MapVisualizer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("map_json", help="Path to json")
    parser.add_argument("--start_id", type=int, help="Start Node ID")
    parser.add_argument("--end_id", type=int, help="End Node ID")
    parser.add_argument("--debug", action="store_true", help="Slow motion mode")
    args = parser.parse_args()

    # Init Logic
    mgr = MapManager(args.map_json)
    bot = OHTAgent(mgr)
    viz = MapVisualizer(mgr)

    time_scale = 1.0
    if args.start_id is not None and args.end_id is not None:
        bot.set_mission(args.start_id, args.end_id)
        if args.debug: time_scale = 0.1
    else:
        # Default Random Init
        start_wp = list(mgr.waypoints.keys())[0]
        start_id = mgr.waypoints[start_wp]
        bot.set_mission(start_id, start_id)

    def loop(frame):
        dt = 0.05 * time_scale

        # Auto-Random Mission
        if args.start_id is None and (bot.state == "IDLE"):
            curr_node = mgr.segments[bot.current_seg]['v']
            opts = [nid for nid in mgr.waypoints.values() if nid != curr_node]
            if opts:
                dest_id = random.choice(opts)
                bot.set_mission(curr_node, dest_id)
                viz.set_target_dot(dest_id)

        bot.update(dt)
        return viz.update(bot)

    ani = FuncAnimation(viz.fig, loop, interval=30, blit=True, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    main()