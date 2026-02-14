import json
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from minimax_client import chat, chat_with_tools
from simulator import recalculate_emissions, compute_diff

app = Flask(__name__)
CORS(app)

# Load carbon data once at startup
DATA_PATH = os.path.join(os.path.dirname(__file__), "owala-carbon-footprint-dashboard.json")
with open(DATA_PATH, "r") as f:
    CARBON_DATA = json.load(f)

CARBON_JSON_STR = json.dumps(CARBON_DATA, indent=2)

SYSTEM_PROMPT = f"""You are a supply chain sustainability analyst for Owala Inc., a water bottle company.
You have access to comprehensive carbon footprint data for their FreeSip product line (Q3-Q4 2025, 90,000 units).

Here is the complete carbon footprint data:

{CARBON_JSON_STR}

When answering questions:
- Always cite specific numbers from the data (kg CO2e, percentages, supplier names)
- Be concise but precise
- If asked about recommendations, ground them in the actual data
- If a question is outside the scope of this data, say so clearly
- Use plain language, not jargon — imagine presenting to a VP of Operations"""

SIMULATE_SYSTEM_PROMPT = """You are a supply chain sustainability analyst for Owala Inc.
The user will describe a what-if scenario. You must call the recalculate_emissions tool with the appropriate parameter overrides to model the scenario.

Available override parameters (use dot notation):
- raw_materials.steel_factor: kg CO2e per kg steel (baseline: 1.83). Use ~1.2 for recycled steel, ~1.5 for low-carbon steel
- raw_materials.tritan_factor: kg CO2e per kg resin (baseline: 3.8). Use ~2.5 for bio-based alternatives
- raw_materials.silicone_factor: kg CO2e per kg silicone (baseline: 4.23)
- manufacturing.grid_factor: kg CO2e per kWh (baseline: 0.581 Zhejiang grid)
- manufacturing.renewable_pct: 0-100, % of factory electricity from on-site solar/wind (baseline: 0)
- ocean_freight.speed_mode: "slow" | "moderate" | "express" | "ultra_slow"
- ocean_freight.all_same_speed: true to apply speed_mode to ALL shipments
- port_drayage.ev_pct: 0-100, % of drayage trips using electric trucks (baseline: 14.3)
- warehousing.renewable_pct: 0-100, % of DC electricity from renewables (baseline: 0)
- warehousing.efficiency_gain_pct: 0-100, % overall energy reduction from efficiency upgrades
- distribution.ftl_shift_pct: 0-100, % of LTL shipments consolidated to FTL

Choose the overrides that best match the user's scenario. You can combine multiple overrides.
Always call the tool — never guess the numbers."""

SIMULATE_TOOL = {
    "type": "function",
    "function": {
        "name": "recalculate_emissions",
        "description": "Recalculate supply chain carbon emissions with modified parameters to model a what-if scenario.",
        "parameters": {
            "type": "object",
            "properties": {
                "overrides": {
                    "type": "object",
                    "description": "Key-value pairs of parameters to change. Use dot notation keys like 'ocean_freight.speed_mode' or 'warehousing.renewable_pct'. Values should be numbers or strings.",
                },
                "scenario_name": {
                    "type": "string",
                    "description": "Short descriptive name for this scenario, e.g. '100% EV Drayage' or 'Renewable Warehouse'",
                },
            },
            "required": ["overrides", "scenario_name"],
        },
    },
}


@app.route("/data", methods=["GET"])
def get_data():
    """Return the raw carbon footprint JSON for dashboard charts."""
    return jsonify(CARBON_DATA)


@app.route("/chat", methods=["POST"])
def chat_endpoint():
    """Simple Q&A — context-stuffed Minimax M2 call."""
    body = request.get_json()
    question = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    try:
        answer = chat(messages)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/simulate", methods=["POST"])
def simulate_endpoint():
    """What-if simulation agent — Minimax M2 + recalculate tool loop."""
    body = request.get_json()
    scenario = body.get("scenario", "").strip()
    if not scenario:
        return jsonify({"error": "No scenario provided"}), 400

    # Step 1: Ask LLM to decide which parameters to override
    messages = [
        {"role": "system", "content": SIMULATE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Model this scenario: {scenario}"},
    ]

    try:
        content, tool_calls = chat_with_tools(messages, [SIMULATE_TOOL])
    except Exception as e:
        return jsonify({"error": f"Minimax API error: {str(e)}"}), 500

    if not tool_calls:
        # LLM didn't call the tool — return its text response as a fallback
        return jsonify({
            "scenario": scenario,
            "narrative": content,
            "error": "Model did not call the recalculation tool. Try rephrasing your scenario.",
        })

    # Step 2: Execute the recalculation
    tc = tool_calls[0]
    overrides = tc["arguments"].get("overrides", {})
    scenario_name = tc["arguments"].get("scenario_name", scenario)

    simulated = recalculate_emissions(CARBON_DATA, overrides)
    diff = compute_diff(CARBON_DATA, simulated)

    # Step 3: Send results back to LLM for narrative
    tool_result = json.dumps({
        "scenario_name": scenario_name,
        "overrides_applied": overrides,
        "simulated_totals": simulated["totals"],
        "diff": diff,
    }, indent=2)

    messages.append({"role": "assistant", "content": content, "tool_calls": [
        {"id": tc.get("id", "call_1"), "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
    ]})
    messages.append({"role": "tool", "tool_call_id": tc.get("id", "call_1"), "content": tool_result})

    try:
        narrative = chat(messages, temperature=0.3)
    except Exception:
        # If the follow-up fails, still return the data
        narrative = f"Scenario '{scenario_name}' applied. Total emissions change: {diff['total']['delta_pct']}%."

    return jsonify({
        "scenario": scenario_name,
        "overrides": overrides,
        "original": {
            "total_kg_co2e": diff["total"]["original_kg"],
            "per_unit_kg": diff["per_unit"]["original_kg"],
        },
        "simulated": {
            "total_kg_co2e": diff["total"]["simulated_kg"],
            "per_unit_kg": diff["per_unit"]["simulated_kg"],
        },
        "diff": diff,
        "stage_details": simulated,
        "narrative": narrative,
    })


if __name__ == "__main__":
    print("Carbon Footprint API running on http://localhost:5001")
    print("Endpoints:")
    print("  GET  /data     — raw carbon data for charts")
    print("  POST /chat     — Q&A about the data")
    print("  POST /simulate — what-if scenario modeling")
    app.run(host="0.0.0.0", port=5001, debug=True)
