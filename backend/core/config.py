OHT_SPECS = {
    # Geometry in meters and mm
    "length_m": 1.0,           # 1.0 meter OHT length
    "width_m": 0.4,            # 0.4 meter OHT width
    "buffer_m": 0.2,           # 0.2 meter safety buffer
    "min_section_len_m": 1.2,  # 1.2 meter minimum section length (length + buffer)

    # Geometry in mm (legacy & visual compatibility)
    "offsets": {
        "Preceding": 600.0,
        "Front": 500.0,
        "Center": 0.0,
        "Rear": -500.0,
        "Following": -600.0
    },
    "width": 400.0,

    # Motor Limits (mm/s and m/s)
    "speed_max": 2000.0,       # 2.0 m/s
    "speed_crawl": 300.0,      # 0.3 m/s
    "speed_curve": 800.0,      # 0.8 m/s

    # Dynamics (mm/s^2 and m/s^2)
    "accel": 1500.0,           # 1.5 m/s^2
    "decel": 2000.0,           # 2.0 m/s^2

    # Motion Helper Settings (mm, s)
    "stop_buffer": 2.0,
    "linear_stop_dist": 50.0,
    "wait_time": 1.5,
    
    "safety": {
        "min_lookahead_obs": 3000.0,
        "min_lookahead_zone": 500.0,
        "buffer_stop_obs": 2000.0,
        "buffer_stop_zone": 1000.0,
        "gap_maintained": 200.0,
        "gap_yield": 500.0,
        "merge_relevance_dist": 2000.0,
        "merge_tie_epsilon": 50.0,
    }
}

def get_oht_specs() -> dict:
    return OHT_SPECS

def update_oht_specs(new_specs: dict):
    global OHT_SPECS
    if not new_specs:
        return
    for k, v in new_specs.items():
        if k in OHT_SPECS:
            OHT_SPECS[k] = v
    if "length_m" in new_specs or "buffer_m" in new_specs:
        l = OHT_SPECS.get("length_m", 1.0)
        b = OHT_SPECS.get("buffer_m", 0.2)
        OHT_SPECS["min_section_len_m"] = l + b
        half_mm = (l * 1000.0) / 2.0
        buf_mm = (b * 1000.0)
        OHT_SPECS["offsets"]["Front"] = half_mm
        OHT_SPECS["offsets"]["Rear"] = -half_mm
        OHT_SPECS["offsets"]["Preceding"] = half_mm + buf_mm
        OHT_SPECS["offsets"]["Following"] = -(half_mm + buf_mm)