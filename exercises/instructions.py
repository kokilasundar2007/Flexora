# =====================================================
# BEGINNER INSTRUCTIONS FOR EACH EXERCISE
# =====================================================

INSTRUCTIONS = {

    "squat": {
        "name": "Squat",
        "starting_position": "Stand with feet shoulder-width apart, toes pointing slightly outward.",
        "steps": [
            "Keep your chest up and back straight throughout the movement.",
            "Bend your knees and push your hips back, as if sitting into a chair.",
            "Lower until your thighs are roughly parallel to the floor.",
            "Push through your heels to stand back up to the starting position.",
        ],
        "common_mistakes": [
            "Letting your knees cave inward.",
            "Rounding your lower back.",
            "Not going low enough (partial squats).",
        ],
        "camera_tip": "Stand SIDEWAYS to the camera so your full body is visible from the side.",
    },

    "bicep_curl": {
        "name": "Bicep Curl",
        "starting_position": "Stand facing the camera, arms fully extended down by your sides.",
        "steps": [
            "Keep your upper arm and elbow still, close to your body.",
            "Curl the weight up by bending your elbow, bringing your hand toward your shoulder.",
            "Squeeze at the top, then slowly lower back to the starting position.",
        ],
        "common_mistakes": [
            "Swinging your body to help lift the weight.",
            "Moving your elbow forward or away from your body.",
            "Using momentum instead of controlled movement.",
        ],
        "camera_tip": "Face the camera directly so your arm movement is clearly visible.",
    },

    "lunge": {
        "name": "Lunge",
        "starting_position": "Stand upright with feet together.",
        "steps": [
            "Step one leg forward and lower your body until both knees are bent at about 90 degrees.",
            "Keep your front knee above your ankle, not pushed past your toes.",
            "Push back up through your front heel to return to standing.",
        ],
        "common_mistakes": [
            "Leaning your torso too far forward.",
            "Letting the front knee collapse inward.",
            "Not bending the back knee enough.",
        ],
        "camera_tip": "Stand SIDEWAYS to the camera so your front-to-back leg movement is visible.",
    },

    "plank": {
        "name": "Plank",
        "starting_position": "Get into a push-up position, resting on your forearms or hands, body in a straight line.",
        "steps": [
            "Keep your body in one straight line from shoulders to ankles.",
            "Engage your core and glutes to hold the position.",
            "Breathe steadily and hold for as long as you can with good form.",
        ],
        "common_mistakes": [
            "Letting your hips sag toward the floor.",
            "Piking your hips up too high.",
            "Holding your breath.",
        ],
        "camera_tip": "Position the camera at floor level, to the SIDE of your body, so your full body line is visible.",
    },

    "pushup": {
        "name": "Push-up",
        "starting_position": "Start in a plank position, hands slightly wider than shoulder-width.",
        "steps": [
            "Keep your body in a straight line from head to heels.",
            "Lower your body by bending your elbows until your chest is close to the floor.",
            "Push back up through your palms to full arm extension.",
        ],
        "common_mistakes": [
            "Letting your hips sag or pike.",
            "Flaring your elbows straight out to the sides.",
            "Not lowering far enough.",
        ],
        "camera_tip": "Position the camera at floor level, to the SIDE of your body, so your full body line is visible.",
    },

    "shoulder_press": {
        "name": "Shoulder Press",
        "starting_position": "Stand facing the camera, elbows bent, weights at shoulder height.",
        "steps": [
            "Press the weights straight overhead until your arms are fully extended.",
            "Keep your core tight and avoid arching your back.",
            "Slowly lower back to the starting shoulder-height position.",
        ],
        "common_mistakes": [
            "Leaning back to help push the weight up.",
            "Not fully extending your arms at the top.",
            "Pressing the weights forward instead of straight up.",
        ],
        "camera_tip": "Face the camera directly so your overhead arm movement is clearly visible.",
    },

    "side_lunge": {
        "name": "Side Lunge",
        "starting_position": "Stand with feet wide apart, facing the camera.",
        "steps": [
            "Shift your weight to one side, bending that knee while keeping the other leg straight.",
            "Lower your hips back and down over the bent knee.",
            "Push back through the bent leg to return to the starting position.",
        ],
        "common_mistakes": [
            "Letting the straight leg bend too much.",
            "Leaning your torso too far forward.",
            "Not bending the working knee deep enough.",
        ],
        "camera_tip": "Face the camera directly so your side-to-side movement is clearly visible.",
    },

}


# =====================================================
# DISPLAY FUNCTIONS
# =====================================================

def print_instructions(exercise_name):
    """
    Prints beginner-friendly instructions for the given exercise
    to the terminal, before the camera starts.
    """

    data = INSTRUCTIONS.get(exercise_name)

    if data is None:
        print(f"No instructions found for '{exercise_name}'.")
        return

    print("\n" + "=" * 50)
    print(f"HOW TO DO: {data['name']}")
    print("=" * 50)

    print(f"\nStarting Position:\n  {data['starting_position']}")

    print("\nSteps:")
    for i, step in enumerate(data["steps"], start=1):
        print(f"  {i}. {step}")

    print("\nCommon Mistakes to Avoid:")
    for mistake in data["common_mistakes"]:
        print(f"  - {mistake}")

    print(f"\nCamera Tip:\n  {data['camera_tip']}")

    print("\n" + "=" * 50)
    input("Press Enter when you're ready to start...\n")