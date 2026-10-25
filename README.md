# Flexora AI
A real-time AI workout assistant that uses your webcam to count reps, time holds, and check your form. It runs locally in Python with OpenCV and MediaPipe Pose, and can be controlled by voice.
> Flexora AI is a learning project. Its form checks are simple angle-based rules, not medical or professional coaching advice.
## Features
- **Live pose tracking** with MediaPipe's Pose Landmarker, drawn as a skeleton overlay on the camera feed
- **Rep counting and form feedback** for 7 exercises, based on joint angles (knee, hip, elbow, back/torso lean)
- **Plank timer** that only counts time while your form is good, and tracks your best hold
- **Two workout modes**
  - **Freestyle:** pick one exercise and go
  - **Planned session:** build a queue of exercises with rep or time targets, with automatic rest periods between them
- **Hands-free voice commands** (offline, via Vosk) to switch exercises, skip rest, or stop the workout
- **Audio cues:** beeps and spoken announcements for reps, targets reached, rest countdown, and workout completion
- **Post-workout report** with results per exercise, total time, and plain-language suggestions
- **Workout history** saved to `workout_history.json`
- **Graceful fallbacks:** if voice or speech libraries are missing, the workout still runs
## Supported exercises
| Exercise | Tracked as | Notes |
|---|---|---|
| Squat | Reps | Needs a side-on view |
| Bicep curl | Reps | Face the camera |
| Lunge | Reps | Needs a side-on view |
| Plank | Hold time (seconds) | Needs a side-on view |
| Push-up | Reps | Needs a side-on view |
| Shoulder press | Reps | |
| Side lunge | Reps | |
For exercises that need a side-on view, the app shows an on-screen prompt if it detects you are facing the camera. Each exercise also prints beginner instructions (starting position, steps, common mistakes, camera tip) before it starts.
## How it works
Webcam frame
    -> MediaPipe Pose Landmarker (33 body landmarks)
    -> Joint angles calculated from landmark coordinates
    -> Exercise module: form check + rep/hold state machine
    -> WorkoutState / WorkoutSession: which exercise is active, targets, rest
    -> On-screen HUD + audio cues + end-of-workout summary
Each exercise lives in its own module under `exercises/` and exposes the same three pieces: an angle function, a form checker, and a counter (or timer). A rep is counted when the joint angle passes a "down" threshold and then returns to an "up" threshold. For example, a squat counts when the knee angle drops to 120 degrees or less and then returns to 160 degrees or more. These thresholds are constants at the top of each file and can be tuned.
Voice recognition and speech run on background threads so the camera loop is never blocked.
## UML diagrams
Design diagrams are in the(UML) folder: class, activity,data flow diagram,use case diagram
## Getting started
### Requirements
- Python 3.9 or newer (use a version supported by your installed MediaPipe release)
- A webcam
- **Windows** is recommended. Beeps use `winsound` and the default speech backend uses Windows' built-in voice. On other systems the app still runs, but audio cues are limited (speech falls back to `pyttsx3` if installed).
- A microphone (optional, for voice commands)
### Installation
git clone https://github.com/<your-username>/Flexora.git
cd Flexora
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install opencv-python mediapipe
Optional packages:
pip install vosk sounddevice   # voice commands
pip install pyttsx3            # speech fallback (non-Windows)
pip install pywin32            # speech fallback (Windows SAPI)
The MediaPipe pose model (`models/pose_landmarker_full.task`) is already included in the repo.
### Optional: enable voice commands
1. Download the small English Vosk model: <https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip>
2. Unzip it so this folder exists: 
   models/vosk-model-small-en-us-0.15/
If Vosk, `sounddevice`, the model, or a microphone is missing, voice control stays off with a message and the workout runs normally.
### Run
python main.py
You will be asked to choose a mode:
1. **Freestyle:** pick one exercise from the menu
2. **Planned session:** add exercises one at a time with a rep or seconds target, then set the rest time between exercises (default 30 seconds)
Make sure your full body is visible to the camera, then start moving.
## Controls
| Input | Action |
|---|---|
| `Q` | Quit the workout |
| `S` | Skip the current rest |

Structure:
Flexora/
├── main.py               # Entry point: camera loop, HUD, mode selection
├── pose_detection.py     # MediaPipe Pose Landmarker setup and detection
├── angle_calculation.py  # Joint angle helpers
├── exercises/            # One module per exercise (angles, form check, counter)
│   ├── squat.py
│   ├── bicep_curl.py
│   ├── lunge.py
│   ├── plank.py
│   ├── pushup.py
│   ├── shoulder_press.py
│   ├── side_lunge.py
│   └── instructions.py   # Beginner instructions shown before each exercise
├── session.py            # Planned session queue and targets
├── workout_state.py      # Active exercise, rest periods, counter resets
├── workout_summary.py    # Post-workout report, suggestions, history saving
├── voice_commands.py     # Offline voice control (Vosk)
├── audio_cues.py         # Beeps and spoken cues
├── models/               # MediaPipe model (and optional Vosk model)
├── UML/                  # Design diagrams
└── workout_history.json  # Saved workout results
## Known limitations
- **Single person, single camera.** Only the first detected person is used, and the webcam is fixed to the default device (index 0).
- **2D angle heuristics.** Form checks use angles from a single camera view, so results depend on camera angle, lighting, clothing, and distance. Thresholds are tuned by hand and may need adjusting for your setup.
- **Side-on exercises are sensitive to position.** If your body is partly out of frame, the app shows "Body not fully visible" and pauses counting.
- **Audio is Windows-first.** Beeps and the default text-to-speech rely on Windows features.
- **Command-line setup.** Workouts are configured in the terminal; there is no graphical menu yet.
- **No automated tests** at the moment.
## Roadmap
- [ ] `requirements.txt` for one-step installs
- [ ] Cross-platform audio cues
- [ ] Graphical front end (the camera loop is already structured around a single `run_workout(state)` entry point)
- [ ] Workout history viewer and progress charts
- [ ] Per-user threshold calibration
- [ ] Unit tests for angle and counter logic
## Tech stack
Python, OpenCV, MediaPipe (Pose Landmarker), Vosk, sounddevice, pyttsx3 / Windows SAPI.
