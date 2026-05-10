"""
JARVIS Lambda Backend
Deploy this to AWS Lambda (Python 3.11)
Calls Anthropic Claude API and returns the response.
"""

import json
import os
import urllib.request
import urllib.error

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-haiku-4-5-20251001"  # cheapest/fastest Claude model
SYSTEM_PROMPT = """You are JARVIS (Just A Rather Very Intelligent System), the AI assistant built by Tony Stark. 
You are highly intelligent, efficient, and slightly dry in humor. You address the user as "Boss" occasionally.
Keep responses concise — you are a voice assistant, so avoid long lists or markdown formatting.
Speak in plain sentences. Be direct and helpful."""

def lambda_handler(event, context):
    # Parse body (API Gateway sends it as a string)
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

    # Call Anthropic
    try:
        reply = call_claude(user_message)
        return _response(200, {"response": reply})
    except Exception as e:
        return _response(500, {"error": str(e)})

def call_claude(user_message: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 512,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_message}
        ]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
        return data["content"][0]["text"]

def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }
