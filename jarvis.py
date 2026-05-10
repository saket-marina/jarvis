#!/usr/bin/env python3
"""
JARVIS - Voice Assistant
Wake word: "Jarvis" (Whisper sliding window)
Command:   Whisper small (local, fast)
Voice:     Daniel (macOS TTS)
"""

import os
import time
import json
import wave
import struct
import tempfile
import subprocess
import collections
import urllib.request
import urllib.error
import numpy as np
import pyaudio
import whisper

# ── Config ────────────────────────────────────────────────────────────────────
AWS_API_URL          = os.environ.get("JARVIS_API_URL", "")
WHISPER_MODEL        = "small"
TTS_VOICE            = "Daniel"
TTS_RATE             = 230
SAMPLE_RATE          = 16000
CHUNK                = 1024
SILENCE_THRESHOLD    = 200
SILENCE_DURATION     = 1.5
MAX_RECORD_SECONDS   = 30
WAKE_WINDOW_SECONDS  = 2.0
WAKE_SLIDE_CHUNKS    = 8
FOLLOW_UP_SECONDS    = 4.0        # How long to wait for a follow-up after response
INPUT_DEVICE_INDEX   = 0
WAKE_WORDS           = ["jarvis", "davis", "travis", "barvis", "jervis", "journey", "javis"]

WINDOW_CHUNKS = int(SAMPLE_RATE * WAKE_WINDOW_SECONDS / CHUNK)

# ── Colors ────────────────────────────────────────────────────────────────────
class C:
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    DIM    = "\033[2m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def banner():
    print(f"""
{C.CYAN}{C.BOLD}
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
{C.RESET}{C.DIM}  Just A Rather Very Intelligent System{C.RESET}
""")

def chime():
    """Play activation sound non-blocking."""
    subprocess.Popen(["afplay", os.path.join(os.path.dirname(__file__), "activate.wav")])

def speak(text: str):
    clean = text.replace("**","").replace("*","").replace("`","").replace("#","")
    subprocess.run(["say", "-v", TTS_VOICE, "-r", str(TTS_RATE), clean], check=False)

def log(label: str, msg: str, color=C.CYAN):
    ts = time.strftime("%H:%M:%S")
    print(f"{C.DIM}[{ts}]{C.RESET} {color}{C.BOLD}{label}{C.RESET}  {msg}")

def _rms(raw: bytes) -> float:
    count = len(raw) // 2
    if count == 0:
        return 0
    shorts = struct.unpack(f"{count}h", raw[:count * 2])
    return (sum(s * s for s in shorts) / count) ** 0.5

def frames_to_wav(frames: list) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return tmp_path

def record_command(stream) -> str:
    """Record until silence, return path to WAV."""
    frames = []
    silent_chunks = 0
    silent_limit = int(SILENCE_DURATION * SAMPLE_RATE / CHUNK)

    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
        rms = _rms(data)
        silent_chunks = silent_chunks + 1 if rms < SILENCE_THRESHOLD else 0
        total = len(frames) * CHUNK / SAMPLE_RATE
        if silent_chunks >= silent_limit or total >= MAX_RECORD_SECONDS:
            break

    return frames_to_wav(frames)

def wait_for_followup(stream) -> bool:
    """Wait up to FOLLOW_UP_SECONDS for sound. Returns True if sound detected."""
    follow_up_chunks = int(FOLLOW_UP_SECONDS * SAMPLE_RATE / CHUNK)
    for _ in range(follow_up_chunks):
        data = stream.read(CHUNK, exception_on_overflow=False)
        if _rms(data) > SILENCE_THRESHOLD:
            return True
    return False

WHISPER_HALLUCINATIONS = [
    "thank you", "thanks for watching", "thanks for listening",
    "please subscribe", "you", ".", "..", "...", "bye", "goodbye",
    "see you", "see you next time", "have a good day", "have a nice day",
    "have a safe harvest", "says america", "have a safe harvest says america",
    "like and subscribe", "don't forget to subscribe", "we'll see you next time"
]

def is_hallucination(text: str) -> bool:
    t = text.lower().strip().strip(".,!?")
    if len(t) < 2:
        return True
    return any(h in t for h in WHISPER_HALLUCINATIONS)

def contains_wake_word(text: str) -> bool:
    return any(w in text.lower() for w in WAKE_WORDS)

def query_jarvis(user_text: str) -> tuple:
    """Returns (spoken_response, command_or_None)."""
    if not AWS_API_URL:
        return "API URL not configured.", None
    payload = json.dumps({"message": user_text}).encode()
    req = urllib.request.Request(
        AWS_API_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            return body.get("response", "No response."), body.get("command", None)
    except urllib.error.HTTPError as e:
        return f"Backend error {e.code}.", None
    except Exception as e:
        return f"Connection error: {e}", None

def fetch_calendar(days: int = 1) -> str:
    """Read calendar events for the next N days via AppleScript."""
    script = f'''
    set output to ""
    set today to current date
    set startOfDay to today - (time of today)
    set endOfDay to startOfDay + ({days} * 86400) - 1
    tell application "Calendar"
        repeat with cal in calendars
            set evts to (every event of cal whose start date >= startOfDay and start date <= endOfDay)
            repeat with e in evts
                set output to output & summary of e & " on " & (start date of e as string) & "\\n"
            end repeat
        end repeat
    end tell
    return output
    '''
    try:
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or f"No events in the next {days} day(s)."
    except Exception as e:
        return f"Calendar error: {e}"

def run_command(command: str):
    """Execute a shell command on the Mac."""
    try:
        subprocess.Popen(command, shell=True)
        log("⚙️  EXEC", command, C.YELLOW)
    except Exception as e:
        log("❌ CMD ERROR", str(e), C.RED)

def main():
    banner()

    if not AWS_API_URL:
        print(f"{C.YELLOW}⚠️  JARVIS_API_URL not set.{C.RESET}\n")

    log("⏳ LOADING", "Whisper small model...", C.YELLOW)
    model = whisper.load_model(WHISPER_MODEL)
    log("✅ WHISPER", "Loaded.", C.GREEN)

    speak("JARVIS online. Say JARVIS to activate.")
    print(f"\n{C.DIM}Listening for wake word...{C.RESET}\n")

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1,
                     rate=SAMPLE_RATE, input=True,
                     input_device_index=INPUT_DEVICE_INDEX,
                     frames_per_buffer=CHUNK)

    ring = collections.deque(maxlen=WINDOW_CHUNKS)
    chunks_since_last_check = 0

    try:
        while True:
            # ── Phase 1: Wake word detection (sliding window) ─────────────
            data = stream.read(CHUNK, exception_on_overflow=False)
            ring.append(data)
            chunks_since_last_check += 1

            if len(ring) < WINDOW_CHUNKS:
                continue
            if chunks_since_last_check < WAKE_SLIDE_CHUNKS:
                continue

            chunks_since_last_check = 0

            if _rms(b"".join(ring)) < SILENCE_THRESHOLD:
                continue

            clip_path = frames_to_wav(list(ring))
            result = model.transcribe(clip_path, language="en", fp16=False,
                                      condition_on_previous_text=False)
            os.unlink(clip_path)
            heard = result["text"].strip()

            if heard and not is_hallucination(heard):
                log("👂 HEARD", heard, C.DIM)

            if is_hallucination(heard) or not contains_wake_word(heard):
                continue

            # ── Phase 2: Wake word detected ───────────────────────────────
            print(f"\n{C.CYAN}{'─'*50}{C.RESET}")
            log("⚡ ACTIVATED", f"Wake word: '{heard}'", C.CYAN)
            chime()
            ring.clear()

            # ── Phase 3: Conversation loop ────────────────────────────────
            while True:
                log("🎙️  LISTENING", "Speak your command...", C.GREEN)
                audio_path = record_command(stream)

                log("🔍 TRANSCRIBING", "Running Whisper...", C.YELLOW)
                result = model.transcribe(audio_path, language="en", fp16=False)
                command = result["text"].strip()
                os.unlink(audio_path)

                if not command or is_hallucination(command):
                    speak("I didn't catch that.")
                    break

                log("🗣️  YOU SAID", command, C.GREEN)
                log("🌐 QUERYING", "Sending to JARVIS backend...", C.YELLOW)
                response, shell_cmd = query_jarvis(command)

                if shell_cmd and shell_cmd.startswith("FETCH_CALENDAR"):
                    days = int(shell_cmd.split(":")[1]) if ":" in shell_cmd else 1
                    log("📅 CALENDAR", f"Reading calendar ({days} day(s))...", C.YELLOW)
                    events = fetch_calendar(days)
                    response, shell_cmd = query_jarvis(f"My calendar events for the next {days} day(s): {events}. Summarize this naturally in 1-2 sentences.")

                log("🤖 JARVIS", response, C.CYAN)
                if shell_cmd and not shell_cmd.startswith("FETCH_CALENDAR"):
                    run_command(shell_cmd)
                speak(response)

                # Wait for follow-up — if silent, drop back to wake word mode
                log("🔁 WAITING", f"Listening for follow-up ({FOLLOW_UP_SECONDS:.0f}s)...", C.DIM)
                if not wait_for_followup(stream):
                    log("💤 IDLE", "No follow-up. Back to wake word.", C.DIM)
                    break

            print(f"{C.CYAN}{'─'*50}{C.RESET}\n")
            print(f"{C.DIM}Listening for wake word...{C.RESET}\n")
            ring.clear()

    except KeyboardInterrupt:
        print(f"\n{C.DIM}JARVIS offline.{C.RESET}")
        speak("JARVIS offline. Goodbye.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

if __name__ == "__main__":
    main()