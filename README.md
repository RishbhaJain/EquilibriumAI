# EquilibriumAI

EquilibriumAI is a supply-chain carbon analysis project for Owala's FreeSip product line.
It combines source documents, a consolidated emissions dataset, and a Python API that supports:

- Data access for dashboards
- Natural-language Q&A over emissions data
- Agentic what-if simulation of decarbonization scenarios

## Repository Structure

- `owala-carbon-footprint-dashboard.json`: Consolidated carbon/emissions dataset used by the API.
- `owala-supply-chain-docs/`: Source documents (invoices, BOLs, shipping/fleet reports, routing data, etc.).
- `app.py`: Flask API with `/data`, `/chat`, and `/simulate` endpoints.
- `minimax_client.py`: Minimax client wrapper for chat and tool-calling.
- `simulator.py`: Deterministic emissions recalculation engine used by the simulation endpoint.
- `bem.py`: Utility script to call a BEM workflow for image-to-text extraction.
- `ui/`: Frontend folder placeholder.

## How It Works

1. Base emissions data is loaded from `owala-carbon-footprint-dashboard.json`.
2. `/chat` sends user questions plus full dataset context to Minimax for grounded responses.
3. `/simulate` uses tool-calling to pick scenario overrides and runs `recalculate_emissions(...)` in `simulator.py`.
4. The API returns original vs simulated totals, stage-level diffs, and a narrative summary.

## Prerequisites

- Python 3.10+
- Minimax API credentials

Install dependencies:

```bash
pip install flask flask-cors requests python-dotenv
```

## Environment Variables

Create a `.env` file in the repo root:

```env
MINIMAX_API_KEY=your_api_key_here
MINIMAX_GROUP_ID=your_group_id_here
```

## Run the API

```bash
python app.py
```

Server starts at `http://localhost:5001`.

## API Endpoints

### `GET /data`
Returns the raw carbon dataset JSON.

### `POST /chat`
Ask questions about the supply-chain emissions dataset.

Example:

```bash
curl -X POST http://localhost:5001/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the largest emissions stage?"}'
```

### `POST /simulate`
Runs an agentic what-if scenario with parameter overrides selected via tool-calling.

Example:

```bash
curl -X POST http://localhost:5001/simulate \
  -H "Content-Type: application/json" \
  -d '{"scenario":"What if we shift 50% of drayage trips to EV and source 30% renewable electricity at warehousing?"}'
```

## Simulation Override Model

`simulator.py` supports overrides across these areas:

- Raw materials (steel/resin/silicone factors)
- Manufacturing grid factor and renewable share
- Ocean freight speed mode
- Port drayage EV share
- Warehousing renewable share and efficiency gains
- DC-to-retail LTL→FTL shift

The engine computes stage totals, per-unit emissions, and before/after deltas.

## BEM Utility (`bem.py`)

`bem.py` is a standalone helper that:

1. Reads a local image
2. Encodes it to Base64
3. Calls a BEM workflow
4. Saves extracted text output

Run:

```bash
python bem.py /path/to/image.png
```

Before use, update API/workflow constants in `bem.py` (`API_KEY`, workflow name, and transformation settings).

## Notes

- Current repository includes backend logic and data; `ui/` is present but empty.
- Keep secrets in `.env` only. Do not commit real credentials.
