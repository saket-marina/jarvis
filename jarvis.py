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
SILENCE_DURATION     = 1.2
MAX_RECORD_SECONDS   = 30
WAKE_WINDOW_SECONDS  = 2.0
WAKE_SLIDE_CHUNKS    = 8
FOLLOW_UP_SECONDS    = 4.0
INPUT_DEVICE_INDEX   = 0
MAX_HISTORY          = 10           # Max conversation turns to keep in memory
WAKE_WORDS           = ["jarvis", "davis", "travis", "barvis", "jervis", "journey", "javis"]
WHISPER_HALLUCINATIONS = [
    "thank you", "thanks for watching", "thanks for listening",
    "please subscribe", ".", "..", "...", "bye", "goodbye",
    "have a good day", "have a nice day",
    "have a safe harvest", "says america", "have a safe harvest says america",
    "like and subscribe", "don't forget to subscribe", "we'll see you next time"
]

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
    subprocess.Popen(["afplay", os.path.join(os.path.dirname(os.path.abspath(__file__)), "activate.wav")])

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
    follow_up_chunks = int(FOLLOW_UP_SECONDS * SAMPLE_RATE / CHUNK)
    for _ in range(follow_up_chunks):
        data = stream.read(CHUNK, exception_on_overflow=False)
        if _rms(data) > SILENCE_THRESHOLD:
            return True
    return False

def is_hallucination(text: str) -> bool:
    t = text.lower().strip().strip(".,!?")
    if len(t) < 2:
        return True
    # Filter non-ASCII (Chinese, Arabic, etc. hallucinations)
    if any(ord(c) > 127 for c in t):
        return True
    return any(h in t for h in WHISPER_HALLUCINATIONS)

def contains_wake_word(text: str) -> bool:
    return any(w in text.lower() for w in WAKE_WORDS)

def get_weather_brief() -> str:
    try:
        url = "https://wttr.in/Seattle?format=3"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.64.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode().strip()
    except:
        return "Weather unavailable."

def startup_briefing():
    """JARVIS gives a brief on boot: time + weather."""
    hour = int(time.strftime("%H"))
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    weather = get_weather_brief()
    t = time.strftime("%I:%M %p").lstrip("0")
    briefing = f"{greeting}, Boss. It's {t}. {weather}. Systems are online and ready."
    log("🌅 BRIEFING", briefing, C.CYAN)
    speak(briefing)

def query_jarvis(user_text: str, history: list) -> tuple:
    """Returns (spoken_response, commands_list, calendar_days)."""
    if not AWS_API_URL:
        return "API URL not configured.", [], None
    payload = json.dumps({"message": user_text, "history": history}).encode()
    req = urllib.request.Request(
        AWS_API_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            return (
                body.get("response", "No response."),
                body.get("commands", []),
                body.get("calendar_days", None)
            )
    except urllib.error.HTTPError as e:
        return f"Backend error {e.code}.", [], None
    except Exception as e:
        return f"Connection error: {e}", [], None

def run_command(command: str):
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

    startup_briefing()
    print(f"\n{C.DIM}Listening for wake word...{C.RESET}\n")

    # Session-level conversation history
    history = []

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1,
                     rate=SAMPLE_RATE, input=True,
                     input_device_index=INPUT_DEVICE_INDEX,
                     frames_per_buffer=CHUNK)

    ring = collections.deque(maxlen=WINDOW_CHUNKS)
    chunks_since_last_check = 0

    try:
        while True:
            # ── Phase 1: Wake word detection ──────────────────────────────
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
                                      condition_on_previous_text=False,
                                      suppress_blank=True)
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
                result = model.transcribe(audio_path, language="en", fp16=False,
                                          suppress_blank=True)
                command = result["text"].strip()
                os.unlink(audio_path)

                if not command or is_hallucination(command):
                    speak("I didn't catch that.")
                    break

                log("🗣️  YOU SAID", command, C.GREEN)
                log("🌐 QUERYING", "Sending to JARVIS backend...", C.YELLOW)
                response, commands, calendar_days = query_jarvis(command, history)

                log("🤖 JARVIS", response, C.CYAN)

                if response.strip() == "SUIT_UP":
                    response = "Initializing suit assembly sequence, Boss."
                    subprocess.Popen(["afplay", os.path.join(os.path.dirname(os.path.abspath(__file__)), "suitup.wav")])
                    speak(response)
                else:
                    speak(response)
                    for cmd in commands:
                        log("⚙️  EXEC", cmd, C.YELLOW)
                        subprocess.Popen(cmd, shell=True)
                        time.sleep(0.5)

                # Update history
                history.append({"role": "user", "content": command})
                history.append({"role": "assistant", "content": response})
                if len(history) > MAX_HISTORY * 2:
                    history = history[-(MAX_HISTORY * 2):]

                # Wait for follow-up
                log("🔁 WAITING", f"Listening for follow-up ({FOLLOW_UP_SECONDS:.0f}s)...", C.DIM)
                if not wait_for_followup(stream):
                    log("💤 IDLE", "No follow-up. Back to wake word.", C.DIM)
                    break

            print(f"{C.CYAN}{'─'*50}{C.RESET}\n")
            print(f"{C.DIM}Listening for wake word...{C.RESET}\n")
            ring.clear()

    except KeyboardInterrupt:
        print(f"\n{C.DIM}JARVIS offline.{C.RESET}")
        speak("JARVIS offline. Goodbye, Boss.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

if __name__ == "__main__":
    main()