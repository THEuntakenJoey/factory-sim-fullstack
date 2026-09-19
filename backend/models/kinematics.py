import math
from typing import Dict, Any, Tuple

def solve_kinematic_motion(
    distance_m: float,
    v0: float,
    vf: float,
    v_limit: float,
    accel: float = 1.5,
    decel: float = 2.0
) -> Dict[str, Any]:
    """
    Computes closed-form trapezoidal or triangular kinematic motion profile for a segment.
    All distance units in meters, velocity in m/s, accel/decel in m/s^2, time in seconds.
    """
    S = max(0.001, distance_m)
    v0 = max(0.0, min(v0, v_limit))
    vf = max(0.0, min(vf, v_limit))
    v_limit = max(0.01, v_limit)

    # 1. Pure decel check: what if even direct decel from v0 to vf needs >= S?
    if v0 > vf:
        min_decel_dist = (v0**2 - vf**2) / (2 * decel)
        if min_decel_dist >= S:
            # Need to decel as hard as possible
            actual_vf = math.sqrt(max(0.0, v0**2 - 2 * decel * S))
            t_decel = (v0 - actual_vf) / decel if decel > 0 else 0.1
            return {
                "S": S,
                "v0": v0,
                "vf": actual_vf,
                "v_peak": v0,
                "s1": 0.0, "s2": 0.0, "s3": S,
                "t1": 0.0, "t2": 0.0, "t3": t_decel,
                "duration": t_decel,
                "accel": accel,
                "decel": decel
            }

    # 2. Check if we can reach v_limit
    s_acc = max(0.0, v_limit**2 - v0**2) / (2 * accel)
    s_dec = max(0.0, v_limit**2 - vf**2) / (2 * decel)

    if s_acc + s_dec <= S:
        # Trapezoidal Profile (reaches v_limit)
        v_peak = v_limit
        s1 = s_acc
        s3 = s_dec
        s2 = S - (s1 + s3)
        t1 = (v_peak - v0) / accel if accel > 0 else 0.0
        t2 = s2 / v_peak if v_peak > 0 else 0.0
        t3 = (v_peak - vf) / decel if decel > 0 else 0.0
        total_time = t1 + t2 + t3
        return {
            "S": S,
            "v0": v0,
            "vf": vf,
            "v_peak": v_peak,
            "s1": s1, "s2": s2, "s3": s3,
            "t1": t1, "t2": t2, "t3": t3,
            "duration": total_time,
            "accel": accel,
            "decel": decel
        }
    else:
        # Triangular Profile (peaks at v_peak < v_limit)
        num = 2 * accel * decel * S + decel * (v0**2) + accel * (vf**2)
        den = accel + decel
        v_peak_sq = max(0.0, num / den)
        v_peak = math.sqrt(v_peak_sq)

        # Ensure peak does not drop below max(v0, vf)
        v_peak = max(v_peak, max(v0, vf))
        v_peak = min(v_peak, v_limit)

        s1 = max(0.0, v_peak**2 - v0**2) / (2 * accel)
        s3 = max(0.0, v_peak**2 - vf**2) / (2 * decel)
        s2 = max(0.0, S - (s1 + s3))

        t1 = (v_peak - v0) / accel if accel > 0 else 0.0
        t2 = s2 / v_peak if (s2 > 0 and v_peak > 0) else 0.0
        t3 = (v_peak - vf) / decel if decel > 0 else 0.0
        total_time = max(0.001, t1 + t2 + t3)

        return {
            "S": S,
            "v0": v0,
            "vf": vf,
            "v_peak": v_peak,
            "s1": s1, "s2": s2, "s3": s3,
            "t1": t1, "t2": t2, "t3": t3,
            "duration": total_time,
            "accel": accel,
            "decel": decel
        }

def interpolate_motion(profile: Dict[str, Any], tau: float) -> Tuple[float, float]:
    """
    Given an active profile and elapsed time tau in [0, duration],
    returns (distance_traveled_mm, current_velocity_mm_s).
    """
    tau = max(0.0, min(tau, profile["duration"]))
    t1 = profile["t1"]
    t2 = profile["t2"]
    t3 = profile["t3"]
    v0 = profile["v0"]
    vf = profile["vf"]
    v_peak = profile["v_peak"]
    accel = profile["accel"]
    decel = profile["decel"]
    s1 = profile["s1"]
    s2 = profile["s2"]
    S = profile["S"]

    if tau <= t1 and t1 > 0:
        # Phase 1: Accel
        dist = v0 * tau + 0.5 * accel * (tau**2)
        vel = v0 + accel * tau
    elif tau <= (t1 + t2):
        # Phase 2: Cruise
        tau_c = tau - t1
        dist = s1 + v_peak * tau_c
        vel = v_peak
    else:
        # Phase 3: Decel
        tau_d = tau - (t1 + t2)
        dist = s1 + s2 + v_peak * tau_d - 0.5 * decel * (tau_d**2)
        vel = max(vf, v_peak - decel * tau_d)

    return max(0.0, min(dist, S)), max(0.0, vel)
