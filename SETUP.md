# JARVIS Setup Guide

## Architecture

```
"Yo Jarvis" (mic)
      ↓
  jarvis.py  (Mac)
  ├── Wake word → Google STT (free)
  ├── Command  → Whisper (local, free)
  └── Response → macOS `say` (free)
      ↓
AWS API Gateway → Lambda → Anthropic Claude
```

---

## Part 1: Mac App Setup

### 1. Install system dependencies

```bash
brew install portaudio ffmpeg
```

### 2. Create a virtual environment

```bash
cd jarvis/
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python packages

```bash
pip install -r requirements.txt
```

> Whisper will download the `base` model (~140MB) on first run.

### 4. Grant microphone access

Run the script once — macOS will prompt for mic permission. Grant it.

---

## Part 2: AWS Backend (Free Tier)

### 1. Create the Lambda function

1. Go to [AWS Lambda Console](https://console.aws.amazon.com/lambda)
2. Click **Create function**
3. Settings:
   - Name: `jarvis-backend`
   - Runtime: `Python 3.11`
   - Architecture: `x86_64`
4. Click **Create function**
5. In the **Code** tab, paste the contents of `lambda_function.py`
6. Click **Deploy**

### 2. Set environment variables

In Lambda → Configuration → Environment variables:

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` (your Anthropic key) |

### 3. Increase timeout

Configuration → General configuration → Edit → Timeout: **30 seconds**

### 4. Create API Gateway

1. Go to [API Gateway Console](https://console.aws.amazon.com/apigateway)
2. Click **Create API** → **HTTP API** → **Build**
3. Add integration: **Lambda** → select `jarvis-backend`
4. Route: `POST /jarvis`
5. Stage: `prod`
6. Click **Create**
7. Copy the **Invoke URL** — it looks like:
   `https://abc123.execute-api.us-east-1.amazonaws.com/prod/jarvis`

### Free Tier Limits (more than enough)
- Lambda: 1M requests/month free
- API Gateway: 1M calls/month free (first 12 months)
- You only pay for Anthropic API usage (~$0.001/query with Haiku)

---

## Part 3: Connect & Run

### 1. Set your API URL

```bash
export JARVIS_API_URL=https://abc123.execute-api.us-east-1.amazonaws.com/prod/jarvis
```

To make it permanent, add that line to `~/.zshrc` and run `source ~/.zshrc`.

### 2. Run JARVIS

```bash
source venv/bin/activate
python jarvis.py
```

### 3. Usage

- Say **"Yo Jarvis"** to wake it up
- JARVIS will say "Yes?" 
- Speak your command
- Pause for ~1.5 seconds → it processes and responds

---

## Optional: Auto-start on Login

Create `~/Library/LaunchAgents/com.jarvis.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jarvis</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/jarvis/venv/bin/python</string>
        <string>/path/to/jarvis/jarvis.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>JARVIS_API_URL</key>
        <string>https://your-url.execute-api.us-east-1.amazonaws.com/prod/jarvis</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Then run:
```bash
launchctl load ~/Library/LaunchAgents/com.jarvis.plist
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `PyAudio` install fails | `brew install portaudio` first |
| Mic not working | System Preferences → Privacy → Microphone → allow Terminal |
| Wake word not detected | Speak clearly; adjust `SILENCE_THRESHOLD` in `jarvis.py` |
| Lambda timeout | Increase timeout to 30s in Lambda config |
| Whisper slow | Change model to `"tiny"` in `jarvis.py` for faster (less accurate) transcription |
