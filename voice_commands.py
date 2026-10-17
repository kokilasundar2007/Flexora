"""
voice_commands.py — hands-free control for Flexora AI.

Listens to the microphone on a background thread (offline, using Vosk)
and turns spoken phrases into commands. The camera loop asks for new
commands once per frame with poll() — no audio work happens on the main
thread, so the video never stutters.

Setup (with your venv active):
    pip install vosk sounddevice
Then download the small English model
    https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
and unzip it so this folder exists:
    <project folder>\\models\\vosk-model-small-en-us-0.15

If Vosk, sounddevice, the model or a microphone is missing, voice control
simply stays off (with a clear message) and the workout runs normally.
"""

import json
import os
import queue
import threading

try:
    import sounddevice
except ImportError:  # not installed
    sounddevice = None

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
except ImportError:  # not installed
    Model = None
    KaldiRecognizer = None
    SetLogLevel = None


MODEL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models",
    "vosk-model-small-en-us-0.15",
)

SAMPLE_RATE = 16000

# What you can say -> the command it produces.
# You can also say it naturally, e.g. "change to squat" or "switch to push up".
# Commands are (kind, value):
#   ("switch", exercise_name)   switch to that exercise
#   ("skip_rest", None)         end the rest early
#   ("stop", None)              end the workout
# Several phrases can map to the same command. Recognition is limited to
# exactly these phrases, which keeps it accurate even with gym noise.
PHRASES = {
    "squat": ("switch", "squat"),
    "squats": ("switch", "squat"),

    "bicep curl": ("switch", "bicep_curl"),
    "biceps curl": ("switch", "bicep_curl"),
    "bicep curls": ("switch", "bicep_curl"),
    "curl": ("switch", "bicep_curl"),
    "curls": ("switch", "bicep_curl"),

    "lunge": ("switch", "lunge"),
    "lunges": ("switch", "lunge"),

    "plank": ("switch", "plank"),

    "push up": ("switch", "pushup"),
    "push ups": ("switch", "pushup"),
    "pushup": ("switch", "pushup"),
    "pushups": ("switch", "pushup"),

    "shoulder press": ("switch", "shoulder_press"),
    "overhead press": ("switch", "shoulder_press"),

    "side lunge": ("switch", "side_lunge"),
    "side lunges": ("switch", "side_lunge"),

    "skip rest": ("skip_rest", None),
    "skip": ("skip_rest", None),

    # Two words on purpose, so a stray "stop" doesn't end your workout
    "stop workout": ("stop", None),
    "end workout": ("stop", None),
    "finish workout": ("stop", None),
}


# Natural ways to ask for an exercise, e.g. "change to squat", "switch to push up".
# The bare exercise name ("squat") still works too.
SWITCH_PREFIXES = [
    "change to",
    "switch to",
    "change exercise to",
    "switch exercise to",
    "go to",
    "start",
    "do",
    "let's do",
]


def _build_grammar():
    """Every phrase the recognizer is allowed to hear."""

    phrases = set(PHRASES)

    for alias, (kind, _value) in PHRASES.items():
        if kind == "switch":
            for prefix in SWITCH_PREFIXES:
                phrases.add(f"{prefix} {alias}")

    return sorted(phrases) + ["[unk]"]


def match_command(text):
    """
    Turns what was heard into a command, or None.
    Matches an exact phrase first, then looks for a known phrase inside
    the sentence (longest first, so "side lunge" wins over "lunge").
    """

    words = " ".join(text.replace("[unk]", " ").split())

    if not words:
        return None

    if words in PHRASES:
        return PHRASES[words]

    padded = f" {words} "

    for alias in sorted(PHRASES, key=len, reverse=True):
        if f" {alias} " in padded:
            return PHRASES[alias]

    return None


class VoiceCommands:
    """
    Usage:

        voice = VoiceCommands()
        voice.start()                 # loads the model, starts listening
        for command in voice.poll():  # every frame, returns new commands
            ...
        voice.close()                 # at the very end
    """

    def __init__(self, debug=True):
        self.debug = debug
        self.enabled = False

        self._commands = queue.Queue()
        self._audio = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    # -------------------------------------------------
    # START / STOP
    # -------------------------------------------------

    def start(self):
        """
        Starts listening. Returns True if voice control is on, False if
        something is missing (a message explains what to do).
        """

        if Model is None or sounddevice is None:
            print("[voice] Voice commands are off: run  pip install vosk sounddevice")
            return False

        if not os.path.isdir(MODEL_DIR):
            print("[voice] Voice commands are off: model not found.")
            print("        Download vosk-model-small-en-us-0.15 from")
            print("        https://alphacephei.com/vosk/models and unzip it to:")
            print(f"        {MODEL_DIR}")
            return False

        self.enabled = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return True

    def close(self):
        """Stops listening."""

        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=3)

    # -------------------------------------------------
    # BACKGROUND LISTENER
    # -------------------------------------------------

    def _on_audio(self, indata, frames, time_info, status):
        """Called by sounddevice with each chunk of microphone audio."""

        self._audio.put(bytes(indata))

    def _listen(self):
        try:
            SetLogLevel(-1)  # silence Vosk's console logging

            model = Model(MODEL_DIR)

            # Limit recognition to our phrases; "[unk]" catches everything else
            grammar = json.dumps(_build_grammar())
            recognizer = KaldiRecognizer(model, SAMPLE_RATE, grammar)

            with sounddevice.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=self._on_audio,
            ):
                print("[voice] Listening for commands")

                while not self._stop.is_set():

                    try:
                        data = self._audio.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    if recognizer.AcceptWaveform(data):

                        text = json.loads(recognizer.Result()).get("text", "").strip()

                        command = match_command(text)

                        if self.debug and text:
                            if command is not None:
                                print(f'[voice] heard: "{text}"  ->  {command[0]} {command[1] or ""}'.rstrip())
                            else:
                                print(f'[voice] heard: "{text}"  ->  no matching command')

                        if command is not None:
                            self._commands.put(command)

        except Exception as error:
            self.enabled = False
            print(f"[voice] Voice commands stopped: {error}")

    # -------------------------------------------------
    # USED BY THE CAMERA LOOP
    # -------------------------------------------------

    def poll(self):
        """Returns a list of the commands heard since the last call."""

        commands = []

        while True:
            try:
                commands.append(self._commands.get_nowait())
            except queue.Empty:
                break

        return commands