import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("MINIMAX_API_KEY")
GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
BASE_URL = f"https://api.minimax.io/v1/text/chatcompletion_v2?GroupId={GROUP_ID}"
MODEL = "MiniMax-M2"


def _headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def chat(messages, temperature=0.3, max_tokens=2048):
    """Simple chat completion — no tools."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(BASE_URL, headers=_headers(), json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # Minimax response format: choices[0].message.content
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Minimax response: {json.dumps(data, indent=2)}")


def chat_with_tools(messages, tools, temperature=0.1, max_tokens=2048):
    """Chat completion with tool definitions. Returns (content, tool_calls).

    tool_calls is a list of dicts: [{"name": "...", "arguments": {...}}]
    If the model doesn't call a tool, tool_calls is an empty list.
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(BASE_URL, headers=_headers(), json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Minimax response: {json.dumps(data, indent=2)}")

    content = message.get("content", "")
    tool_calls = []

    # Check for tool_calls in the standard OpenAI-compatible format
    if "tool_calls" in message and message["tool_calls"]:
        for tc in message["tool_calls"]:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": args,
            })
        return content, tool_calls

    # Fallback: parse XML-style tool calls from content
    # <minimax:tool_call><invoke name="fn"><parameter name="k">v</parameter></invoke></minimax:tool_call>
    xml_pattern = r'<minimax:tool_call>(.*?)</minimax:tool_call>'
    xml_matches = re.findall(xml_pattern, content, re.DOTALL)
    for match in xml_matches:
        name_match = re.search(r'<invoke\s+name="([^"]+)"', match)
        if not name_match:
            continue
        fn_name = name_match.group(1)
        params = {}
        for pm in re.finditer(r'<parameter\s+name="([^"]+)">(.*?)</parameter>', match, re.DOTALL):
            key = pm.group(1)
            val = pm.group(2).strip()
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass
            params[key] = val
        tool_calls.append({
            "id": "",
            "name": fn_name,
            "arguments": params,
        })

    return content, tool_calls
