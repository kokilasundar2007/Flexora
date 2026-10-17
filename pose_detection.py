import cv2
import mediapipe as mp


BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
RunningMode = mp.tasks.vision.RunningMode


def create_pose_detector():

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path="models/pose_landmarker_full.task"
        ),
        running_mode=RunningMode.IMAGE
    )

    return PoseLandmarker.create_from_options(options)


def get_pose(frame, pose_detector):

    rgb_frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb_frame
    )

    result = pose_detector.detect(mp_image)

    if result.pose_landmarks:
        print("Pose detected")
        return result.pose_landmarks[0]

    print("Pose not detected")
    return None