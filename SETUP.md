# JARVIS Setup Guide

## Architecture

```
"Jarvis" (mic)
      ↓
  jarvis.py  (Mac)
  ├── Wake word → Whisper small (local, sliding window)
  ├── Command  → Whisper small (local)
  └── Response → macOS `say` Daniel voice
      ↓
AWS API Gateway → Lambda → Amazon Bedrock (Claude Sonnet 4.5)
```

---

## Part 1: Mac App Setup

### 1. Install system dependencies

```bash
brew install portaudio ffmpeg
```

### 2. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/jarvis.git
cd jarvis
```

### 3. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python packages

```bash
pip install -r requirements.txt
```

### 5. Download openWakeWord models

```bash
python3 -c "from openwakeword.utils import download_models; download_models()"
```

### 6. Set your API URL permanently

```bash
echo 'export JARVIS_API_URL=https://YOUR_ID.execute-api.us-east-1.amazonaws.com/jarvis' >> ~/.zshrc
source ~/.zshrc
```

### 7. Grant microphone access

Run the script once — macOS will prompt for mic permission. Grant it.

---

## Part 2: AWS Backend (Free Tier)

### 1. Create the Lambda function

1. Go to [AWS Lambda Console](https://console.aws.amazon.com/lambda)
2. Click **Create function**
3. Settings:
   - Name: `jarvis-backend`
   - Runtime: `Python 3.11`
4. Click **Create function**
5. Paste contents of `lambda_function.py` into the code editor
6. Click **Deploy**

### 2. Set timeout

Configuration → General configuration → Edit → Timeout: **30 seconds**

### 3. Give Lambda Bedrock access

Configuration → Permissions → click the role name → Add permissions → Attach policies → `AmazonBedrockFullAccess`

### 4. Create API Gateway

1. Go to [API Gateway Console](https://console.aws.amazon.com/apigateway)
2. Create API → **HTTP API** → Build
3. Add integration: Lambda → `jarvis-backend`
4. Route: `POST /jarvis`
5. Stage: `prod` → Create
6. Copy the **Invoke URL** and add `/jarvis` to the end

### Free Tier Limits
- Lambda: 1M requests/month free
- API Gateway: 1M calls/month free (first 12 months)
- Bedrock: pay per token (~$0.003/query with Claude Sonnet 4.5)

---

## Part 3: Run JARVIS

```bash
cd jarvis
source venv/bin/activate
python3 jarvis.py
```

JARVIS will greet you with the time and weather, then listen for the wake word.

---

## Wake Word

Say **"Jarvis"** clearly. JARVIS uses a sliding window so you only need to say it once. Common mishearings that also trigger it: Jervis, Javis, Davis, Travis.

---

## Capabilities

| Command | Example |
|---------|---------|
| Open apps | "Open Safari" |
| Open projects | "Open my jarvis project in VS Code" |
| Spotify | "Play Telugu Gym Hype" / "Pause" / "Skip" |
| Weather | "What's the weather?" |
| Timers | "Set a timer for 10 minutes" |
| Web search | "Search for AWS Lambda pricing" |
| Volume | "Turn it up" / "Set volume to 50" |
| Easter eggs | "Suit up" / "Are you there?" |

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
        <string>https://your-url.execute-api.us-east-1.amazonaws.com/jarvis</string>
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
| Mic not working | System Settings → Privacy → Microphone → allow Terminal |
| Wake word not detected | Speak clearly; check `SILENCE_THRESHOLD` in `jarvis.py` |
| Lambda timeout | Increase timeout to 30s in Lambda config |
| Whisper slow | Change `WHISPER_MODEL` to `"tiny"` in `jarvis.py` |
| "Thank you" phantom triggers | Already filtered — add new ones to `WHISPER_HALLUCINATIONS` in `jarvis.py` |