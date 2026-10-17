import json
import os
import time


HISTORY_FILE = "workout_history.json"


# =====================================================
# ONE LOGGED EXERCISE RESULT
# =====================================================

class ExerciseResult:
    """
    A single exercise's result at the end of a workout.

    achieved: final rep count, or final hold seconds for time-based
              exercises (plank).
    target: the goal for that exercise, if there was one (planned
            session mode). None in freestyle mode, since there's
            nothing to compare against.
    is_time_based: True for hold-based exercises like plank.
    """

    def __init__(self, exercise_name, achieved, target=None, is_time_based=False):
        self.exercise_name = exercise_name
        self.achieved = achieved
        self.target = target
        self.is_time_based = is_time_based

    def met_target(self):
        if self.target is None:
            return None
        return self.achieved >= self.target

    def achieved_label(self):
        if self.is_time_based:
            return f"{self.achieved:.1f}s"
        return f"{self.achieved} reps"

    def result_label(self):
        """
        Human-readable line for this exercise, used in the report.
        """

        name = self.exercise_name.replace("_", " ").title()

        if self.target is None:
            return f"{name}: {self.achieved_label()}"

        target_label = f"{self.target}s" if self.is_time_based else f"{self.target} reps"
        status = "Hit target" if self.met_target() else "Below target"

        return f"{name}: {self.achieved_label()} / {target_label}  ({status})"


# =====================================================
# THE WORKOUT SUMMARY
# =====================================================

class WorkoutSummary:
    """
    Collects results across a workout (freestyle or planned) and
    produces a final report: exercises done, total time, suggestions.

    Usage:
        summary = WorkoutSummary()
        summary.start()
        ... during the workout, whenever an exercise segment ends ...
        summary.log_exercise("squat", achieved=12, target=10)
        summary.log_exercise("plank", achieved=32.4, target=30, is_time_based=True)
        ... when the workout ends ...
        summary.finish()
        summary.print_report()
    """

    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None

    def start(self):
        self.start_time = time.time()

    def finish(self):
        self.end_time = time.time()

    def log_exercise(self, exercise_name, achieved, target=None, is_time_based=False):
        """
        Records one exercise's final result. Call this once per
        exercise segment — e.g. when a planned-session item completes,
        or when the user quits a freestyle exercise.
        """

        self.results.append(
            ExerciseResult(exercise_name, achieved, target, is_time_based)
        )

    def total_duration_seconds(self):
        if self.start_time is None:
            return 0.0

        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time

    # -------------------------------------------------
    # SUGGESTIONS
    # -------------------------------------------------

    def generate_suggestions(self):
        """
        Returns a list of short, plain-language suggestions based on
        what happened during the workout. Rule-based — no ML, just
        readable heuristics that give useful next-session guidance.
        """

        suggestions = []

        if len(self.results) == 0:
            suggestions.append("No exercises were completed — try a short freestyle session to get started.")
            return suggestions

        duration_minutes = self.total_duration_seconds() / 60

        # --- Per-exercise target performance ---

        for result in self.results:

            met = result.met_target()

            if met is None:
                continue

            if met:
                if result.is_time_based:
                    suggestions.append(
                        f"You held {result.exercise_name.replace('_', ' ')} for the full target — "
                        f"try aiming a few seconds longer next time."
                    )
                else:
                    suggestions.append(
                        f"You hit your {result.exercise_name.replace('_', ' ')} target comfortably — "
                        f"consider raising it next session."
                    )
            else:
                ratio = result.achieved / result.target if result.target else 1

                if ratio < 0.5:
                    suggestions.append(
                        f"{result.exercise_name.replace('_', ' ').title()} fell well short of target — "
                        f"try a lower target or focus on form before adding volume."
                    )
                else:
                    suggestions.append(
                        f"{result.exercise_name.replace('_', ' ').title()} was close to target — "
                        f"a small push should get you there next time."
                    )

        # --- Overall session length ---

        if duration_minutes < 3:
            suggestions.append("This was a short session — even 5-10 extra minutes adds meaningful volume.")
        elif duration_minutes > 45:
            suggestions.append("That was a long session — make sure to rest and hydrate between workouts.")

        # --- Variety ---

        unique_exercises = {result.exercise_name for result in self.results}

        if len(unique_exercises) == 1:
            suggestions.append("You focused on one exercise — a planned session with a few different exercises can help balance muscle groups.")

        return suggestions

    # -------------------------------------------------
    # REPORT
    # -------------------------------------------------

    def print_report(self):
        """
        Prints the full post-workout report to the terminal and saves
        it to workout_history.json.
        """

        print("\n========== Workout Report ==========")

        if len(self.results) == 0:
            print("  No exercises recorded.")
        else:
            for result in self.results:
                print(f"  {result.result_label()}")

        duration = self.total_duration_seconds()
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        print(f"\n  Total time: {minutes}m {seconds}s")

        suggestions = self.generate_suggestions()

        if suggestions:
            print("\n  Suggestions:")
            for suggestion in suggestions:
                print(f"    - {suggestion}")

        print("======================================\n")

        self._save_to_file()

    # -------------------------------------------------
    # SAVE TO HISTORY
    # -------------------------------------------------

    def _save_to_file(self, filepath=HISTORY_FILE):

        record = {
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(self.total_duration_seconds(), 1),
            "exercises": [
                {
                    "exercise": result.exercise_name,
                    "achieved": round(result.achieved, 1) if result.is_time_based else result.achieved,
                    "target": result.target,
                    "met_target": result.met_target(),
                }
                for result in self.results
            ],
            "suggestions": self.generate_suggestions(),
        }

        history = []

        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    history = json.load(f)
                    if not isinstance(history, list):
                        history = []
            except (json.JSONDecodeError, OSError):
                history = []

        history.append(record)

        with open(filepath, "w") as f:
            json.dump(history, f, indent=2)
