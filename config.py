OHT_SPECS = {
    # Geometry (120mm wheelbase)
    "offsets": {
        "Preceding": 400.0,
        "Front": 200.0,
        "Center": 0.0,
        "Rear": -200.0,
        "Following": -400.0
    },
    "width": 500.0,
    # Motor Limits (mm/s)
    "speed_max": 2000.0,
    "speed_crawl": 300.0,
    "speed_curve": 800.0,
    # Dynamics (mm/s^2)
    "accel": 1500.0,
    "decel": 2000.0,
    # Motion Helper Settings (mm, s)
    "stop_buffer": 2.0,
    "linear_stop_dist": 50.0,
    "wait_time": 1.5,
    
    "safety": {
        # Minimum lookahead for obstacles (even if stopped)
        "min_lookahead_obs": 3000.0,
        # Minimum lookahead for zones (e.g. check slightly ahead of nose)
        "min_lookahead_zone": 500.0,
       
        # Buffer added to physical stopping distance
        "buffer_stop_obs": 2000.0,
        "buffer_stop_zone": 1000.0,
       
        # Physical gap to maintain between cars (500mm)
        "gap_maintained": 500.0,
       
        # Distance to stop before a merge point if yeild
        "gap_yield": 500.0,

        "merge_relevance_dist": 2000.0,
        "merge_tie_epsilon": 50.0,
    }
}