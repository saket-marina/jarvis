#!/usr/bin/env python3
"""
JARVIS - Voice Assistant
Wake word: "Jarvis" (Whisper-based, fully local)
Command:   Whisper medium (local, accurate)
Voice:     Daniel (macOS TTS)
"""

import os
import time
import json
import wave
import struct
import tempfile
import subprocess
import urllib.request
import urllib.error
import numpy as np
import pyaudio
import whisper

# ── Config ────────────────────────────────────────────────────────────────────
AWS_API_URL        = os.environ.get("JARVIS_API_URL", "")
WHISPER_MODEL      = "medium"
TTS_VOICE          = "Daniel"
TTS_RATE           = 200
SAMPLE_RATE        = 16000
CHUNK              = 1024
SILENCE_THRESHOLD  = 200
SILENCE_DURATION   = 1.5
MAX_RECORD_SECONDS = 30
WAKE_CLIP_SECONDS  = 2.0
INPUT_DEVICE_INDEX = 0
WAKE_WORDS         = ["jarvis", "davis", "travis", "barvis"]

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

def record_clip(pa, seconds: float) -> str:
    frames_needed = int(SAMPLE_RATE * seconds / CHUNK)
    stream = pa.open(format=pyaudio.paInt16, channels=1,
                     rate=SAMPLE_RATE, input=True,
                     input_device_index=INPUT_DEVICE_INDEX,
                     frames_per_buffer=CHUNK)
    frames = []
    try:
        for _ in range(frames_needed):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
    finally:
        stream.stop_stream()
        stream.close()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return tmp_path

def record_command(pa) -> str:
    log("🎙️  LISTENING", "Speak your command...", C.GREEN)
    stream = pa.open(format=pyaudio.paInt16, channels=1,
                     rate=SAMPLE_RATE, input=True,
                     input_device_index=INPUT_DEVICE_INDEX,
                     frames_per_buffer=CHUNK)
    frames = []
    silent_chunks = 0
    silent_limit = int(SILENCE_DURATION * SAMPLE_RATE / CHUNK)

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
            rms = _rms(data)
            silent_chunks = silent_chunks + 1 if rms < SILENCE_THRESHOLD else 0
            total = len(frames) * CHUNK / SAMPLE_RATE
            if silent_chunks >= silent_limit or total >= MAX_RECORD_SECONDS:
                break
    finally:
        stream.stop_stream()
        stream.close()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return tmp_path

def contains_wake_word(text: str) -> bool:
    text = text.lower().strip()
    return any(w in text for w in WAKE_WORDS)

def query_jarvis(user_text: str) -> str:
    if not AWS_API_URL:
        return "API URL not configured."
    payload = json.dumps({"message": user_text}).encode()
    req = urllib.request.Request(
        AWS_API_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            return body.get("response", "No response received.")
    except urllib.error.HTTPError as e:
        return f"Backend error {e.code}."
    except Exception as e:
        return f"Connection error: {e}"

def main():
    banner()

    if not AWS_API_URL:
        print(f"{C.YELLOW}⚠️  JARVIS_API_URL not set.{C.RESET}\n")

    log("⏳ LOADING", "Whisper medium model...", C.YELLOW)
    model = whisper.load_model(WHISPER_MODEL)
    log("✅ WHISPER", "Loaded.", C.GREEN)

    speak("JARVIS online. Say JARVIS to activate.")
    print(f"\n{C.DIM}Listening for wake word...{C.RESET}\n")

    pa = pyaudio.PyAudio()

    try:
        while True:
            clip_path = record_clip(pa, WAKE_CLIP_SECONDS)
            result = model.transcribe(clip_path, language="en", fp16=False,
                                      condition_on_previous_text=False)
            os.unlink(clip_path)
            heard = result["text"].strip()

            if heard:
                log("👂 HEARD", heard, C.DIM)

            if not contains_wake_word(heard):
                continue

            print(f"\n{C.CYAN}{'─'*50}{C.RESET}")
            log("⚡ ACTIVATED", f"Wake word detected: '{heard}'", C.CYAN)
            speak("Yes?")

            audio_path = record_command(pa)

            log("🔍 TRANSCRIBING", "Running Whisper...", C.YELLOW)
            result = model.transcribe(audio_path, language="en", fp16=False)
            command = result["text"].strip()
            os.unlink(audio_path)

            if not command or len(command) < 3:
                speak("I didn't catch that. Say JARVIS to try again.")
            else:
                log("🗣️  YOU SAID", command, C.GREEN)
                log("🌐 QUERYING", "Sending to JARVIS backend...", C.YELLOW)
                response = query_jarvis(command)
                log("🤖 JARVIS", response, C.CYAN)
                speak(response)

            print(f"{C.CYAN}{'─'*50}{C.RESET}\n")
            print(f"{C.DIM}Listening for wake word...{C.RESET}\n")

    except KeyboardInterrupt:
        print(f"\n{C.DIM}JARVIS offline.{C.RESET}")
        speak("JARVIS offline. Goodbye.")
    finally:
        pa.terminate()

if __name__ == "__main__":
    main()