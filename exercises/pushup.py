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


def _pick_side(landmarks):
    """
    Decides which side (left/right) is more visible,
    so angle calculations use reliable landmarks.
    Returns "left", "right", or None if neither side is usable.
    """

    left_points = [
        landmarks[LEFT_SHOULDER],
        landmarks[LEFT_ELBOW],
        landmarks[LEFT_WRIST],
        landmarks[LEFT_HIP],
        landmarks[LEFT_ANKLE],
    ]

    right_points = [
        landmarks[RIGHT_SHOULDER],
        landmarks[RIGHT_ELBOW],
        landmarks[RIGHT_WRIST],
        landmarks[RIGHT_HIP],
        landmarks[RIGHT_ANKLE],
    ]

    left_ok = all(_visible(p) for p in left_points)
    right_ok = all(_visible(p) for p in right_points)

    if left_ok and right_ok:
        left_avg = sum(getattr(p, "visibility", 1.0) for p in left_points) / 5
        right_avg = sum(getattr(p, "visibility", 1.0) for p in right_points) / 5
        return "left" if left_avg >= right_avg else "right"

    if left_ok:
        return "left"

    if right_ok:
        return "right"

    return None


# =====================================================
# ORIENTATION CHECK (push-ups need a side view)
# =====================================================

SIDEWAYS_SHOULDER_THRESHOLD = 0.10


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
# PUSH-UP ANGLE CALCULATION
# =====================================================

def get_pushup_angles(landmarks):
    """
    Calculates elbow angle and body alignment (sag/pike) for push-ups.
    Automatically chooses the more visible side.

    Returns a dict:
        {
            "side": "left" or "right",
            "elbow": angle or None,
            "body_angle": angle or None,
            "hip_position": "sagging", "piking", or "aligned"
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
        ankle = landmarks[LEFT_ANKLE]
    else:
        shoulder = landmarks[RIGHT_SHOULDER]
        elbow = landmarks[RIGHT_ELBOW]
        wrist = landmarks[RIGHT_WRIST]
        hip = landmarks[RIGHT_HIP]
        ankle = landmarks[RIGHT_ANKLE]

    # Elbow angle: shoulder - elbow - wrist
    elbow_angle = calculate_angle(shoulder, elbow, wrist)

    # Body alignment angle: shoulder - hip - ankle
    body_angle = calculate_angle(shoulder, hip, ankle)

    # Sag/pike detection: compare actual hip position to the
    # expected position if shoulder-hip-ankle were a straight line.
    hip_position = "aligned"

    if shoulder.x != ankle.x:
        t = (hip.x - shoulder.x) / (ankle.x - shoulder.x)
        expected_hip_y = shoulder.y + t * (ankle.y - shoulder.y)

        diff = hip.y - expected_hip_y

        SAG_PIKE_THRESHOLD = 0.03

        if diff > SAG_PIKE_THRESHOLD:
            hip_position = "sagging"
        elif diff < -SAG_PIKE_THRESHOLD:
            hip_position = "piking"

    return {
        "side": side,
        "elbow": elbow_angle,
        "body_angle": body_angle,
        "hip_position": hip_position,
    }


# =====================================================
# POSTURE / FORM CHECKING
# =====================================================

ARM_EXTENDED_ANGLE = 160      # elbow angle at the top of the push-up
PUSHUP_DEPTH_ANGLE = 100      # elbow angle must go below this at the bottom


def check_pushup_form(angles):
    """
    Given the angles dict from get_pushup_angles, returns a form status string.
    Possible values:
        "Not Detected"
        "Up Position"
        "Good Form"
        "Not Deep Enough"
        "Hips Sagging"
        "Hips Piking"
    """

    if angles is None:
        return "Not Detected"

    elbow = angles["elbow"]
    hip_position = angles["hip_position"]

    if elbow is None:
        return "Not Detected"

    if hip_position == "sagging":
        return "Hips Sagging"

    if hip_position == "piking":
        return "Hips Piking"

    if elbow >= ARM_EXTENDED_ANGLE:
        return "Up Position"

    if elbow <= PUSHUP_DEPTH_ANGLE:
        return "Good Form"

    return "Not Deep Enough"


# =====================================================
# REPETITION COUNTER (STATE MACHINE)
# =====================================================

class PushupCounter:
    """
    Tracks push-up repetitions using a simple two-state machine:
        "up"   -> arms extended
        "down" -> chest lowered

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

        if angles is None or angles["elbow"] is None:
            return self.count, self.stage

        elbow = angles["elbow"]

        # Transition to "down" once elbow bends past push-up depth
        if elbow <= PUSHUP_DEPTH_ANGLE:
            self.stage = "down"

        # Transition back to "up" -> completes one rep
        elif elbow >= ARM_EXTENDED_ANGLE and self.stage == "down":
            self.stage = "up"
            self.count += 1

        return self.count, self.stage

    def reset(self):
        self.stage = "up"
        self.count = 0