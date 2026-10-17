import math
import time


# =====================================================
# LANDMARK INDICES (MediaPipe Pose)
# =====================================================

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
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
    Decides which side (left/right) is more visible.
    Returns "left", "right", or None if neither side is usable.
    """

    left_points = [
        landmarks[LEFT_SHOULDER],
        landmarks[LEFT_HIP],
        landmarks[LEFT_ANKLE],
    ]

    right_points = [
        landmarks[RIGHT_SHOULDER],
        landmarks[RIGHT_HIP],
        landmarks[RIGHT_ANKLE],
    ]

    left_ok = all(_visible(p) for p in left_points)
    right_ok = all(_visible(p) for p in right_points)

    if left_ok and right_ok:
        left_avg = sum(getattr(p, "visibility", 1.0) for p in left_points) / 3
        right_avg = sum(getattr(p, "visibility", 1.0) for p in right_points) / 3
        return "left" if left_avg >= right_avg else "right"

    if left_ok:
        return "left"

    if right_ok:
        return "right"

    return None


# =====================================================
# ORIENTATION CHECK (plank needs a side view)
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
# PLANK ANGLE CALCULATION
# =====================================================

def get_plank_angles(landmarks):
    """
    Calculates the body alignment angle (shoulder-hip-ankle) for plank,
    plus whether the hip is sagging or piking relative to the
    shoulder-ankle line.

    Returns a dict:
        {
            "side": "left" or "right",
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
        hip = landmarks[LEFT_HIP]
        ankle = landmarks[LEFT_ANKLE]
    else:
        shoulder = landmarks[RIGHT_SHOULDER]
        hip = landmarks[RIGHT_HIP]
        ankle = landmarks[RIGHT_ANKLE]

    # Body alignment angle: shoulder - hip - ankle
    body_angle = calculate_angle(shoulder, hip, ankle)

    # Determine if hip is above or below the shoulder-ankle line.
    # Using linear interpolation: expected hip y-position if shoulder,
    # hip, ankle were perfectly in a straight line.
    hip_position = "aligned"

    if shoulder.x != ankle.x:
        # Fraction of the way from shoulder to ankle, based on x position
        t = (hip.x - shoulder.x) / (ankle.x - shoulder.x)
        expected_hip_y = shoulder.y + t * (ankle.y - shoulder.y)

        # In image coordinates, y increases downward.
        # If actual hip.y is greater than expected -> hip is lower -> sagging
        # If actual hip.y is less than expected -> hip is higher -> piking
        diff = hip.y - expected_hip_y

        SAG_PIKE_THRESHOLD = 0.03  # normalized distance; tune if needed

        if diff > SAG_PIKE_THRESHOLD:
            hip_position = "sagging"
        elif diff < -SAG_PIKE_THRESHOLD:
            hip_position = "piking"

    return {
        "side": side,
        "body_angle": body_angle,
        "hip_position": hip_position,
    }


# =====================================================
# POSTURE / FORM CHECKING
# =====================================================

GOOD_PLANK_ANGLE_MIN = 165   # body angle must be at least this straight
GOOD_PLANK_ANGLE_MAX = 195   # allows slight measurement wobble both directions


def check_plank_form(angles):
    """
    Given the angles dict from get_plank_angles, returns a form status string.
    Possible values:
        "Not Detected"
        "Good Form"
        "Hips Sagging"
        "Hips Piking"
    """

    if angles is None:
        return "Not Detected"

    body_angle = angles["body_angle"]
    hip_position = angles["hip_position"]

    if body_angle is None:
        return "Not Detected"

    if hip_position == "sagging":
        return "Hips Sagging"

    if hip_position == "piking":
        return "Hips Piking"

    if GOOD_PLANK_ANGLE_MIN <= body_angle <= GOOD_PLANK_ANGLE_MAX:
        return "Good Form"

    # Angle is off but hip_position check didn't catch a clear direction
    return "Adjust Position"


# =====================================================
# HOLD TIMER (instead of a rep counter)
# =====================================================

class PlankTimer:
    """
    Tracks how long good plank form has been held continuously.
    Resets the streak if form breaks, but keeps the best time achieved.
    """

    def __init__(self):
        self.hold_start_time = None
        self.current_hold_seconds = 0.0
        self.best_hold_seconds = 0.0

    def update(self, form_status):
        """
        Call this every frame with the current form_status string.
        Returns (current_hold_seconds, best_hold_seconds).
        """

        now = time.time()

        if form_status == "Good Form":

            if self.hold_start_time is None:
                self.hold_start_time = now

            self.current_hold_seconds = now - self.hold_start_time

            if self.current_hold_seconds > self.best_hold_seconds:
                self.best_hold_seconds = self.current_hold_seconds

        else:
            self.hold_start_time = None
            self.current_hold_seconds = 0.0

        return self.current_hold_seconds, self.best_hold_seconds

    def reset(self):
        self.hold_start_time = None
        self.current_hold_seconds = 0.0
        self.best_hold_seconds = 0.0