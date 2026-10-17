import time


class WorkoutState:
    """
    Holds the single source of truth for "what exercise is active right now."

    Can be changed by:
    - A planned session auto-advancing when a target is hit
    - Voice commands switching exercises directly (built later)
    - Simply staying fixed if the user picked freestyle mode with no plan

    The camera loop reads self.current_exercise_name every frame —
    it doesn't need to know why or how it changed.

    Rest periods (planned sessions only):
    After each finished exercise a rest starts. While self.is_resting is
    True, current_exercise_name is already the NEXT exercise (so the HUD
    can show "Next up: ..."), but the camera loop should not count reps.

    Counter resets:
    Whenever the active exercise changes or a rest ends, needs_reset is
    set to True. The camera loop should call consume_reset() every frame;
    when it returns True, reset the rep counter / hold timer of the
    current exercise module. Until that happens, handle_progress() ignores
    progress values, so stale counts from the previous exercise can never
    complete the next one.
    """

    def __init__(self, initial_exercise, session=None, rest_seconds=30):
        """
        initial_exercise: the exercise name to start with
        session: a WorkoutSession object if the user planned a queue,
                 or None if this is freestyle (single exercise, no plan)
        rest_seconds: length of the break between planned exercises
        """

        self.current_exercise_name = initial_exercise
        self.session = session
        self.should_end = False

        # Rest state (only ever used in planned sessions)
        self.rest_seconds = rest_seconds
        self.is_resting = False
        self.rest_end_time = 0.0

        # True when the active exercise's counter/timer must be reset
        self.needs_reset = False

    def switch_exercise(self, new_exercise_name):
        """
        Manually changes the active exercise.
        This is what a voice command will call later.
        Cancels any rest in progress and requests a counter reset.
        """

        self.current_exercise_name = new_exercise_name
        self.is_resting = False
        self.needs_reset = True

    def consume_reset(self):
        """
        Returns True exactly once after the exercise changed or a rest
        ended, so the camera loop knows to reset the current module's
        rep counter / hold timer. Returns False otherwise.
        """

        if self.needs_reset:
            self.needs_reset = False
            return True

        return False

    def start_rest(self):
        """Begins the rest countdown."""

        self.is_resting = True
        self.rest_end_time = time.monotonic() + self.rest_seconds

    def _end_rest(self):
        """Ends the rest and requests a reset for the upcoming exercise."""

        self.is_resting = False
        self.needs_reset = True

    def skip_rest(self):
        """Ends the rest early (e.g. when the user presses a key)."""

        if self.is_resting:
            self._end_rest()

    def rest_remaining(self):
        """Seconds left in the current rest (0 if not resting)."""

        if not self.is_resting:
            return 0.0

        return max(0.0, self.rest_end_time - time.monotonic())

    def handle_progress(self, current_value):
        """
        Call this every frame with the current progress value
        (rep count for rep-based exercises, or hold seconds for
        time-based ones like plank).

        If running a planned session, checks whether the current
        item's target has been reached, and auto-advances if so
        (with a rest period before the next exercise).
        Does nothing in freestyle mode (session is None).
        """

        if self.session is None:
            return

        # During rest, just wait for the countdown to finish.
        if self.is_resting:
            if self.rest_remaining() <= 0:
                self._end_rest()
            return

        # Counter hasn't been reset yet for the new exercise, so the
        # value being passed in is stale. Ignore it.
        if self.needs_reset:
            return

        current_item = self.session.get_current_item()

        if current_item is None:
            return

        # If the user voice-switched away from the planned exercise,
        # don't count progress toward the wrong item.
        if current_item.exercise_name != self.current_exercise_name:
            return

        if current_item.check_complete(current_value):

            self.session.advance()

            if self.session.is_finished():
                self.should_end = True
            else:
                self.current_exercise_name = self.session.get_current_item().exercise_name
                self.start_rest()