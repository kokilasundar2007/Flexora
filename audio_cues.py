"""
audio_cues.py — beeps and spoken cues for Flexora AI.

Everything is played on a background thread, so the camera loop never
freezes while a sound (or a spoken sentence) is playing.

- Beeps use winsound (built into Windows, nothing to install).
- Speech tries these backends in order and uses the first that works:
    1. A small background PowerShell process using Windows' built-in
       voice (nothing to install, and it runs outside Python so it can't
       get stuck the way in-process speech engines sometimes do)
    2. Windows SAPI through pywin32
    3. pyttsx3
  If none work, it falls back to beeps only. Nothing crashes either way.
"""

import base64
import queue
import subprocess
import threading

try:
    import winsound
except ImportError:  # not running on Windows
    winsound = None

try:
    import pyttsx3
except ImportError:  # not installed
    pyttsx3 = None


# Each pattern is a list of (frequency_hz, duration_ms) beeps.
BEEP_PATTERNS = {
    "rep": [(1000, 60)],
    "tick": [(700, 90)],
    "go": [(1500, 300)],
    "target": [(880, 120), (1175, 120), (1568, 220)],
    "complete": [(880, 150), (1047, 150), (1319, 150), (1760, 400)],
}


# =====================================================
# SPEECH BACKENDS
# Every backend has: speak(text, interrupt=False) and wait(timeout_seconds)
# =====================================================

# Runs inside the PowerShell process: reads one sentence per line from
# stdin and speaks it. A leading "!" means "cut off whatever is playing".
_POWERSHELL_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = 1
[Console]::Out.WriteLine('READY')
[Console]::Out.Flush()
while (($line = [Console]::In.ReadLine()) -ne $null) {
    if ($line.StartsWith('!')) { $s.SpeakAsyncCancelAll(); $line = $line.Substring(1) }
    if ($line.Length -gt 0) { [void]$s.SpeakAsync($line) }
}
while ($s.State -eq 'Speaking') { Start-Sleep -Milliseconds 100 }
"""


class _PowerShellSpeaker:
    """
    Keeps one PowerShell process alive and feeds it sentences. Speech
    happens outside Python, so every rep number is spoken reliably and a
    new number cuts off the previous one (no lag).
    """

    name = "Windows voice via PowerShell"

    def __init__(self, command=None):
        if command is None:
            encoded = base64.b64encode(_POWERSHELL_SCRIPT.encode("utf-16-le")).decode()
            command = [
                "powershell.exe", "-NoProfile", "-NoLogo", "-NonInteractive",
                "-EncodedCommand", encoded,
            ]

        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # The script prints READY once the voice is loaded. If PowerShell
        # failed to start, the pipe closes and we raise so the next backend runs.
        if self._process.stdout.readline().strip() != "READY":
            raise RuntimeError("PowerShell voice did not start")

    def speak(self, text, interrupt=False):
        text = text.replace("\r", " ").replace("\n", " ").strip()

        if not text:
            return

        self._process.stdin.write(("!" if interrupt else "") + text + "\n")
        self._process.stdin.flush()

    def wait(self, timeout_seconds):
        """Closing stdin tells the script to finish speaking and exit."""

        try:
            self._process.stdin.close()
            self._process.wait(timeout=timeout_seconds)
        except Exception:
            self._process.kill()


class _SapiSpeaker:
    """Talks to the Windows speech engine directly through pywin32."""

    name = "Windows SAPI"

    def __init__(self):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()  # each thread must initialise COM
        self._voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._voice.Rate = 1  # -10 (slow) .. 10 (fast)

    def speak(self, text, interrupt=False):
        flags = 1  # SVSFlagsAsync: don't wait for the sentence to finish
        if interrupt:
            flags |= 2  # SVSFlagsPurgeBeforeSpeak: cut off whatever is playing
        self._voice.Speak(text, flags)

    def wait(self, timeout_seconds):
        self._voice.WaitUntilDone(int(timeout_seconds * 1000))


class _Pyttsx3Speaker:
    """
    Last resort. Uses a fresh pyttsx3 engine for every sentence, because
    reusing one engine inside a thread often speaks only the first sentence.
    """

    name = "pyttsx3"

    def __init__(self):
        if pyttsx3 is None:
            raise RuntimeError("pyttsx3 is not installed")

    def speak(self, text, interrupt=False):
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        del engine

    def wait(self, timeout_seconds):
        pass  # speak() already blocks until the sentence is finished


def _create_speaker():
    """Returns the first speech backend that starts, or None."""

    problems = []

    for backend in (_PowerShellSpeaker, _SapiSpeaker, _Pyttsx3Speaker):
        try:
            return backend()
        except Exception as error:
            problems.append(f"{backend.name}: {error}")

    print("[audio] Speech unavailable, using beeps only. " + " | ".join(problems))
    return None


# =====================================================
# AUDIO CUES
# =====================================================

class AudioCues:
    """
    Usage (from the camera loop):

        cues = AudioCues()
        cues.rep(count)               # every frame with the current rep count
        cues.target_reached()         # exercise target hit
        cues.rest_start("pushup")     # rest begins, announces what's next
        cues.rest_tick(seconds_left)  # every frame while resting (3-2-1 beeps)
        cues.go()                     # rest over, next exercise starts
        cues.workout_complete()       # whole session finished
        cues.reset()                  # exercise changed, restart rep counting
        cues.close()                  # at the very end, lets the last sound finish
    """

    def __init__(self, beeps=True, speech=True, speak_reps=True, debug=False):
        """
        beeps: play beeps (Windows only)
        speech: use spoken cues if a speech backend is available
        speak_reps: say each rep number out loud (otherwise a short beep per rep)
        debug: print every cue to the terminal (handy for troubleshooting)
        """

        self.beeps_enabled = beeps and winsound is not None
        self.speak_reps = speak_reps
        self.debug = debug

        self._speech_wanted = speech
        self.speech_enabled = False  # set by the worker once the voice is ready

        self._queue = queue.Queue()
        self._ready = threading.Event()

        self._last_rep = 0
        self._last_tick = None

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        # Wait so we know whether speech works before the camera starts
        self._ready.wait(timeout=10)

    # -------------------------------------------------
    # BACKGROUND WORKER
    # -------------------------------------------------

    def _worker(self):
        speaker = _create_speaker() if self._speech_wanted else None

        self.speech_enabled = speaker is not None

        if speaker is not None:
            print(f"[audio] Speech ready ({speaker.name})")

        self._ready.set()

        while True:

            task = self._queue.get()

            if task is None:
                break

            kind, payload, interrupt = task

            try:
                if kind == "beep":
                    for frequency, duration in BEEP_PATTERNS[payload]:
                        winsound.Beep(frequency, duration)

                elif kind == "say" and speaker is not None:
                    speaker.speak(payload, interrupt=interrupt)

                if self.debug:
                    print(f"[audio] played {kind}: {payload}")

            except Exception as error:
                print(f"[audio] {kind} failed: {error}")

                if kind == "say":
                    speaker = None
                    self.speech_enabled = False

        # Let the last spoken sentence finish before the thread ends
        if speaker is not None:
            try:
                speaker.wait(10)
            except Exception:
                pass

    def _beep(self, name):
        if self.beeps_enabled:
            self._queue.put(("beep", name, False))

    def _say(self, text, interrupt=False):
        if self.speech_enabled:
            self._queue.put(("say", text, interrupt))

    # -------------------------------------------------
    # CUES
    # -------------------------------------------------

    def reset(self):
        """Call when the active exercise changes or a rest ends."""

        self._last_rep = 0
        self._last_tick = None

    def rep(self, count):
        """
        Call every frame with the current rep count. Only reacts when the
        count goes up. Speaks the number, or beeps if speech isn't available.
        """

        if count is None or count <= self._last_rep:
            return

        self._last_rep = count

        if self.speak_reps and self.speech_enabled:
            self._say(str(int(count)), interrupt=True)
        else:
            self._beep("rep")

    def say(self, text, interrupt=False):
        """Speaks any short message (used for voice-command confirmations)."""

        self._say(text, interrupt)

    def target_reached(self):
        self._beep("target")

    def rest_start(self, next_exercise_name):
        self._last_tick = None
        self._say(f"Rest. Next up, {next_exercise_name.replace('_', ' ')}")

    def rest_tick(self, seconds_left):
        """Beeps once for each of the last 3 seconds of a rest."""

        if seconds_left in (1, 2, 3) and seconds_left != self._last_tick:
            self._last_tick = seconds_left
            self._beep("tick")

    def go(self):
        self._beep("go")

    def workout_complete(self):
        self._beep("complete")
        self._say("Workout complete. Great job!")

    def close(self, timeout=15):
        """Lets any queued sound finish, then stops the background thread."""

        self._queue.put(None)
        self._thread.join(timeout=timeout)