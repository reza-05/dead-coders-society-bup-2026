
import { useState } from "react";
import "./index.css";

const BASELINE_HOURS = [
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
];

function App() {
  const [notes, setNotes] = useState(
    "Solar output will drop to about 20% from 1 PM to 3 PM.\nDo not charge the battery between 2 PM and 4 PM.\nThe cafeteria menu changes tomorrow."
  );
  const [status, setStatus] = useState("Ready");
  const [optimized, setOptimized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({
    solar: "--",
    battery: "--",
    grid: "--",
    cost: "--"
  });
  const [plan, setPlan] = useState([]);
  const [directives, setDirectives] = useState([]);

  const handleOptimize = async () => {
    setLoading(true);
    setStatus("Interpreting notes via Groq LLM & optimizing schedule...");

    const parsedNotes = notes
      .split("\n")
      .map((n) => n.trim())
      .filter((n) => n.length > 0);

    const payload = {
      scenario_id: "DASHBOARD-LIVE",
      operator_notes: parsedNotes.length > 0 ? parsedNotes.slice(0, 3) : ["The cafeteria menu changes tomorrow."],
      hours: BASELINE_HOURS,
      battery: {
        capacity_kwh: 500,
        initial_energy_kwh: 200,
        minimum_energy_kwh: 50,
        max_charge_kwh_per_hour: 100,
        max_discharge_kwh_per_hour: 100
      }
    };

    try {
      const res = await fetch("http://localhost:8000/optimize-energy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const data = await res.json();
      const totalSolar = data.hourly_plan.reduce((sum, h) => sum + h.solar_used_kwh, 0);

      setStats({
        solar: totalSolar.toFixed(1),
        battery: data.hourly_plan[23].battery_energy_after_kwh.toFixed(1),
        grid: data.total_grid_kwh.toFixed(1),
        cost: data.total_cost_bdt.toFixed(2)
      });

      setPlan(data.hourly_plan);
      setDirectives(data.directive_interpretation || []);
      setStatus(data.plan_summary || "Optimization complete!");
      setOptimized(true);
    } catch (err) {
      console.error(err);
      setStatus(`Error: Make sure backend is running on localhost:8000 (${err.message})`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">⚡</div>
          <div>
            <h2>GridWise</h2>
            <p>Energy Intelligence</p>
          </div>
        </div>

        <nav className="nav-links">
          <a className="active" href="#overview">Overview</a>
          <a href="#schedule">Energy Schedule</a>
          <a href="#directives">Directives</a>
          <a href="#settings">Settings</a>
        </nav>

        <div className="sidebar-bottom">
          <span className="status-dot"></span>
          System Online
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">ENERGY MANAGEMENT PLATFORM</p>
            <h1>Good evening, Operator.</h1>
            <p className="subtitle">
              Monitor your energy and optimize tomorrow's schedule.
            </p>
          </div>

          <div className="topbar-right">
            <span className="live-badge">
              <span className="status-dot"></span>
              Live Demo
            </span>
            <div className="avatar">OP</div>
          </div>
        </header>

        <section className="dashboard-grid" id="overview">
          <div className="stat-card">
            <div className="stat-header">
              <span>Solar Used</span>
              <span className="stat-icon">☀</span>
            </div>
            <h2>{stats.solar} <small>kWh</small></h2>
            <p className="stat-label">24h Clean Solar Generation</p>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span>Battery EOD State</span>
              <span className="stat-icon">▣</span>
            </div>
            <h2>{stats.battery} <small>kWh</small></h2>
            <p className="stat-label">Battery Neutrality ($E_{23} = E_0$)</p>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span>Grid Purchased</span>
              <span className="stat-icon">↯</span>
            </div>
            <h2>{stats.grid} <small>kWh</small></h2>
            <p className="stat-label">Total Grid Import</p>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span>Optimized Cost</span>
              <span className="stat-icon">৳</span>
            </div>
            <h2>{stats.cost} <small>BDT</small></h2>
            <p className="stat-label">Global Minimum Cost</p>
          </div>
        </section>

        <section className="content-grid">
          <div className="panel schedule-panel" id="schedule">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">OPTIMIZATION ENGINE</p>
                <h2>24-Hour Energy Schedule</h2>
              </div>
              <span className="panel-tag">SciPy HiGHS LP</span>
            </div>

            <div className="chart-placeholder">
              <div className="chart-label">HOURLY DISPATCH SAMPLE (00:00 - 20:00)</div>

              <div className="chart-bars">
                {(plan.length > 0 ? plan.filter(p => [0, 4, 8, 12, 16, 20].includes(p.hour)) : [
                  { hour: 0, solar_used_kwh: 0, grid_kwh: 180 },
                  { hour: 4, solar_used_kwh: 0, grid_kwh: 180 },
                  { hour: 8, solar_used_kwh: 60, grid_kwh: 190 },
                  { hour: 12, solar_used_kwh: 240, grid_kwh: 60 },
                  { hour: 16, solar_used_kwh: 60, grid_kwh: 180 },
                  { hour: 20, solar_used_kwh: 0, grid_kwh: 260 }
                ]).map((item) => (
                  <div className="bar-group" key={item.hour}>
                    <div className="bar-track">
                      <div
                        className="bar solar-bar"
                        style={{ height: `${Math.min(100, item.solar_used_kwh / 2.5)}%` }}
                        title={`Solar: ${item.solar_used_kwh} kWh`}
                      ></div>
                      <div
                        className="bar demand-bar"
                        style={{ height: `${Math.min(100, item.grid_kwh / 2.5)}%` }}
                        title={`Grid: ${item.grid_kwh} kWh`}
                      ></div>
                    </div>
                    <span>{`${String(item.hour).padStart(2, '0')}:00`}</span>
                  </div>
                ))}
              </div>

              <div className="chart-legend">
                <span>
                  <i className="legend-solar"></i>
                  Solar Used
                </span>
                <span>
                  <i className="legend-demand"></i>
                  Grid Purchased
                </span>
              </div>
            </div>

            <div className="schedule-note">
              <span>ⓘ</span>
              <p>{status}</p>
            </div>
          </div>

          <div className="panel directive-panel" id="directives">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">OPERATOR INPUT (LLM-ASSISTED)</p>
                <h2>Operator Directives</h2>
              </div>
            </div>

            <label htmlFor="notes">
              Enter 1-3 natural language notes (one per line):
            </label>

            <textarea
              id="notes"
              rows={4}
              placeholder="e.g. Solar output will drop to about 20% from 1 PM to 3 PM."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            ></textarea>

            <div className="input-hint">
              Parsed via Groq LLaMA 3.3 70B with deterministic Python guardrails.
            </div>

            <button className="optimize-btn" onClick={handleOptimize} disabled={loading}>
              <span>✦</span>
              {loading ? "Optimizing..." : "Optimize Schedule"}
            </button>

            {directives.length > 0 && (
              <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <p style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "#8b949e" }}>
                  Extracted Directives:
                </p>
                {directives.map((d) => (
                  <div key={d.note_index} style={{
                    padding: "0.5rem 0.75rem",
                    borderRadius: "6px",
                    background: d.applies ? "rgba(46, 160, 67, 0.15)" : "rgba(110, 118, 129, 0.15)",
                    border: `1px solid ${d.applies ? "rgba(46, 160, 67, 0.4)" : "rgba(110, 118, 129, 0.3)"}`,
                    fontSize: "0.8rem"
                  }}>
                    <strong>Note {d.note_index}:</strong> <code>{d.directive_type}</code> {d.applies ? "✓ applies" : "✗ no_op"}
                    <div style={{ fontSize: "0.75rem", color: "#8b949e", marginTop: "2px" }}>{d.explanation}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="panel table-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">SCHEDULE BREAKDOWN</p>
              <h2>24-Hour Hourly Energy Plan</h2>
            </div>
            <span className="panel-tag">{plan.length > 0 ? "LIVE OPTIMIZED" : "DEFAULT VIEW"}</span>
          </div>

          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Hour</th>
                  <th>Demand (kWh)</th>
                  <th>Solar Used (kWh)</th>
                  <th>Battery Action</th>
                  <th>Battery Energy (kWh)</th>
                  <th>Grid Purchased (kWh)</th>
                </tr>
              </thead>
              <tbody>
                {(plan.length > 0 ? plan : BASELINE_HOURS.map(b => ({
                  hour: b.hour,
                  demand_kwh: b.demand_kwh,
                  solar_used_kwh: b.solar_kwh,
                  battery_action: "idle",
                  battery_energy_after_kwh: 200,
                  grid_kwh: Math.max(0, b.demand_kwh - b.solar_kwh)
                }))).map((item) => (
                  <tr key={item.hour}>
                    <td><strong>{String(item.hour).padStart(2, "0")}:00</strong></td>
                    <td>{BASELINE_HOURS[item.hour].demand_kwh}</td>
                    <td style={{ color: "#e3b341" }}>{item.solar_used_kwh}</td>
                    <td>
                      <span style={{
                        padding: "2px 8px",
                        borderRadius: "12px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        background: item.battery_action === "charge" ? "rgba(56, 139, 253, 0.15)" : item.battery_action === "discharge" ? "rgba(240, 136, 62, 0.15)" : "rgba(110, 118, 129, 0.15)",
                        color: item.battery_action === "charge" ? "#58a6ff" : item.battery_action === "discharge" ? "#f0883e" : "#8b949e"
                      }}>
                        {item.battery_action} {item.battery_kwh > 0 ? `(${item.battery_kwh} kWh)` : ""}
                      </span>
                    </td>
                    <td>{item.battery_energy_after_kwh}</td>
                    <td style={{ color: "#f85149", fontWeight: 600 }}>{item.grid_kwh}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className="footer">
          <span>GridWise LLM • Team Dead Coders Society</span>
          <span>BUP CSE FEST 2026 Hackathon</span>
        </footer>
      </main>
    </div>
  );
}

export default App;