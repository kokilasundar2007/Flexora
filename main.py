import cv2
import mediapipe as mp

from pose_detection import create_pose_detector, get_pose

from exercises.squat import (
    get_squat_angles,
    check_squat_form,
    SquatCounter,
    is_facing_sideways,
)

from exercises.bicep_curl import (
    get_curl_angles,
    check_curl_form,
    CurlCounter,
)

from exercises.lunge import (
    get_lunge_angles,
    check_lunge_form,
    LungeCounter,
    is_facing_sideways as lunge_is_facing_sideways,
)

from exercises.plank import (
    get_plank_angles,
    check_plank_form,
    PlankTimer,
    is_facing_sideways as plank_is_facing_sideways,
)

from exercises.pushup import (
    get_pushup_angles,
    check_pushup_form,
    PushupCounter,
    is_facing_sideways as pushup_is_facing_sideways,
)

from exercises.shoulder_press import (
    get_press_angles,
    check_press_form,
    PressCounter,
)

from exercises.side_lunge import (
    get_side_lunge_angles,
    check_side_lunge_form,
    SideLungeCounter,
)

from exercises.instructions import print_instructions

from workout_state import WorkoutState

from session import (
    build_session_from_terminal,
    EXERCISE_MENU,
    TIME_BASED_EXERCISES,
)

from workout_summary import WorkoutSummary

from audio_cues import AudioCues

from voice_commands import VoiceCommands, print_help


# =====================================================
# HELPER: log a completed exercise segment to the summary
# =====================================================

def _record_progress(state, summary, cues, achieved_value):
    """
    Wraps state.handle_progress(). Also:
      - announces each new rep through the audio cues (rep-based exercises)
      - in planned-session mode, logs the just-finished exercise to the
        WorkoutSummary and plays the target / rest / complete cues the
        moment the session advances past it (or finishes on it).

    Completion is detected by the session's queue index moving forward,
    not by the exercise name changing, so back-to-back items of the same
    exercise (e.g. squat 10 then squat 15) are still handled correctly.

    In freestyle mode (state.session is None) this only announces reps and
    calls handle_progress (a no-op there) — freestyle logs its single
    result once, after the loop ends, since there's no target/advance
    event to hook into.
    """

    # Work out the exercise type BEFORE handle_progress, because it may
    # switch state.current_exercise_name to the next exercise.
    is_time_based_now = state.current_exercise_name in TIME_BASED_EXERCISES

    if not is_time_based_now:
        cues.rep(achieved_value)

    if state.session is None:
        state.handle_progress(achieved_value)
        return

    previous_index = state.session.current_index
    previous_item = state.session.get_current_item()

    state.handle_progress(achieved_value)

    if previous_item is None:
        return

    if state.session.current_index != previous_index:

        summary.log_exercise(
            previous_item.exercise_name,
            achieved=achieved_value,
            target=previous_item.target_value,
            is_time_based=previous_item.is_time_based,
        )

        if state.should_end:
            cues.workout_complete()
        else:
            cues.target_reached()
            cues.rest_start(state.current_exercise_name)


def _handle_voice_command(command, state, summary, cues, last_achieved_value, last_is_time_based):
    """
    Applies one spoken command. Returns True if the exercise was switched.

    Commands are (kind, value):
        ("switch", exercise_name)  switch exercise
        ("skip_rest", None)        end the rest early
        ("stop", None)             end the workout
    """

    kind, value = command

    if kind == "stop":
        cues.say("Stopping workout", interrupt=True)
        state.should_end = True
        return False

    if kind == "skip_rest":
        if state.is_resting:
            state.skip_rest()
        return False

    if kind == "switch":

        # Ignore switch commands while resting, and ignore switching to the
        # exercise that's already active. This also stops the mic from
        # reacting to the app's own "Next up, push up" announcement.
        if state.is_resting or value == state.current_exercise_name:
            return False

        # Freestyle keeps one result per session, so log the exercise being left
        if state.session is None and last_achieved_value > 0:
            summary.log_exercise(
                state.current_exercise_name,
                achieved=last_achieved_value,
                target=None,
                is_time_based=last_is_time_based,
            )

        state.switch_exercise(value)
        cues.say(value.replace("_", " "), interrupt=True)
        print_instructions(value)
        return True

    return False


def run_workout(state):
    """
    Runs the live camera workout session, driven by a WorkoutState.

    state: a WorkoutState object holding the current active exercise
           and (optionally) a planned session queue with targets.

    This function is the single entry point a frontend (web page,
    desktop app, API, etc.) will call later. For now, it also runs
    directly when this file is executed as a script.
    """

    # Create pose detector
    pose_detector = create_pose_detector()

    # One counter/timer per exercise, created once, persists across frames
    squat_counter = SquatCounter()
    curl_counter = CurlCounter()
    lunge_counter = LungeCounter()
    plank_timer = PlankTimer()
    pushup_counter = PushupCounter()
    press_counter = PressCounter()
    side_lunge_counter = SideLungeCounter()

    # Post-workout report — collects results across the whole session
    # (freestyle or planned) and prints/saves them once the loop ends.
    summary = WorkoutSummary()
    summary.start()

    # Beeps + spoken cues (plays on a background thread, never blocks the camera)
    cues = AudioCues()

    # Hands-free voice commands (listens on a background thread; stays off
    # with a message if Vosk or its model isn't installed)
    voice = VoiceCommands()
    if voice.start():
        print_help()
    voice_switched = False

    # Tracks the most recent progress value/type seen, for freestyle
    # mode's final log-on-quit (planned mode logs via _record_progress
    # instead, since it has explicit per-item completion events).
    last_achieved_value = 0
    last_is_time_based = False

    # Camera
    cap = cv2.VideoCapture(0)

    while True:

        if state.should_end:
            break

        ret, frame = cap.read()

        if not ret:
            print("Cannot access camera")
            break

        # Mirror camera
        frame = cv2.flip(frame, 1)

        # Get pose landmarks
        landmarks = get_pose(
            frame,
            pose_detector
        )

        # Apply any spoken commands heard since the last frame
        for command in voice.poll():
            if _handle_voice_command(command, state, summary, cues,
                                     last_achieved_value, last_is_time_based):
                voice_switched = True

        exercise_name = state.current_exercise_name


        # -------------------------------
        # RESET COUNTERS
        # A rest just ended, or the exercise was switched manually.
        # Start the active exercise from a clean slate so leftover
        # reps / hold time from the previous exercise can't carry over.
        # -------------------------------

        if state.consume_reset():

            squat_counter = SquatCounter()
            curl_counter = CurlCounter()
            lunge_counter = LungeCounter()
            plank_timer = PlankTimer()
            pushup_counter = PushupCounter()
            press_counter = PressCounter()
            side_lunge_counter = SideLungeCounter()

            last_achieved_value = 0
            last_is_time_based = False

            cues.reset()
            cues.go()


        # -------------------------------
        # REST SCREEN (planned sessions only)
        # No pose logic and no rep counting while resting.
        # -------------------------------

        if state.is_resting:

            # Keep the rest countdown ticking
            state.handle_progress(0)

            # Dim the camera feed so the rest info stands out
            frame = cv2.convertScaleAbs(frame, alpha=0.35, beta=0)

            seconds_left = int(state.rest_remaining()) + 1

            cues.rest_tick(seconds_left)

            next_name = state.current_exercise_name.replace("_", " ").title()
            next_item = state.session.get_current_item() if state.session is not None else None

            if next_item is not None:
                next_text = f"Next up: {next_name} ({next_item.target_label()})"
            else:
                next_text = f"Next up: {next_name}"

            cv2.putText(frame, "REST", (30, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 255), 4)

            cv2.putText(frame, f"{seconds_left}s", (30, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4)

            cv2.putText(frame, next_text, (30, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            cv2.putText(frame, "Press S to skip rest", (30, 260),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)


        elif landmarks is not None:

            height, width, _ = frame.shape


            # -------------------------------
            # DRAW JOINTS
            # -------------------------------

            for landmark in landmarks:

                x = int(landmark.x * width)
                y = int(landmark.y * height)

                if 0 <= x < width and 0 <= y < height:

                    cv2.circle(
                        frame,
                        (x, y),
                        5,
                        (0, 255, 0),
                        -1
                    )


            # -------------------------------
            # DRAW SKELETON
            # -------------------------------

            connections = [
                (11, 13),
                (13, 15),

                (12, 14),
                (14, 16),

                (11, 12),

                (11, 23),
                (12, 24),

                (23, 24),

                (23, 25),
                (25, 27),

                (24, 26),
                (26, 28)
            ]


            for start, end in connections:

                x1 = int(landmarks[start].x * width)
                y1 = int(landmarks[start].y * height)

                x2 = int(landmarks[end].x * width)
                y2 = int(landmarks[end].y * height)

                cv2.line(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )


            # -------------------------------
            # SQUAT LOGIC
            # -------------------------------

            if exercise_name == "squat":

                sideways = is_facing_sideways(landmarks)

                if sideways is False:

                    cv2.putText(
                        frame,
                        "Please turn sideways for squat detection",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                elif sideways is None:

                    cv2.putText(
                        frame,
                        "Body not fully visible",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                else:

                    angles = get_squat_angles(landmarks)
                    form_status = check_squat_form(angles)
                    count, stage = squat_counter.update(angles)
                    last_achieved_value = count
                    last_is_time_based = False
                    _record_progress(state, summary, cues, count)

                    if angles is not None:

                        knee = angles["knee"]
                        hip = angles["hip"]
                        back = angles["back"]

                        if knee is not None:
                            cv2.putText(frame, f"Knee Angle: {knee:.1f}", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Knee Angle: Not detected", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        if hip is not None:
                            cv2.putText(frame, f"Hip Angle: {hip:.1f}", (30, 85),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Hip Angle: Not detected", (30, 85),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        if back is not None:
                            cv2.putText(frame, f"Back Angle: {back:.1f}", (30, 120),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Back Angle: Not detected", (30, 120),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        cv2.putText(frame, f"Form: {form_status}", (30, 155),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                    (0, 255, 0) if form_status == "Good Form" else (0, 0, 255), 2)

                        cv2.putText(frame, f"Reps: {count} ({stage})", (30, 190),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


            # -------------------------------
            # BICEP CURL LOGIC
            # -------------------------------

            elif exercise_name == "bicep_curl":

                angles = get_curl_angles(landmarks)
                form_status = check_curl_form(angles)
                count, stage = curl_counter.update(angles)
                last_achieved_value = count
                last_is_time_based = False
                _record_progress(state, summary, cues, count)

                if angles is not None:

                    elbow = angles["elbow"]
                    torso_lean = angles["torso_lean"]

                    if elbow is not None:
                        cv2.putText(frame, f"Elbow Angle: {elbow:.1f}", (30, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    else:
                        cv2.putText(frame, "Elbow Angle: Not detected", (30, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    if torso_lean is not None:
                        cv2.putText(frame, f"Torso Lean: {torso_lean:.1f}", (30, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    else:
                        cv2.putText(frame, "Torso Lean: Not detected", (30, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    cv2.putText(frame, f"Form: {form_status}", (30, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 255, 0) if form_status == "Good Rep" else (0, 0, 255), 2)

                    cv2.putText(frame, f"Reps: {count} ({stage})", (30, 155),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


            # -------------------------------
            # LUNGE LOGIC
            # -------------------------------

            elif exercise_name == "lunge":

                sideways = lunge_is_facing_sideways(landmarks)

                if sideways is False:

                    cv2.putText(
                        frame,
                        "Please turn sideways for lunge detection",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                elif sideways is None:

                    cv2.putText(
                        frame,
                        "Body not fully visible",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                else:

                    angles = get_lunge_angles(landmarks)
                    form_status = check_lunge_form(angles)
                    count, stage = lunge_counter.update(angles)
                    last_achieved_value = count
                    last_is_time_based = False
                    _record_progress(state, summary, cues, count)

                    if angles is not None:

                        front_knee = angles["front_knee"]
                        back_knee = angles["back_knee"]
                        torso_lean = angles["torso_lean"]

                        if front_knee is not None:
                            cv2.putText(frame, f"Front Knee: {front_knee:.1f}", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Front Knee: Not detected", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        if back_knee is not None:
                            cv2.putText(frame, f"Back Knee: {back_knee:.1f}", (30, 85),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Back Knee: Not detected", (30, 85),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        if torso_lean is not None:
                            cv2.putText(frame, f"Torso Lean: {torso_lean:.1f}", (30, 120),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Torso Lean: Not detected", (30, 120),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        cv2.putText(frame, f"Form: {form_status}", (30, 155),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                    (0, 255, 0) if form_status == "Good Form" else (0, 0, 255), 2)

                        cv2.putText(frame, f"Reps: {count} ({stage})", (30, 190),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


            # -------------------------------
            # PLANK LOGIC
            # -------------------------------

            elif exercise_name == "plank":

                sideways = plank_is_facing_sideways(landmarks)

                if sideways is False:

                    cv2.putText(
                        frame,
                        "Please turn sideways for plank detection",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                elif sideways is None:

                    cv2.putText(
                        frame,
                        "Body not fully visible",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                else:

                    angles = get_plank_angles(landmarks)
                    form_status = check_plank_form(angles)
                    current_hold, best_hold = plank_timer.update(form_status)
                    last_achieved_value = current_hold
                    last_is_time_based = True
                    _record_progress(state, summary, cues, current_hold)

                    if angles is not None:

                        body_angle = angles["body_angle"]

                        if body_angle is not None:
                            cv2.putText(frame, f"Body Angle: {body_angle:.1f}", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Body Angle: Not detected", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        cv2.putText(frame, f"Form: {form_status}", (30, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                    (0, 255, 0) if form_status == "Good Form" else (0, 0, 255), 2)

                        cv2.putText(frame, f"Hold Time: {current_hold:.1f}s", (30, 120),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

                        cv2.putText(frame, f"Best Hold: {best_hold:.1f}s", (30, 155),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


            # -------------------------------
            # PUSH-UP LOGIC
            # -------------------------------

            elif exercise_name == "pushup":

                sideways = pushup_is_facing_sideways(landmarks)

                if sideways is False:

                    cv2.putText(
                        frame,
                        "Please turn sideways for push-up detection",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                elif sideways is None:

                    cv2.putText(
                        frame,
                        "Body not fully visible",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 165, 255),
                        2
                    )

                else:

                    angles = get_pushup_angles(landmarks)
                    form_status = check_pushup_form(angles)
                    count, stage = pushup_counter.update(angles)
                    last_achieved_value = count
                    last_is_time_based = False
                    _record_progress(state, summary, cues, count)

                    if angles is not None:

                        elbow = angles["elbow"]
                        body_angle = angles["body_angle"]

                        if elbow is not None:
                            cv2.putText(frame, f"Elbow Angle: {elbow:.1f}", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Elbow Angle: Not detected", (30, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        if body_angle is not None:
                            cv2.putText(frame, f"Body Angle: {body_angle:.1f}", (30, 85),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Body Angle: Not detected", (30, 85),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                        cv2.putText(frame, f"Form: {form_status}", (30, 120),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                    (0, 255, 0) if form_status == "Good Form" else (0, 0, 255), 2)

                        cv2.putText(frame, f"Reps: {count} ({stage})", (30, 155),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


            # -------------------------------
            # SHOULDER PRESS LOGIC
            # -------------------------------

            elif exercise_name == "shoulder_press":

                angles = get_press_angles(landmarks)
                form_status = check_press_form(angles)
                count, stage = press_counter.update(angles)
                last_achieved_value = count
                last_is_time_based = False
                _record_progress(state, summary, cues, count)

                if angles is not None:

                    elbow = angles["elbow"]
                    torso_lean = angles["torso_lean"]

                    if elbow is not None:
                        cv2.putText(frame, f"Elbow Angle: {elbow:.1f}", (30, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    else:
                        cv2.putText(frame, "Elbow Angle: Not detected", (30, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    if torso_lean is not None:
                        cv2.putText(frame, f"Torso Lean: {torso_lean:.1f}", (30, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    else:
                        cv2.putText(frame, "Torso Lean: Not detected", (30, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    cv2.putText(frame, f"Form: {form_status}", (30, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 255, 0) if form_status == "Good Rep" else (0, 0, 255), 2)

                    cv2.putText(frame, f"Reps: {count} ({stage})", (30, 155),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


            # -------------------------------
            # SIDE LUNGE LOGIC
            # -------------------------------

            elif exercise_name == "side_lunge":

                angles = get_side_lunge_angles(landmarks)
                form_status = check_side_lunge_form(angles)
                count, stage = side_lunge_counter.update(angles)
                last_achieved_value = count
                last_is_time_based = False
                _record_progress(state, summary, cues, count)

                if angles is not None:

                    working_knee = angles["working_knee"]
                    straight_knee = angles["straight_knee"]
                    torso_lean = angles["torso_lean"]

                    if working_knee is not None:
                        cv2.putText(frame, f"Working Knee: {working_knee:.1f}", (30, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                    if straight_knee is not None:
                        cv2.putText(frame, f"Straight Knee: {straight_knee:.1f}", (30, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                    if torso_lean is not None:
                        cv2.putText(frame, f"Torso Lean: {torso_lean:.1f}", (30, 120),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                    cv2.putText(frame, f"Form: {form_status}", (30, 155),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 255, 0) if form_status == "Good Form" else (0, 0, 255), 2)

                    cv2.putText(frame, f"Reps: {count} ({stage})", (30, 190),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)


        else:

            cv2.putText(
                frame,
                "Pose Not Detected",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2
            )


        # If a planned session just finished, show a final message briefly
        if state.should_end:

            cv2.putText(
                frame,
                "Workout Complete!",
                (30, 230),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 255),
                3
            )


        # Voice hint (only shown when voice control is actually on)
        if voice.enabled:
            cv2.putText(
                frame,
                "Voice: say an exercise name | skip rest | stop workout",
                (10, frame.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )


        # Show window
        cv2.imshow(
            "Flexora AI",
            frame
        )


        # Keys: Q = quit, S = skip rest
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

        if key == ord("s"):
            state.skip_rest()


    # Release resources
    cap.release()
    cv2.destroyAllWindows()
    pose_detector.close()
    voice.close()

    # Freestyle mode has no target/advance events to log against, so
    # log its single result here, once, using whatever was last seen.
    if state.session is None and (last_achieved_value > 0 or not voice_switched):
        summary.log_exercise(
            state.current_exercise_name,
            achieved=last_achieved_value,
            target=None,
            is_time_based=last_is_time_based,
        )

    # Print + save the post-workout report (exercises done, total time,
    # suggestions) for both freestyle and planned-session runs.
    summary.finish()
    summary.print_report()

    # Let the final sound (e.g. "Workout complete") finish playing
    cues.close()


# -------------------------------
# SCRIPT ENTRY POINT (for direct testing)
# -------------------------------

if __name__ == "__main__":

    print("How do you want to work out?")
    print("1. Freestyle (pick one exercise, no targets)")
    print("2. Planned session (queue of exercises with targets)")

    mode_choice = input("Enter number: ").strip()

    if mode_choice == "2":

        session = build_session_from_terminal()
        first_exercise = session.get_current_item().exercise_name

        rest_raw = input("Rest between exercises in seconds (press Enter for 30): ").strip()
        rest_seconds = int(rest_raw) if rest_raw.isdigit() and int(rest_raw) > 0 else 30

        print_instructions(first_exercise)

        state = WorkoutState(first_exercise, session=session, rest_seconds=rest_seconds)

    else:

        print("\nChoose an exercise:")
        for key, name in EXERCISE_MENU.items():
            print(f"  {key}. {name}")

        choice = input("Enter number: ").strip()
        selected_exercise = EXERCISE_MENU.get(choice, "squat")

        print_instructions(selected_exercise)

        state = WorkoutState(selected_exercise, session=None)

    run_workout(state)