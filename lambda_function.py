"""
JARVIS Lambda Backend
Deploy this to AWS Lambda (Python 3.11)
Calls Claude Sonnet 4.5 via Amazon Bedrock.
"""

import json
import boto3

MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
SYSTEM_PROMPT = """You are JARVIS (Just A Rather Very Intelligent System), the AI assistant built by Tony Stark. 
You are highly intelligent, efficient, and slightly dry in humor. You address the user as "Boss" occasionally.
Keep responses concise — you are a voice assistant, so avoid long lists or markdown formatting.
Speak in plain sentences. Be direct and helpful."""

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
        reply = call_claude(user_message)
        return _response(200, {"response": reply})
    except Exception as e:
        return _response(500, {"error": str(e)})

def call_claude(user_message: str) -> str:
    response = client.invoke_model(
        modelId=MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_message}
            ]
        })
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]

def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }