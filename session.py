import json
import os
import time


# =====================================================
# EXERCISE MENU (shared with main.py's freestyle picker)
# =====================================================

EXERCISE_MENU = {
    "1": "squat",
    "2": "bicep_curl",
    "3": "lunge",
    "4": "plank",
    "5": "pushup",
    "6": "shoulder_press",
    "7": "side_lunge",
}

# Exercises where progress is measured in seconds held rather than reps.
TIME_BASED_EXERCISES = {"plank"}

HISTORY_FILE = "workout_history.json"


# =====================================================
# SESSION ITEM
# =====================================================

class SessionItem:
    """
    One entry in a planned workout queue: a single exercise plus its target.

    target_value means:
        - rep count, for rep-based exercises (squat, bicep_curl, lunge,
          pushup, shoulder_press, side_lunge)
        - seconds held, for time-based exercises (plank)
    """

    def __init__(self, exercise_name, target_value):
        self.exercise_name = exercise_name
        self.target_value = target_value
        self.is_time_based = exercise_name in TIME_BASED_EXERCISES

        # Best progress value actually reached on this item — filled in by
        # check_complete() every frame, read later for the summary.
        self.final_value = 0

    def check_complete(self, current_value):
        """
        Call every frame with the current progress value (rep count, or
        current hold seconds for plank). Updates final_value and returns
        True once the target has been reached.
        """

        if current_value is None:
            return False

        if current_value > self.final_value:
            self.final_value = current_value

        return current_value >= self.target_value

    def target_label(self):
        """
        Human-readable target, for menus and summaries.
        """

        if self.is_time_based:
            return f"{self.target_value}s hold"

        return f"{self.target_value} reps"

    def result_label(self):
        """
        Human-readable result, for the final summary.
        """

        if self.is_time_based:
            return f"{self.final_value:.1f}s / {self.target_value}s"

        return f"{self.final_value} / {self.target_value} reps"


# =====================================================
# WORKOUT SESSION (the queue)
# =====================================================

class WorkoutSession:
    """
    Holds an ordered queue of SessionItems and tracks progress through it.
    """

    def __init__(self, items):
        self.items = items
        self.current_index = 0
        self.start_time = time.time()
        self.end_time = None

    def get_current_item(self):
        """
        Returns the SessionItem currently in progress, or None if the
        queue has been fully completed.
        """

        if self.current_index >= len(self.items):
            return None

        return self.items[self.current_index]

    def advance(self):
        """
        Moves on to the next item in the queue. Called by WorkoutState
        once the current item's target has been hit.
        """

        self.current_index += 1

        if self.is_finished():
            self.end_time = time.time()

    def is_finished(self):
        return self.current_index >= len(self.items)

    def total_duration_seconds(self):
        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time

    def print_summary(self):
        """
        Prints a final summary of the session to the terminal and saves
        it to workout_history.json.
        """

        print("\n===== Workout Summary =====")

        for item in self.items:
            status = "Done" if item.final_value >= item.target_value else "Incomplete"
            print(f"  {item.exercise_name}: {item.result_label()}  [{status}]")

        duration = self.total_duration_seconds()
        print(f"Total time: {duration:.1f}s")
        print("============================\n")

        save_session_to_file(self)


# =====================================================
# SAVE / LOAD HISTORY
# =====================================================

def save_session_to_file(session, filepath=HISTORY_FILE):
    """
    Appends this session's results to a JSON history file. Creates the
    file if it doesn't exist yet, or if it's empty/corrupt.
    """

    record = {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": round(session.total_duration_seconds(), 1),
        "exercises": [
            {
                "exercise": item.exercise_name,
                "target": item.target_value,
                "achieved": round(item.final_value, 1) if item.is_time_based else item.final_value,
                "completed": item.final_value >= item.target_value,
            }
            for item in session.items
        ],
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


# =====================================================
# BUILD A SESSION FROM TERMINAL INPUT
# =====================================================

def _prompt_target_value(exercise_name):
    """
    Asks the user for a target (reps or seconds) appropriate to the
    exercise, re-prompting on invalid input.
    """

    is_time_based = exercise_name in TIME_BASED_EXERCISES
    unit = "seconds to hold" if is_time_based else "reps"

    while True:

        raw = input(f"  Target {unit} for {exercise_name}: ").strip()

        try:
            value = int(raw)
        except ValueError:
            print("  Please enter a whole number.")
            continue

        if value <= 0:
            print("  Target must be greater than 0.")
            continue

        return value


def build_session_from_terminal():
    """
    Interactively builds a WorkoutSession by repeatedly asking the user
    to pick an exercise and a target, until they choose to stop.

    Returns a WorkoutSession with at least one item.
    """

    items = []

    print("\nBuild your planned session — add exercises one at a time.")

    while True:

        print("\nExercises:")
        for key, name in EXERCISE_MENU.items():
            print(f"  {key}. {name}")

        choice = input("Add exercise number (or press Enter to finish): ").strip()

        if choice == "":
            if len(items) == 0:
                print("Add at least one exercise before finishing.")
                continue
            break

        exercise_name = EXERCISE_MENU.get(choice)

        if exercise_name is None:
            print("Invalid choice, try again.")
            continue

        target_value = _prompt_target_value(exercise_name)

        items.append(SessionItem(exercise_name, target_value))

        print(f"  Added: {exercise_name} — {items[-1].target_label()}")

    print("\nSession queue:")
    for index, item in enumerate(items, start=1):
        print(f"  {index}. {item.exercise_name} — {item.target_label()}")
    print()

    return WorkoutSession(items)