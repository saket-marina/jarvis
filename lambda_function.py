"""
JARVIS Lambda Backend
Calls Claude Sonnet 4.5 via Amazon Bedrock with tool support and session memory.
"""

import json
import boto3
import urllib.request

MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
SYSTEM_PROMPT = """You are JARVIS, Tony Stark's AI assistant running on a MacBook. You are a voice assistant — responses must be short and spoken naturally.

STRICT RULES:
- Maximum 2-3 sentences per response. Never more.
- No lists, no bullet points, no markdown.
- No preamble like "Certainly!" or "Great question!". Get straight to the answer.
- Occasionally call the user "Boss" but not every time.
- Dry wit is welcome but keep it brief.

You have access to tools to execute shell commands, fetch weather, and read the calendar. Always tell the user what you're doing in plain speech.

SYSTEM KNOWLEDGE:
- The user's name is Saket. Located in Seattle, WA.
- All coding projects are in ~/GitHub/. Use the 'code' command to open them in VS Code.
- To open a project: code ~/GitHub/<folder-name>
- To open apps: open -a "App Name"
- To open websites: open "https://..."
- Spotify playlists (use AppleScript to play):
  - "Teri Ma": spotify:playlist:1mVud8kKo1G8R2NVxDDA3W
  - "My Telugu": spotify:playlist:5HGxmx0FoeF4d8df506fTZ
  - "Telugu Gym Hype": spotify:playlist:4EeAEFFoHRAt9Xu1srQ9UP
  - Play command: osascript -e 'tell application "Spotify" to play track "spotify:playlist:ID"'
  - Pause: osascript -e 'tell application "Spotify" to pause'
  - Skip: osascript -e 'tell application "Spotify" to next track'
- Timers: osascript -e 'delay SECONDS' -e 'display notification "Timer done!" with title "JARVIS"' &
- Web search: open "https://www.google.com/search?q=QUERY" (URL encode spaces as +)
- Volume control: osascript -e 'set volume output volume NUMBER' (0-100). "turn it up" = +20, "turn it down" = -20, use get volume settings to check current first if needed.
- Do Not Disturb on: osascript -e 'tell application "System Events" to tell process "Control Center" to click menu bar item "Focus"'
- Mute: osascript -e 'set volume output muted true'
- Unmute: osascript -e 'set volume output muted false'"""

TOOLS = [
    {
        "name": "run_command",
        "description": "Execute a shell command on the user's MacBook. Use for opening apps, controlling Spotify, setting timers, searching the web, adjusting volume, Do Not Disturb, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run"},
                "spoken_response": {"type": "string", "description": "What JARVIS says out loud. Short and natural."}
            },
            "required": ["command", "spoken_response"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name e.g. 'Seattle'"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_calendar",
        "description": "Read calendar events from macOS Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Days to look ahead. 1=today, 2=tomorrow too, 7=this week."}
            },
            "required": ["days"]
        }
    }
]

client = boto3.client("bedrock-runtime", region_name="us-east-1")

def fetch_weather(location: str) -> str:
    try:
        url = f"https://wttr.in/{location.replace(' ', '+')}?format=3"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.64.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode().strip()
    except Exception as e:
        return f"Weather unavailable: {e}"

def lambda_handler(event, context):
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)
    except Exception:
        body = event

    user_message = body.get("message", "").strip()
    history = body.get("history", [])
    if not user_message:
        return _response(400, {"error": "No message provided"})

    try:
        result = call_claude(user_message, history)
        return _response(200, result)
    except Exception as e:
        return _response(500, {"error": str(e)})

def call_claude(user_message: str, history: list) -> dict:
    # Build messages with history
    messages = history + [{"role": "user", "content": user_message}]

    response = client.invoke_model(
        modelId=MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "messages": messages
        })
    )
    result = json.loads(response["body"].read())

    if result.get("stop_reason") == "tool_use":
        tool_results = []
        shell_command = None
        spoken = None

        for block in result.get("content", []):
            if block.get("type") != "tool_use":
                continue
            name = block["name"]
            inp = block.get("input", {})
            tool_id = block["id"]

            if name == "run_command":
                shell_command = inp.get("command", "")
                spoken = inp.get("spoken_response", "Done.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": "Command queued."
                })

            elif name == "get_weather":
                weather = fetch_weather(inp.get("location", "Seattle"))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": weather
                })

            elif name == "get_calendar":
                days = inp.get("days", 1)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": "FETCH_CALENDAR"
                })
                shell_command = f"FETCH_CALENDAR:{days}"

        if shell_command and not shell_command.startswith("FETCH_CALENDAR") and spoken:
            return {"response": spoken, "command": shell_command}

        # Second call for weather/calendar
        messages.append({"role": "assistant", "content": result["content"]})
        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_results[0]["tool_use_id"], "content": tool_results[0]["content"]}]})

        response2 = client.invoke_model(
            modelId=MODEL,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 150,
                "system": SYSTEM_PROMPT,
                "tools": TOOLS,
                "messages": messages
            })
        )
        result2 = json.loads(response2["body"].read())

        if shell_command and shell_command.startswith("FETCH_CALENDAR"):
            for block in result2.get("content", []):
                if block.get("type") == "text":
                    return {"response": block["text"], "command": shell_command}

        for block in result2.get("content", []):
            if block.get("type") == "text":
                return {"response": block["text"]}

    for block in result.get("content", []):
        if block.get("type") == "text":
            return {"response": block["text"]}

    return {"response": "I'm not sure how to help with that."}

def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }