"""One-shot Anthropic API smoke test. Prints the response or the full error."""

import os
import sys

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

key = os.environ.get("ANTHROPIC_API_KEY")
if not key:
    sys.exit("ANTHROPIC_API_KEY not set (check .env)")

print(f"Using key: {key[:14]}…{key[-4:]} (len={len(key)})")

client = anthropic.Anthropic()

try:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=32,
        messages=[{"role": "user", "content": "Say 'pong' and nothing else."}],
    )
    print("OK")
    print("  content:", msg.content[0].text if msg.content else "<empty>")
    print("  usage  :", msg.usage)
except anthropic.APIStatusError as e:
    print(f"FAIL: {e.status_code}")
    print(f"  body: {e.response.text}")
    print(f"  req_id: {e.response.headers.get('request-id')}")
