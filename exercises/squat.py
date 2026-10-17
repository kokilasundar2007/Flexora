import math


# =====================================================
# LANDMARK INDICES (MediaPipe Pose)
# =====================================================

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28

VISIBILITY_THRESHOLD = 0.5


# =====================================================
# GENERIC ANGLE HELPER
# =====================================================

def calculate_angle(a, b, c):
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    cx, cy = c.x, c.y

    ba = (ax - bx, ay - by)
    bc = (cx - bx, cy - by)

    dot = ba[0] * bc[0] + ba[1] * bc[1]

    mag_ba = math.hypot(ba[0], ba[1])
    mag_bc = math.hypot(bc[0], bc[1])

    if mag_ba == 0 or mag_bc == 0:
        return None

    cos_angle = dot / (mag_ba * mag_bc)
    cos_angle = max(-1.0, min(1.0, cos_angle))

    angle = math.degrees(math.acos(cos_angle))

    return angle


def _visible(landmark):
    visibility = getattr(landmark, "visibility", 1.0)
    return visibility is not None and visibility >= VISIBILITY_THRESHOLD


def _pick_side(landmarks):
    left_points = [
        landmarks[LEFT_SHOULDER],
        landmarks[LEFT_HIP],
        landmarks[LEFT_KNEE],
        landmarks[LEFT_ANKLE],
    ]

    right_points = [
        landmarks[RIGHT_SHOULDER],
        landmarks[RIGHT_HIP],
        landmarks[RIGHT_KNEE],
        landmarks[RIGHT_ANKLE],
    ]

    left_ok = all(_visible(p) for p in left_points)
    right_ok = all(_visible(p) for p in right_points)

    if left_ok and right_ok:
        left_avg = sum(getattr(p, "visibility", 1.0) for p in left_points) / 4
        right_avg = sum(getattr(p, "visibility", 1.0) for p in right_points) / 4
        return "left" if left_avg >= right_avg else "right"

    if left_ok:
        return "left"

    if right_ok:
        return "right"

    return None


# =====================================================
# FRONT/SIDE ORIENTATION CHECK
# =====================================================

SIDEWAYS_SHOULDER_THRESHOLD = 0.10  # normalized x-distance; tune if needed


def is_facing_sideways(landmarks):
    """
    Returns True if sideways enough, False if too front-facing,
    or None if shoulders aren't visible.
    """

    left_shoulder = landmarks[LEFT_SHOULDER]
    right_shoulder = landmarks[RIGHT_SHOULDER]

    if not (_visible(left_shoulder) and _visible(right_shoulder)):
        return None

    shoulder_distance = abs(left_shoulder.x - right_shoulder.x)

    return shoulder_distance <= SIDEWAYS_SHOULDER_THRESHOLD


# =====================================================
# SQUAT ANGLE CALCULATION
# =====================================================

def get_squat_angles(landmarks):
    side = _pick_side(landmarks)

    if side is None:
        return None

    if side == "left":
        shoulder = landmarks[LEFT_SHOULDER]
        hip = landmarks[LEFT_HIP]
        knee = landmarks[LEFT_KNEE]
        ankle = landmarks[LEFT_ANKLE]
    else:
        shoulder = landmarks[RIGHT_SHOULDER]
        hip = landmarks[RIGHT_HIP]
        knee = landmarks[RIGHT_KNEE]
        ankle = landmarks[RIGHT_ANKLE]

    knee_angle = calculate_angle(hip, knee, ankle)
    hip_angle = calculate_angle(shoulder, hip, knee)

    try:
        vertical_ref = type(hip)(x=hip.x, y=hip.y - 0.5, z=getattr(hip, "z", 0.0))
    except Exception:
        vertical_ref = None

    back_angle = None
    if vertical_ref is not None:
        back_angle = calculate_angle(shoulder, hip, vertical_ref)

    return {
        "side": side,
        "knee": knee_angle,
        "hip": hip_angle,
        "back": back_angle,
    }


# =====================================================
# POSTURE / FORM CHECKING
# =====================================================

STANDING_KNEE_ANGLE = 160
SQUAT_DEPTH_KNEE_ANGLE = 120
BACK_LEAN_LIMIT = 45


def check_squat_form(angles):
    if angles is None:
        return "Not Detected"

    knee = angles["knee"]
    back = angles["back"]

    if knee is None:
        return "Not Detected"

    if knee >= STANDING_KNEE_ANGLE:
        return "Standing"

    if back is not None and back > BACK_LEAN_LIMIT:
        return "Leaning Too Far Forward"

    if knee > SQUAT_DEPTH_KNEE_ANGLE:
        return "Not Deep Enough"

    return "Good Form"


# =====================================================
# REPETITION COUNTER (STATE MACHINE)
# =====================================================

class SquatCounter:
    def __init__(self):
        self.stage = "up"
        self.count = 0

    def update(self, angles):
        if angles is None or angles["knee"] is None:
            return self.count, self.stage

        knee = angles["knee"]

        if knee <= SQUAT_DEPTH_KNEE_ANGLE:
            self.stage = "down"

        elif knee >= STANDING_KNEE_ANGLE and self.stage == "down":
            self.stage = "up"
            self.count += 1

        return self.count, self.stage

    def reset(self):
        self.stage = "up"
        self.count = 0