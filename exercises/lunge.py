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
# ORIENTATION CHECK (lunges need a side view, like squats)
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
# LUNGE ANGLE CALCULATION
# =====================================================

def get_lunge_angles(landmarks):
    """
    Calculates front-knee angle, back-knee angle, and torso lean
    for the lunge exercise. Uses BOTH legs, since a lunge inherently
    involves one leg forward and one leg back.

    Returns a dict:
        {
            "front_knee": angle or None,
            "back_knee": angle or None,
            "torso_lean": angle or None,
            "front_leg": "left" or "right",
            "back_leg": "left" or "right"
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

    # Angle at each knee: hip - knee - ankle
    left_knee_angle = calculate_angle(left_hip, left_knee, left_ankle)
    right_knee_angle = calculate_angle(right_hip, right_knee, right_ankle)

    # The back knee drops lower toward the floor during a lunge,
    # so it has a larger y value (y increases downward in image coords).
    if left_knee.y > right_knee.y:
        back_leg = "left"
        front_leg = "right"
        back_knee_angle = left_knee_angle
        front_knee_angle = right_knee_angle
        front_hip = right_hip
        front_shoulder = right_shoulder
    else:
        back_leg = "right"
        front_leg = "left"
        back_knee_angle = right_knee_angle
        front_knee_angle = left_knee_angle
        front_hip = left_hip
        front_shoulder = left_shoulder

    # Torso lean: measured at the front hip, between the front shoulder
    # and a vertical reference point directly above the hip.
    # Same technique used in squat.py for the back angle.
    try:
        vertical_ref = type(front_hip)(
            x=front_hip.x,
            y=front_hip.y - 0.5,
            z=getattr(front_hip, "z", 0.0)
        )
    except Exception:
        vertical_ref = None

    torso_lean = None
    if vertical_ref is not None:
        torso_lean = calculate_angle(front_shoulder, front_hip, vertical_ref)

    return {
        "front_knee": front_knee_angle,
        "back_knee": back_knee_angle,
        "torso_lean": torso_lean,
        "front_leg": front_leg,
        "back_leg": back_leg,
    }


# =====================================================
# POSTURE / FORM CHECKING
# =====================================================

STANDING_KNEE_ANGLE = 160        # both knees roughly straight = standing
LUNGE_DEPTH_KNEE_ANGLE = 110     # front knee must go below this to count as good depth
BACK_KNEE_BEND_ANGLE = 120       # back knee must also bend below this
TORSO_LEAN_LIMIT = 30            # torso lean beyond this = leaning too far forward


def check_lunge_form(angles):
    """
    Given the angles dict from get_lunge_angles, returns a form status string.
    Possible values:
        "Not Detected"
        "Standing"
        "Good Form"
        "Front Knee Not Deep Enough"
        "Back Knee Not Bent Enough"
        "Leaning Too Far Forward"
    """

    if angles is None:
        return "Not Detected"

    front_knee = angles["front_knee"]
    back_knee = angles["back_knee"]
    torso_lean = angles["torso_lean"]

    if front_knee is None or back_knee is None:
        return "Not Detected"

    if front_knee >= STANDING_KNEE_ANGLE and back_knee >= STANDING_KNEE_ANGLE:
        return "Standing"

    if torso_lean is not None and torso_lean > TORSO_LEAN_LIMIT:
        return "Leaning Too Far Forward"

    if front_knee > LUNGE_DEPTH_KNEE_ANGLE:
        return "Front Knee Not Deep Enough"

    if back_knee > BACK_KNEE_BEND_ANGLE:
        return "Back Knee Not Bent Enough"

    return "Good Form"


# =====================================================
# REPETITION COUNTER (STATE MACHINE)
# =====================================================

class LungeCounter:
    """
    Tracks lunge repetitions using a simple two-state machine:
        "up"   -> standing upright
        "down" -> in lunge position

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

        if angles is None or angles["front_knee"] is None:
            return self.count, self.stage

        front_knee = angles["front_knee"]

        # Transition to "down" once front knee bends past lunge depth
        if front_knee <= LUNGE_DEPTH_KNEE_ANGLE:
            self.stage = "down"

        # Transition back to "up" -> completes one rep
        elif front_knee >= STANDING_KNEE_ANGLE and self.stage == "down":
            self.stage = "up"
            self.count += 1

        return self.count, self.stage

    def reset(self):
        self.stage = "up"
        self.count = 0