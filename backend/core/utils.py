import numpy as np
import math

def normalize(vec):
    """Safely normalizes a vector, returning (1,0,0) if length is 0."""
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else np.array([1.0, 0.0, 0.0])

def dist_sq(a, b):
    """Squared Euclidean distance (faster than sqrt)."""
    return np.sum((a - b)**2)

def quaternion_to_angle(quat):
    """Placeholder if you move to full 3D engine later."""
    # Assuming quat is [w, x, y, z] or similar
    # For now, unused in 2D plot
    pass

def vector_to_angle(forward_vector):
    """
    Converts a 3D forward vector to a 2D rotation angle (radians).
    Useful for matplotlib markers.
    """
    return math.atan2(forward_vector[1], forward_vector[0])
