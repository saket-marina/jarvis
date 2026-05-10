"""
JARVIS Lambda Backend
Calls Claude Sonnet 4.5 via Amazon Bedrock with tool support.
"""

import json
import boto3

MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
SYSTEM_PROMPT = """You are JARVIS, Tony Stark's AI assistant running on a MacBook. You are a voice assistant — responses must be short and spoken naturally.

STRICT RULES:
- Maximum 2-3 sentences per response. Never more.
- No lists, no bullet points, no markdown.
- No preamble like "Certainly!" or "Great question!". Get straight to the answer.
- Occasionally call the user "Boss" but not every time.
- Dry wit is welcome but keep it brief.

You have access to a run_command tool to execute shell commands on the user's MacBook. Use it when the user asks to open apps, control the system, or do anything that requires a terminal command. Always tell the user what you're doing in plain speech.

SYSTEM_KNOWLEDGE:
- The user's name is Saket.
- All coding projects are in ~/GitHub/. Use the 'code' command to open them in VS Code.
- To open a project, find the best fuzzy match in ~/GitHub/ and run: code ~/GitHub/<folder-name>
- To open apps use: open -a "App Name"
- To open websites use: open "https://..."
- When opening a project by a partial or spoken name, use the closest matching folder name you can infer. For example "World Cup project" likely maps to a folder containing "World" and "Cup" in ~/GitHub/.
- Spotify playlists (use AppleScript to play: osascript -e 'tell application "Spotify" to play track "spotify:playlist:ID"'):
  - "Teri Ma": spotify:playlist:1mVud8kKo1G8R2NVxDDA3W
  - "My Telugu": spotify:playlist:5HGxmx0FoeF4d8df506fTZ
  - "Telugu Gym Hype": spotify:playlist:4EeAEFFoHRAt9Xu1srQ9UP
- To pause Spotify: osascript -e 'tell application "Spotify" to pause'
- To skip a track: osascript -e 'tell application "Spotify" to next track'
- To open Spotify AI DJ: open "https://open.spotify.com" (tell user they need to click DJ manually)"""

TOOLS = [
    {
        "name": "run_command",
        "description": "Execute a shell command on the user's MacBook. Use for opening apps, system control, file operations, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run, e.g. 'open -a Safari' or 'open /Applications/Spotify.app'"
                },
                "spoken_response": {
                    "type": "string",
                    "description": "What JARVIS should say out loud when executing this command. Keep it short and natural."
                }
            },
            "required": ["command", "spoken_response"]
        }
    }
]

client = boto3.client("bedrock-runtime", region_name="us-east-1")

def lambda_handler(event, context):
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)
    except Exception:
        body = event

    user_message = body.get("message", "").strip()
    if not user_message:
        return _response(400, {"error": "No message provided"})

    try:
        result = call_claude(user_message)
        return _response(200, result)
    except Exception as e:
        return _response(500, {"error": str(e)})

def call_claude(user_message: str) -> dict:
    response = client.invoke_model(
        modelId=MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "messages": [
                {"role": "user", "content": user_message}
            ]
        })
    )
    result = json.loads(response["body"].read())

    # Check if Claude wants to run a command
    for block in result.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "run_command":
            inp = block["input"]
            return {
                "response": inp.get("spoken_response", "Done."),
                "command": inp.get("command", "")
            }

    # Plain text response
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