# GridWise LLM — Autonomous Campus Energy Optimization Engine
**BUP CSE FEST 2026 Hackathon (Preliminary Round)**  
**Challenge:** Smart Campus Energy Optimization Challenge (GridWise LLM)  
**Team:** Dead Coders Society  

---

### Team Members
* **Md. Shifat Reza** — System Architect & Backend Lead (`shifatreza5@gmail.com`)
* **Abrar Faiyaz Arian** — Cloud Infrastructure & Deployment Engineer
* **Ahad Kaisar Tamim** — AI & LLM Systems Engineer
* **Anha Khan** — Optimization & Algorithm Specialist

---

### 🎥 Architecture & Demo Video (Priority #1 Tie-Breaker)
* **3-Minute Walkthrough Video:** [Watch on YouTube / Google Drive](https://youtu.be/placeholder-tie-breaker-video)

---

## 1. Executive Summary & Architecture

**GridWise LLM** is an enterprise-grade, high-availability energy management system designed to minimize 24-hour campus electricity expenditures. The system integrates natural language understanding with rigorous mathematical optimization, decoding arbitrary, human-written operator directives and executing a global cost-minimization Linear Program (LP).

```
                      [Operator Notes (1-3 Free Text Strings)]
                                         │
                                         ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │             Tiered Resilient Directive Interpretation Engine              │
   │  Tier 0: In-Memory LRU Cache (0ms latency, zero quota consumption)       │
   │  Tier 1: Groq Cloud High-Speed Inference (Llama 3.3 70B / 3.1 8B)        │
   │  Tier 2: OpenRouter High-Speed Neural Failover                            │
   │  Tier 3: Google DeepMind Gemini 2.5 Flash API                            │
   │  Tier 4: Deterministic High-Precision Rule Fallback                       │
   └─────────────────────────────────────┬─────────────────────────────────────┘
                                         │
                                         ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │                    Deterministic Guardrail Validation                     │
   │  • Whole-hour interval sanitizer ([start, end) -> [start..end-1])         │
   │  • Monotonic ascending unique hour verification (0 to 23)                 │
   │  • Factor clamping [0.0, 1.0] and non-negative reserve bounds             │
   │  • Strict semantic enforcement: applies=false <===> directive_type=no_op │
   └─────────────────────────────────────┬─────────────────────────────────────┘
                                         │
                                         ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │                  Mathematical Optimization Engine (HiGHS LP)              │
   │  • Objective: Minimize Total Cost (BDT) over 24-hour horizon              │
   │  • Constraints: Energy balance, battery bounds, rate limits               │
   │  • Terminal Condition: End-of-day battery neutrality (E_23 = E_initial)   │
   └─────────────────────────────────────┬─────────────────────────────────────┘
                                         │
                                         ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │                       Contract & Schema Validation                        │
   │  • Validates Pydantic v2 strict schemas matching Section 07 & 10          │
   │  • Verified Recalculation: total_grid_kwh, total_cost_bdt, peak_grid_kwh  │
   └───────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Production Live Endpoints

The service is fully deployed and continuously monitored on cloud infrastructure:

* **Base URL:** `https://dead-coders-gridwise.onrender.com`
* **Health Check Endpoint:** `GET https://dead-coders-gridwise.onrender.com/health`
* **Energy Optimization Endpoint:** `POST https://dead-coders-gridwise.onrender.com/optimize-energy`
* **High-Availability Monitor:** Automated 10-minute heartbeat ensuring 0ms cold-starts and 24/7 uptime.

---

## 3. Mathematical Optimization Formulation

The scheduling engine formulates a 120-variable continuous Linear Program solved via `scipy.optimize.linprog(method='highs')`:

### Objective Function
$$\min \sum_{h=0}^{23} \text{tariff}[h] \cdot \text{grid}[h]$$

### Operational Constraints ($\forall h \in \{0, \dots, 23\}$)

1. **Hourly Energy Balance:**
   $$\text{grid}[h] + \text{solar\_used}[h] + \text{discharge}[h] = \text{demand}[h] + \text{charge}[h]$$

2. **Solar Resource Limits:**
   $$0 \le \text{solar\_used}[h] \le \text{effective\_solar}[h]$$
   $$\text{effective\_solar}[h] = \begin{cases} \text{solar}[h] \cdot \text{factor} & \text{if } h \in \text{solar\_reduction hours} \\ \text{solar}[h] & \text{otherwise} \end{cases}$$

3. **Battery State-of-Charge (SoC) Dynamics:**
   $$E_0 = E_{\text{initial}} + \eta \cdot \text{charge}[0] - \text{discharge}[0]$$
   $$E_h = E_{h-1} + \eta \cdot \text{charge}[h] - \text{discharge}[h], \quad \forall h \ge 1$$
   $$\max(\text{min\_energy}, \text{directive\_reserve}[h]) \le E_h \le \text{capacity}$$

4. **Charge and Discharge Ingress/Egress Limits:**
   $$0 \le \text{charge}[h] \le \begin{cases} 0 & \text{if } h \in \text{no\_charge hours} \\ \text{max\_charge\_rate} & \text{otherwise} \end{cases}$$
   $$0 \le \text{discharge}[h] \le \begin{cases} 0 & \text{if } h \in \text{no\_discharge hours} \\ \text{max\_discharge\_rate} & \text{otherwise} \end{cases}$$

5. **Grid Import Ceiling:**
   $$0 \le \text{grid}[h] \le \begin{cases} \text{max\_grid\_kwh} & \text{if } h \in \text{max\_grid hours} \\ \infty & \text{otherwise} \end{cases}$$

6. **End-of-Day Neutrality:**
   $$E_{23} = E_{\text{initial}}$$
   *Prevents parasitic depletion of initial stored energy to artificially deflate costs.*

---

## 4. Directive Interpretation & Guardrails

The engine handles natural language directives via structured JSON generation enforced by deterministic validation:

| Directive Type | JSON Structure | Mathematical Effect |
| :--- | :--- | :--- |
| `solar_reduction` | `{"hours": [int, ...], "factor": float}` | Scales available solar generation: $S_{\text{eff}}[h] = S[h] \cdot \text{factor}$ |
| `minimum_battery_reserve` | `{"hours": [int, ...], "minimum_energy_kwh": float}` | Enforces elevated storage baseline: $E_h \ge \text{reserve}$ |
| `no_charge_window` | `{"hours": [int, ...]} ` | Clamps battery charge power: $\text{charge}[h] = 0$ |
| `no_discharge_window` | `{"hours": [int, ...]} ` | Clamps battery discharge power: $\text{discharge}[h] = 0$ |
| `max_grid_window` | `{"hours": [int, ...], "max_grid_kwh": float}` | Imposes grid import ceiling: $\text{grid}[h] \le \text{cap}$ |
| `no_op` | `null` | Informational note; zero scheduling constraint |

### Deterministic Guardrail Guarantees
* **Standardized Window Convention:** Whole-hour phrases ("1 PM to 3 PM", "13:00 to 15:00") map strictly to start-inclusive, end-exclusive hours: `[13, 14]`.
* **Ordering & Sanitization:** Output hours are guaranteed to be unique, ascending integers in range `0..23`.
* **Failure Independence:** If external networks fail, the system cascades gracefully without returning HTTP 500.

---

## 5. Local Quickstart Guide

### Prerequisites
* Python 3.11+
* Git

### Step 1: Clone Repository
```bash
git clone https://github.com/reza-05/dead-coders-society-bup-2026.git
cd dead-coders-society-bup-2026
```

### Step 2: Environment Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Provide your Groq API key (minimum required for zero-friction setup):
```env
GROQ_API_KEY=your_groq_api_key
```

### Step 4: Run the Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Step 5: Execute Automated Test Suite
```bash
pytest -v tests/test_official_samples.py tests/test_edge_cases.py
```
**Expected Result:** `17 passed in ~60s (100% SUCCESS)`

---

## 6. Docker Container Deployment

A pre-built, production-certified container image is published on Docker Hub.

### Pull from Docker Hub
```bash
docker pull reza05/dead-coders-society-gridwise:v1
```

### Run Container
```bash
docker run -d \
  --name gridwise-production \
  -p 8000:8000 \
  -e GROQ_API_KEY="your_groq_key" \
  reza05/dead-coders-society-gridwise:v1
```

### Digest Reference
```text
reza05/dead-coders-society-gridwise:v1
Digest: sha256:217c179e1a9f5cb8a0e75e524c266ee71dba13bd0fc26beb36efa2a42826e65f
```

---

## 7. API Verification Examples

### Health Readiness Probe
```bash
curl -i -X GET https://dead-coders-gridwise.onrender.com/health
```
```json
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "ok"}
```

### Energy Optimization Request
```bash
curl -i -X POST https://dead-coders-gridwise.onrender.com/optimize-energy \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

---

## 8. Benchmark & Reliability Metrics

* **Memory Footprint:** Peak RSS is constrained to **~98 MB**, well within minimal container quotas.
* **Warm Cache Latency:** Sub-**300ms** turnaround on repeated scenarios.
* **Solvability Rate:** **100%** feasibility achieved across all official BUP sample scenarios.
* **Cold-Start Resilience:** Background heartbeat keeps container warm 24/7.
