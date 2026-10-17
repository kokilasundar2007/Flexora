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


# =====================================================
# SIDE LUNGE ANGLE CALCULATION
# =====================================================

def get_side_lunge_angles(landmarks):
    """
    Calculates working-knee angle, straight-knee angle, and torso lean
    for the side lunge exercise. Uses BOTH legs, since one bends deeply
    (working leg) while the other stays mostly straight.

    Returns a dict:
        {
            "working_knee": angle or None,
            "straight_knee": angle or None,
            "torso_lean": angle or None,
            "working_side": "left" or "right"
        }
    or None if legs aren't reliably visible.
    """

    left_shoulder = landmarks[LEFT_SHOULDER]
    right_shoulder = landmarks[RIGHT_SHOULDER]
    left_hip = landmarks[LEFT_HIP]
    right_hip = landmarks[RIGHT_HIP]
    left_knee = landmarks[LEFT_KNEE]
    right_knee = landmarks[RIGHT_KNEE]
    left_ankle = landmarks[LEFT_ANKLE]
    right_ankle = landmarks[RIGHT_ANKLE]

    required = [left_hip, right_hip, left_knee, right_knee, left_ankle, right_ankle]

    if not all(_visible(p) for p in required):
        return None

    left_knee_angle = calculate_angle(left_hip, left_knee, left_ankle)
    right_knee_angle = calculate_angle(right_hip, right_knee, right_ankle)

    if left_knee_angle is None or right_knee_angle is None:
        return None

    # The working (bent) leg has the smaller knee angle
    if left_knee_angle <= right_knee_angle:
        working_side = "left"
        working_knee_angle = left_knee_angle
        straight_knee_angle = right_knee_angle
        working_hip = left_hip
    else:
        working_side = "right"
        working_knee_angle = right_knee_angle
        straight_knee_angle = left_knee_angle
        working_hip = right_hip

    # Torso lean, using the midpoint of both shoulders vs midpoint of both hips
    mid_shoulder_x = (left_shoulder.x + right_shoulder.x) / 2
    mid_shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
    mid_hip_x = (left_hip.x + right_hip.x) / 2
    mid_hip_y = (left_hip.y + right_hip.y) / 2

    class _Point:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    mid_shoulder = _Point(mid_shoulder_x, mid_shoulder_y)
    mid_hip = _Point(mid_hip_x, mid_hip_y)
    vertical_ref = _Point(mid_hip_x, mid_hip_y - 0.5)

    torso_lean = calculate_angle(mid_shoulder, mid_hip, vertical_ref)

    return {
        "working_knee": working_knee_angle,
        "straight_knee": straight_knee_angle,
        "torso_lean": torso_lean,
        "working_side": working_side,
    }


# =====================================================
# POSTURE / FORM CHECKING
# =====================================================

STANDING_KNEE_ANGLE = 160          # both knees near straight = standing
LUNGE_DEPTH_KNEE_ANGLE = 110       # working knee must go below this
STRAIGHT_LEG_MIN_ANGLE = 150       # the non-working leg should stay close to straight
TORSO_LEAN_LIMIT = 25              # torso lean beyond this = leaning too far forward


def check_side_lunge_form(angles):
    """
    Given the angles dict from get_side_lunge_angles, returns a form status string.
    Possible values:
        "Not Detected"
        "Standing"
        "Good Form"
        "Not Deep Enough"
        "Straight Leg Not Extended"
        "Leaning Too Far Forward"
    """

    if angles is None:
        return "Not Detected"

    working_knee = angles["working_knee"]
    straight_knee = angles["straight_knee"]
    torso_lean = angles["torso_lean"]

    if working_knee is None or straight_knee is None:
        return "Not Detected"

    if working_knee >= STANDING_KNEE_ANGLE and straight_knee >= STANDING_KNEE_ANGLE:
        return "Standing"

    if torso_lean is not None and torso_lean > TORSO_LEAN_LIMIT:
        return "Leaning Too Far Forward"

    if straight_knee < STRAIGHT_LEG_MIN_ANGLE:
        return "Straight Leg Not Extended"

    if working_knee > LUNGE_DEPTH_KNEE_ANGLE:
        return "Not Deep Enough"

    return "Good Form"


# =====================================================
# REPETITION COUNTER (STATE MACHINE)
# =====================================================

class SideLungeCounter:
    """
    Tracks side lunge repetitions using a simple two-state machine:
        "up"   -> standing upright
        "down" -> in side lunge position

    A rep is counted each time the user goes down -> up.
    """

    def __init__(self):
        self.stage = "up"
        self.count = 0

    def update(self, angles):
        """
        Call this every frame with the current angles dict.
        Returns (count, stage).
        """

        if angles is None or angles["working_knee"] is None:
            return self.count, self.stage

        working_knee = angles["working_knee"]

        if working_knee <= LUNGE_DEPTH_KNEE_ANGLE:
            self.stage = "down"

        elif working_knee >= STANDING_KNEE_ANGLE and self.stage == "down":
            self.stage = "up"
            self.count += 1

        return self.count, self.stage

    def reset(self):
        self.stage = "up"
        self.count = 0