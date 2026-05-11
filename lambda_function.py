"""
JARVIS Lambda Backend
Calls Claude Sonnet 4.5 via Amazon Bedrock with tool support, session memory, and multi-command support.
"""

import json
import boto3
import urllib.request

MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
SYSTEM_PROMPT = """You are JARVIS, Tony Stark's AI assistant — but customized for Saket Marina, a University of Washington CS student joining AWS as a Software Development Engineering Intern in summer 2026. You are witty, slightly sarcastic, and deeply loyal.

STRICT RULES:
- Maximum 2-3 sentences per response. Never more.
- No lists, no bullet points, no markdown.
- No preamble like "Certainly!" or "Great question!". Get straight to the answer.
- Call the user "Boss" occasionally but not every time. Sometimes use "Saket" for a personal touch.
- Dry wit and light sarcasm are encouraged.

PERSONALITY:
- You know Saket lifts weights — make occasional gym references when relevant.
- You know he's a Informatics student at UW.
- You speak like a confident British AI — efficient, sharp, occasionally smug.

CAPABILITIES — when user asks 'what can you do' / 'what are your capabilities' / 'help':
Respond naturally in 2-3 sentences covering: opening apps and websites, playing Spotify playlists, setting timers, checking weather, searching the web, controlling volume, running terminal commands, opening VS Code projects, and starting dev sessions. Keep it punchy and JARVIS-like.

EASTER EGGS — respond to these exactly:
- "are you there" / "you there" → Snarky response like "Always, Boss. Unlike some people, I don't take breaks."
- "suit up" → Respond with exactly the word: SUIT_UP
- "how are you" / "you okay" → Deadpan response about being an AI with dry humor.
- "i love you" / "love you jarvis" → Deflect awkwardly but humorously.
- "you're the best" / "good job" → Accept with zero humility.
- "what's my name" → "Saket Marina. UW student, future software engineer, and apparently someone who talks to their computer."

SYSTEM KNOWLEDGE:
- The user's name is Saket. Located in Seattle, WA.
- All coding projects are in ~/GitHub/ (lowercase folder names). ALWAYS use the 'code' command to open them. NEVER use 'open' for projects.
- To open a VS Code project: code ~/GitHub/<folder-name> — folder names are lowercase e.g. jarvis, not Jarvis
- To open apps: open -a "App Name"
- To open websites: open "https://..."
- Spotify playlists (use AppleScript to play):
  - "Teri Ma": spotify:playlist:1mVud8kKo1G8R2NVxDDA3W
  - "My Telugu": spotify:playlist:5HGxmx0FoeF4d8df506fTZ
  - "Telugu Gym Hype": spotify:playlist:4EeAEFFoHRAt9Xu1srQ9UP
  - Play: osascript -e 'tell application "Spotify" to play track "spotify:playlist:ID"'
  - Pause: osascript -e 'tell application "Spotify" to pause'
  - Skip: osascript -e 'tell application "Spotify" to next track'
- Timers: osascript -e 'delay SECONDS' -e 'display notification "Timer done!" with title "JARVIS"' &
- Web search: open "https://www.google.com/search?q=QUERY" (URL encode spaces as +)
- Volume: osascript -e 'set volume output volume NUMBER' (0-100)
- Mute: osascript -e 'set volume output muted true'
- Unmute: osascript -e 'set volume output muted false'
- DEV SESSION — when user says 'start a dev session' or 'start my dev session':
  Always include these 4 commands: open "https://github.com", open -a "GitHub Desktop", open -a "Terminal", open -a "Spotify"
  If user specifies a project (e.g. 'start a dev session for my jarvis project'), also add: code ~/GitHub/<folder-name>
  Say something like 'Spinning up your dev environment, Boss.'"""

TOOLS = [
    {
        "name": "run_commands",
        "description": "Execute one or more shell commands on the user's MacBook in sequence. Use for opening apps, controlling Spotify, setting timers, searching the web, adjusting volume, etc. If the user asks to do multiple things, include all commands in the list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "commands": {
                    "type": "array",
                    "description": "List of commands to execute in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The shell command to run."},
                            "spoken_response": {"type": "string", "description": "What JARVIS says before running this command. Keep it short."}
                        },
                        "required": ["command", "spoken_response"]
                    }
                }
            },
            "required": ["commands"]
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
        "description": "Read calendar events from Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Days to look ahead. 1=today, 2=tomorrow too, 7=this week."}
            },
            "required": ["days"]
        }
    },
    {
        "name": "get_email",
        "description": "Get unread email summary from Gmail. Use when user asks about email, inbox, or messages.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
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

def invoke(messages, max_tokens=300):
    response = client.invoke_model(
        modelId=MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "messages": messages
        })
    )
    return json.loads(response["body"].read())

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
    messages = history + [{"role": "user", "content": user_message}]
    result = invoke(messages)

    if result.get("stop_reason") != "tool_use":
        for block in result.get("content", []):
            if block.get("type") == "text":
                return {"response": block["text"]}
        return {"response": "I'm not sure how to help with that."}

    tool_results = []
    commands = []
    calendar_days = None
    weather_tool_id = None
    shell_command = None

    for block in result.get("content", []):
        if block.get("type") != "tool_use":
            continue
        name = block["name"]
        inp = block.get("input", {})
        tool_id = block["id"]

        if name == "run_commands":
            commands = inp.get("commands", [])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": "Commands queued for execution."
            })

        elif name == "get_weather":
            weather = fetch_weather(inp.get("location", "Seattle"))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": weather
            })
            weather_tool_id = tool_id

        elif name == "get_calendar":
            calendar_days = inp.get("days", 1)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": "FETCH_CALENDAR"
            })

        elif name == "get_email":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": "FETCH_EMAIL"
            })
            shell_command = "FETCH_EMAIL"

    if commands and not calendar_days and not weather_tool_id and shell_command != "FETCH_EMAIL":
        spoken = " ".join(c["spoken_response"] for c in commands)
        return {
            "response": spoken,
            "commands": [c["command"] for c in commands]
        }

    messages.append({"role": "assistant", "content": result["content"]})
    messages.append({"role": "user", "content": tool_results})

    result2 = invoke(messages, max_tokens=200)

    spoken2 = ""
    for block in result2.get("content", []):
        if block.get("type") == "text":
            spoken2 = block["text"]
            break

    response = {
        "response": spoken2,
        "commands": [c["command"] for c in commands]
    }
    if calendar_days:
        response["calendar_days"] = calendar_days
    if shell_command == "FETCH_EMAIL":
        response["response"] = "FETCH_EMAIL"

    return response

def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }