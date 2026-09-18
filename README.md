# GridWise LLM — Smart Campus Energy Optimization Service
**BUP CSE FEST 2026 Hackathon (Preliminary Round)**  
**Team:** Dead Coders Society  

---

## 1. System Architecture & Flow

The service implements a resilient four-stage pipeline: natural-language directive interpretation, deterministic guardrails, mathematical cost optimization, and contract validation.

```text
[Energy Data + Operator Notes]
             │
             ▼
   [LLM Interpreter (Groq)] ──► Extracts structured directive intents (LLaMA 3.3 70B / 3.1 8B)
             │
             ▼
    [Guardrail Validator]   ──► Sanitizes hours [0..23], clamps factors [0..1], enforces applies rules
             │
             ▼
   [Math Optimizer (HiGHS)] ──► Solves 24-hour Linear Program (LP) to minimize total BDT cost
             │
             ▼
    [Contract Validator]    ──► Ensures energy balance, battery neutrality, and schema agreement
             │
             ▼
       [API Response]
```

### Core Components
1. **LLM Interpreter (`app/llm_interpreter.py`)**: Uses Groq's high-speed inference engine (`llama-3.3-70b-versatile` with automatic fallback to `llama-3.1-8b-instant`) to decode complex, paraphrased natural-language operator directives into structured JSON adjustments.
2. **Deterministic Guardrails (`app/guardrails.py`)**: Sanitizes time windows to ascending unique whole-hour integers (`0..23`), ensures non-negative numbers, clamps solar factors to `[0.0, 1.0]`, and ensures `applies = false` and `structured_adjustment = null` exclusively for `no_op`. Safely recovers from malformed inputs without crashing.
3. **Linear Program Optimizer (`app/optimizer.py`)**: Uses `scipy.optimize.linprog(method='highs')` to globally minimize grid electricity purchase cost subject to:
   - Hourly energy balance: $\text{grid} + \text{solar\_used} + \text{discharge} = \text{demand} + \text{charge}$
   - Battery bounds: $\text{effective\_min\_reserve}[h] \le E_h \le \text{capacity}$
   - Charge/Discharge limits and directive windows
   - End-of-day battery neutrality: $E_{23} = E_{\text{initial}}$
4. **FastAPI Web Service (`app/main.py`)**: High-performance asynchronous HTTP API strictly matching the BUP CSE Fest specification.

---

## 2. API Contract

### `GET /health`
* **Purpose:** Judging harness readiness check.
* **Response (HTTP 200):**
```json
{
  "status": "ok"
}
```

### `POST /optimize-energy`
* **Purpose:** 24-hour energy scenario optimization with operator directives.
* **Request:** JSON containing `scenario_id`, `operator_notes` (1-3 strings), `hours` (24 objects), and `battery` configuration.
* **Response (HTTP 200):** JSON containing `scenario_id`, `directive_interpretation`, `hourly_plan`, `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh`, and `plan_summary`.

---

## 3. Environment Variables

Create a `.env` file from `.env.example`:

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GROQ_API_KEY` | **Yes** | - | Groq API Key for operator note interpretation |
| `GROQ_PRIMARY_MODEL` | No | `llama-3.3-70b-versatile` | Primary language model |
| `GROQ_FALLBACK_MODEL` | No | `llama-3.1-8b-instant` | Fast fallback model for high reliability |
| `GROQ_TIMEOUT_SECONDS` | No | `4.0` | Timeout threshold per LLM request |
| `GOOGLE_API_KEY` | No | - | Optional secondary fallback model (Gemini 2.0 Flash) |
| `HOST` | No | `0.0.0.0` | API service bind host |
| `PORT` | No | `8000` | API service port |

> ⚠️ **Secret Safety:** Never commit your actual API keys or `.env` file to version control. The repository includes `.gitignore` to prevent secret leakage.

---

## 4. Local Quickstart (Clean Environment)

### Step 1: Clone the repository
```bash
git clone https://github.com/reza-05/dead-coders-society-bup-2026.git
cd dead-coders-society-bup-2026
```

### Step 2: Create virtual environment and install dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure Environment
```bash
cp .env.example .env
# Edit .env and insert your GROQ_API_KEY
```

### Step 4: Run the API Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 5. Testing & Verification

### Run Automated Unit Tests
```bash
pytest -v tests/test_solution.py
```

### Health Check Verification
```bash
curl -i -X GET http://127.0.0.1:8000/health
```
**Expected Output:**
```json
HTTP/1.1 200 OK
{"status":"ok"}
```

### Optimization Sample Verification
```bash
curl -i -X POST http://127.0.0.1:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "GRID-101",
    "operator_notes": [
      "Solar output will drop to about 20% from 1 PM to 3 PM.",
      "Do not charge the battery between 2 PM and 4 PM.",
      "The cafeteria menu changes tomorrow."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 1, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 2, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 3, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 4, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 5, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 6, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
      {"hour": 7, "demand_kwh": 220, "solar_kwh": 20, "tariff_bdt_per_kwh": 8},
      {"hour": 8, "demand_kwh": 250, "solar_kwh": 60, "tariff_bdt_per_kwh": 8},
      {"hour": 9, "demand_kwh": 280, "solar_kwh": 120, "tariff_bdt_per_kwh": 9},
      {"hour": 10, "demand_kwh": 300, "solar_kwh": 180, "tariff_bdt_per_kwh": 9},
      {"hour": 11, "demand_kwh": 300, "solar_kwh": 220, "tariff_bdt_per_kwh": 9},
      {"hour": 12, "demand_kwh": 300, "solar_kwh": 240, "tariff_bdt_per_kwh": 9},
      {"hour": 13, "demand_kwh": 300, "solar_kwh": 220, "tariff_bdt_per_kwh": 9},
      {"hour": 14, "demand_kwh": 280, "solar_kwh": 180, "tariff_bdt_per_kwh": 9},
      {"hour": 15, "demand_kwh": 260, "solar_kwh": 120, "tariff_bdt_per_kwh": 9},
      {"hour": 16, "demand_kwh": 240, "solar_kwh": 60, "tariff_bdt_per_kwh": 8},
      {"hour": 17, "demand_kwh": 250, "solar_kwh": 20, "tariff_bdt_per_kwh": 12},
      {"hour": 18, "demand_kwh": 270, "solar_kwh": 0, "tariff_bdt_per_kwh": 14},
      {"hour": 19, "demand_kwh": 270, "solar_kwh": 0, "tariff_bdt_per_kwh": 14},
      {"hour": 20, "demand_kwh": 260, "solar_kwh": 0, "tariff_bdt_per_kwh": 14},
      {"hour": 21, "demand_kwh": 240, "solar_kwh": 0, "tariff_bdt_per_kwh": 12},
      {"hour": 22, "demand_kwh": 200, "solar_kwh": 0, "tariff_bdt_per_kwh": 9},
      {"hour": 23, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}
    ],
    "battery": {
      "capacity_kwh": 500,
      "initial_energy_kwh": 200,
      "minimum_energy_kwh": 50,
      "max_charge_kwh_per_hour": 100,
      "max_discharge_kwh_per_hour": 100
    }
  }'
```

---

## 6. Docker Fallback Image Instructions

A standalone container image is provided for instant reproducibility without requiring Python setup.

### Option A: Build and Run Locally
```bash
docker build -t dead-coders-society-gridwise:v1 .
docker run -d --name gridwise-service -p 8000:8000 -e GROQ_API_KEY=your_groq_key dead-coders-society-gridwise:v1
```

### Option B: Pull Pre-built Image
```bash
# Pull from registry
docker pull reza05/dead-coders-society-gridwise:v1

# Run container
docker run -d --name gridwise-service -p 8000:8000 -e GROQ_API_KEY=your_groq_key reza05/dead-coders-society-gridwise:v1
```

Verify the container is responding:
```bash
curl http://localhost:8000/health
```

---

## 7. Known Limitations & Edge Cases Handled
- **Paraphrase Resilience**: Recognizes diverse human expressions (e.g. "one-fifth", "80% reduction", "drop to 20%") using Groq's high-parameter reasoning models.
- **Strict Guardrails**: Ensures sorting and unique bounds on `hours`, preventing out-of-order execution.
- **Safe Failure & Fallback**: If an external LLM call encounters network issues or rate limits, the service falls back sequentially to backup models, then deterministic rule-based extractions, ensuring zero 500 unhandled crashes.
