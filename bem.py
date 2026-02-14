"""
BEM AI - Image to Text Workflow Caller
Reads a local image file, encodes it to Base64, calls the BEM API,
and saves the extracted text output to a file.
"""

import requests
import base64
import json
import sys
import os
from pathlib import Path


# ── Configuration ──────────────────────────────────────────────────────────────
API_KEY               = "BEM_API_KEY"
WORKFLOW_NAME         = "New-Workflow-nucp2nm"   # Replace with your workflow name
TRANSFORMATION_REF_ID = "TRANSFORMATION_REFERENCE_ID"  # Replace with your reference ID
INPUT_TYPE            = "TRANSFORMATION_INPUT_TYPE"     # e.g. "IMAGE", "PDF", etc.

BEM_API_URL = "https://api.bem.ai/v2/calls"
OUTPUT_FILE = "bem_output.txt"   # Where the extracted text will be saved
# ──────────────────────────────────────────────────────────────────────────────


def encode_image_to_base64(image_path: str) -> str:
    """Read a local image file and return its Base64-encoded string."""
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {image_path}")

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    print(f"✔ Encoded '{path.name}' ({path.stat().st_size:,} bytes) to Base64.")
    return encoded


def call_bem_workflow(image_path: str) -> dict:
    """
    Encode the image and send it to the BEM API.
    Returns the parsed JSON response.
    """
    base64_content = encode_image_to_base64(image_path)

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": API_KEY,
    }

    payload = {
        "calls": [
            {
                "callReferenceID": TRANSFORMATION_REF_ID,
                "workflowName": WORKFLOW_NAME,
                "input": {
                    "singleFile": {
                        "inputType": INPUT_TYPE,
                        "inputContent": base64_content,
                    }
                },
            }
        ]
    }

    print(f"⏳ Calling BEM API at {BEM_API_URL} …")

    try:
        response = requests.post(BEM_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"✖ HTTP error: {e}")
        print(f"  Response body: {response.text}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("✖ Connection error — check your network and the API URL.")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("✖ Request timed out (60 s). The BEM API may be busy.")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"✖ Unexpected request error: {e}")
        sys.exit(1)

    print(f"✔ API responded with status {response.status_code}.")
    return response.json()


def extract_text_from_response(response_data: dict) -> str:
    """
    Pull the text content out of the BEM response.
    Adjust the key path below to match your workflow's actual response shape.
    """
    try:
        # Common BEM response path — update if your workflow differs:
        calls = response_data.get("calls") or response_data.get("results") or []
        if calls:
            first_call = calls[0]
            # Try several common output field names
            for key in ("outputText", "text", "output", "content", "result"):
                text = first_call.get(key)
                if text:
                    return str(text)

        # Fallback: return the full JSON so nothing is lost
        print("⚠ Could not find a text field in the response. Saving full JSON instead.")
        return json.dumps(response_data, indent=2)

    except (KeyError, IndexError, TypeError) as e:
        print(f"⚠ Error parsing response ({e}). Saving full JSON instead.")
        return json.dumps(response_data, indent=2)


def save_output(text: str, output_path: str) -> None:
    """Write the extracted text to a file."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"✔ Output saved to '{output_path}'.")


def main():
    # Accept image path from CLI or prompt the user
    if len(sys.argv) >= 2:
        image_path = sys.argv[1]
    else:
        image_path = input("Enter the path to your image file: ").strip()

    if not image_path:
        print("✖ No image path provided. Exiting.")
        sys.exit(1)

    print(f"\n── BEM Image → Text Workflow ──────────────────────")
    print(f"   Image : {image_path}")
    print(f"   Output: {OUTPUT_FILE}")
    print(f"───────────────────────────────────────────────────\n")

    # 1. Call the BEM API
    response_data = call_bem_workflow(image_path)

    # 2. Extract text from the response
    extracted_text = extract_text_from_response(response_data)

    # 3. Save to output file
    save_output(extracted_text, OUTPUT_FILE)

    print("\n✅ Done!\n")


if __name__ == "__main__":
    main()