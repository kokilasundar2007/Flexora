import math


def calculate_angle(a, b, c):

    angle = math.degrees(
        math.atan2(c.y - b.y, c.x - b.x)
        - math.atan2(a.y - b.y, a.x - b.x)
    )

    angle = abs(angle)

    if angle > 180:
        angle = 360 - angle

    return angle


def get_angle(landmarks, a, b, c):

    point_a = landmarks[a]
    point_b = landmarks[b]
    point_c = landmarks[c]

    # Check whether the landmark coordinates are valid
    if not (
        0 <= point_a.x <= 1 and
        0 <= point_a.y <= 1 and
        0 <= point_b.x <= 1 and
        0 <= point_b.y <= 1 and
        0 <= point_c.x <= 1 and
        0 <= point_c.y <= 1
    ):
        return None

    return calculate_angle(
        point_a,
        point_b,
        point_c
    )