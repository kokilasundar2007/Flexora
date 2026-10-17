import math


# =====================================================
# LANDMARK INDICES (MediaPipe Pose)
# =====================================================

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24

VISIBILITY_THRESHOLD = 0.5


# =====================================================
# GENERIC ANGLE HELPER
# =====================================================

def calculate_angle(a, b, c):
    """
    Calculates the angle at point b, formed by points a-b-c.
    Each point must have .x and .y attributes (normalized coords).
    Returns the angle in degrees (0-180).
    """

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
    """
    Checks whether a landmark is visible enough to trust.
    """

    visibility = getattr(landmark, "visibility", 1.0)
    return visibility is not None and visibility >= VISIBILITY_THRESHOLD


def _pick_side(landmarks):
    """
    Decides which arm (left/right) is more visible.
    Returns "left", "right", or None if neither side is usable.
    """

    left_points = [
        landmarks[LEFT_SHOULDER],
        landmarks[LEFT_ELBOW],
        landmarks[LEFT_WRIST],
        landmarks[LEFT_HIP],
    ]

    right_points = [
        landmarks[RIGHT_SHOULDER],
        landmarks[RIGHT_ELBOW],
        landmarks[RIGHT_WRIST],
        landmarks[RIGHT_HIP],
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
# SHOULDER PRESS ANGLE CALCULATION
# =====================================================

def get_press_angles(landmarks):
    """
    Calculates elbow angle and torso lean angle for shoulder press.
    Automatically chooses the more visible arm.

    Returns a dict:
        {
            "side": "left" or "right",
            "elbow": angle or None,
            "torso_lean": angle or None
        }
    or None if not reliably visible.
    """

    side = _pick_side(landmarks)

    if side is None:
        return None

    if side == "left":
        shoulder = landmarks[LEFT_SHOULDER]
        elbow = landmarks[LEFT_ELBOW]
        wrist = landmarks[LEFT_WRIST]
        hip = landmarks[LEFT_HIP]
    else:
        shoulder = landmarks[RIGHT_SHOULDER]
        elbow = landmarks[RIGHT_ELBOW]
        wrist = landmarks[RIGHT_WRIST]
        hip = landmarks[RIGHT_HIP]

    # Elbow angle: shoulder - elbow - wrist
    elbow_angle = calculate_angle(shoulder, elbow, wrist)

    # Torso lean: vertical reference above hip, angle measured at hip
    try:
        vertical_ref = type(hip)(
            x=hip.x,
            y=hip.y - 0.5,
            z=getattr(hip, "z", 0.0)
        )
    except Exception:
        vertical_ref = None

    torso_lean = None
    if vertical_ref is not None:
        torso_lean = calculate_angle(shoulder, hip, vertical_ref)

    return {
        "side": side,
        "elbow": elbow_angle,
        "torso_lean": torso_lean,
    }


# =====================================================
# POSTURE / FORM CHECKING
# =====================================================

ARM_TOP_ANGLE = 160          # elbow angle when arms fully pressed overhead
ARM_BOTTOM_ANGLE = 90        # elbow angle at starting/bottom position
TORSO_LEAN_LIMIT = 20        # torso lean beyond this = leaning back to cheat


def check_press_form(angles):
    """
    Given the angles dict from get_press_angles, returns a form status string.
    Possible values:
        "Not Detected"
        "Bottom Position"
        "Pressing"
        "Good Rep"
        "Leaning Back"
    """

    if angles is None:
        return "Not Detected"

    elbow = angles["elbow"]
    torso_lean = angles["torso_lean"]

    if elbow is None:
        return "Not Detected"

    if torso_lean is not None and torso_lean > TORSO_LEAN_LIMIT:
        return "Leaning Back"

    if elbow <= ARM_BOTTOM_ANGLE:
        return "Bottom Position"

    if elbow >= ARM_TOP_ANGLE:
        return "Good Rep"

    return "Pressing"


# =====================================================
# REPETITION COUNTER (STATE MACHINE)
# =====================================================

class PressCounter:
    """
    Tracks shoulder press repetitions using a simple two-state machine:
        "down" -> arms bent at shoulder height (starting position)
        "up"   -> arms extended overhead

    A rep is counted each time the user goes up -> down
    (completes a full press-and-return cycle).
    """

    def __init__(self):
        self.stage = "down"
        self.count = 0

    def update(self, angles):
        """
        Call this every frame with the current angles dict.
        Returns (count, stage).
        """

        if angles is None or angles["elbow"] is None:
            return self.count, self.stage

        elbow = angles["elbow"]

        # Transition to "up" once arms reach full extension overhead
        if elbow >= ARM_TOP_ANGLE:
            self.stage = "up"

        # Transition back to "down" -> completes one rep
        elif elbow <= ARM_BOTTOM_ANGLE and self.stage == "up":
            self.stage = "down"
            self.count += 1

        return self.count, self.stage

    def reset(self):
        self.stage = "down"
        self.count = 0