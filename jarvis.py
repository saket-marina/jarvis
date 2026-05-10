#!/usr/bin/env python3
"""
JARVIS - Voice Assistant
Wake word: "Yo Jarvis"
"""

import os
import sys
import time
import json
import wave
import struct
import tempfile
import threading
import subprocess
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
AWS_API_URL = os.environ.get("JARVIS_API_URL", "")  # Set this after deploying AWS
WAKE_WORD = "yo jarvis"
SILENCE_THRESHOLD = 500       # Adjust if mic is too/not sensitive
SILENCE_DURATION = 1.5        # Seconds of silence before stopping recording
MAX_RECORD_SECONDS = 30
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024

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
    """macOS TTS via 'say' command."""
    # Strip markdown-style formatting for cleaner speech
    clean = text.replace("**", "").replace("*", "").replace("`", "").replace("#", "")
    subprocess.run(["say", "-v", "Alex", "-r", "200", clean], check=False)

def log(label: str, msg: str, color=C.CYAN):
    ts = time.strftime("%H:%M:%S")
    print(f"{C.DIM}[{ts}]{C.RESET} {color}{C.BOLD}{label}{C.RESET}  {msg}")

# ── Wake Word Detection (using macOS speech recognition via SpeechRecognition) ─
def check_dependencies():
    missing = []
    try:
        import speech_recognition  # noqa
    except ImportError:
        missing.append("SpeechRecognition")
    try:
        import pyaudio  # noqa
    except ImportError:
        missing.append("pyaudio")
    try:
        import openai_whisper  # noqa
    except ImportError:
        try:
            import whisper  # noqa
        except ImportError:
            missing.append("openai-whisper")

    if missing:
        print(f"{C.RED}Missing packages: {', '.join(missing)}{C.RESET}")
        print(f"Run: {C.YELLOW}pip install {' '.join(missing)}{C.RESET}")
        sys.exit(1)

def record_until_silence(recognizer, source) -> bytes:
    """Record audio chunks until silence is detected."""
    import speech_recognition as sr

    log("🎙️  LISTENING", "Speak your command...", C.GREEN)
    frames = []
    silent_chunks = 0
    silent_limit = int(SILENCE_DURATION * SAMPLE_RATE / CHUNK)

    while True:
        audio_chunk = recognizer.record(source, duration=CHUNK / SAMPLE_RATE)
        raw = audio_chunk.get_raw_data()
        frames.append(raw)

        # Detect silence
        rms = _rms(raw)
        if rms < SILENCE_THRESHOLD:
            silent_chunks += 1
        else:
            silent_chunks = 0

        total_duration = len(frames) * (CHUNK / SAMPLE_RATE)
        if silent_chunks >= silent_limit or total_duration >= MAX_RECORD_SECONDS:
            break

    # Build WAV in memory
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
        with wave.open(f, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
    return tmp_path

def _rms(raw: bytes) -> float:
    count = len(raw) // 2
    if count == 0:
        return 0
    shorts = struct.unpack(f"{count}h", raw[:count * 2])
    return (sum(s * s for s in shorts) / count) ** 0.5

def transcribe_whisper(audio_path: str) -> str:
    try:
        import whisper
    except ImportError:
        import openai_whisper as whisper

    log("🔍 TRANSCRIBING", "Running Whisper...", C.YELLOW)
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, language="en", fp16=False)
    return result["text"].strip()

def query_jarvis(user_text: str) -> str:
    """Send query to AWS Lambda backend."""
    if not AWS_API_URL:
        return "API URL not configured. Please set the JARVIS_API_URL environment variable."

    payload = json.dumps({"message": user_text}).encode()
    req = urllib.request.Request(
        AWS_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            return body.get("response", "No response received.")
    except urllib.error.HTTPError as e:
        return f"Backend error: {e.code}"
    except Exception as e:
        return f"Connection error: {e}"

def listen_for_wake_word(recognizer, source) -> bool:
    """Listen for wake word using Google STT (fast, free for short clips)."""
    import speech_recognition as sr

    try:
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
        text = recognizer.recognize_google(audio).lower()
        log("👂 HEARD", text, C.DIM)
        return WAKE_WORD in text
    except sr.WaitTimeoutError:
        return False
    except sr.UnknownValueError:
        return False
    except sr.RequestError:
        # Offline fallback: just return False and keep waiting
        return False

def main():
    check_dependencies()
    import speech_recognition as sr

    banner()

    if not AWS_API_URL:
        print(f"{C.YELLOW}⚠️  JARVIS_API_URL not set. Set it after deploying AWS:{C.RESET}")
        print(f"   export JARVIS_API_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/jarvis\n")

    speak("JARVIS online. Say 'Yo JARVIS' to activate.")
    log("✅ READY", f"Listening for wake word: '{WAKE_WORD.upper()}'", C.GREEN)

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = SILENCE_THRESHOLD
    recognizer.dynamic_energy_threshold = True

    with sr.Microphone(sample_rate=SAMPLE_RATE) as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print(f"{C.DIM}  Ambient noise calibrated.{C.RESET}\n")

        while True:
            try:
                # Phase 1: Wake word
                if not listen_for_wake_word(recognizer, source):
                    continue

                # Acknowledged
                print(f"\n{C.CYAN}{'─'*50}{C.RESET}")
                log("⚡ ACTIVATED", "JARVIS is listening...", C.CYAN)
                speak("Yes?")

                # Phase 2: Record command
                audio_path = record_until_silence(recognizer, source)

                # Phase 3: Transcribe
                command = transcribe_whisper(audio_path)
                os.unlink(audio_path)

                if not command or len(command) < 3:
                    speak("I didn't catch that. Say 'Yo JARVIS' again to activate.")
                    continue

                log("🗣️  YOU SAID", command, C.GREEN)

                # Phase 4: Query backend
                log("🌐 QUERYING", "Sending to JARVIS backend...", C.YELLOW)
                response = query_jarvis(command)

                log("🤖 JARVIS", response, C.CYAN)
                speak(response)
                print(f"{C.CYAN}{'─'*50}{C.RESET}\n")

            except KeyboardInterrupt:
                print(f"\n{C.DIM}JARVIS offline.{C.RESET}")
                speak("JARVIS offline. Goodbye.")
                sys.exit(0)
            except Exception as e:
                log("❌ ERROR", str(e), C.RED)
                time.sleep(1)

if __name__ == "__main__":
    main()
