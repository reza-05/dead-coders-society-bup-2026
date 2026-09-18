
import { useState } from "react";
import "./index.css";

const hourlyData = [
  { hour: "00:00", solar: 12, demand: 38, grid: 26 },
  { hour: "04:00", solar: 8, demand: 32, grid: 24 },
  { hour: "08:00", solar: 65, demand: 55, grid: 0 },
  { hour: "12:00", solar: 92, demand: 68, grid: 0 },
  { hour: "16:00", solar: 54, demand: 72, grid: 18 },
  { hour: "20:00", solar: 10, demand: 64, grid: 54 },
];

function App() {
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("Ready");
  const [optimized, setOptimized] = useState(false);

  const handleOptimize = () => {
    setStatus("Demo optimization complete");
    setOptimized(true);
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
              <span>Solar Production</span>
              <span className="stat-icon">☀</span>
            </div>
            <h2>-- <small>kWh</small></h2>
            <p className="stat-label">Awaiting scenario data</p>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span>Battery Level</span>
              <span className="stat-icon">▣</span>
            </div>
            <h2>-- <small>kWh</small></h2>
            <p className="stat-label">Awaiting scenario data</p>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span>Grid Consumption</span>
              <span className="stat-icon">↯</span>
            </div>
            <h2>-- <small>kWh</small></h2>
            <p className="stat-label">Awaiting scenario data</p>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span>Estimated Cost</span>
              <span className="stat-icon">$</span>
            </div>
            <h2>-- <small>USD</small></h2>
            <p className="stat-label">Awaiting scenario data</p>
          </div>
        </section>

        <section className="content-grid">
          <div className="panel schedule-panel" id="schedule">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">OPTIMIZATION</p>
                <h2>Energy Schedule</h2>
              </div>
              <span className="panel-tag">24 HOURS</span>
            </div>

            <div className="chart-placeholder">
              <div className="chart-label">ENERGY FLOW</div>

              <div className="chart-bars">
                {hourlyData.map((item) => (
                  <div className="bar-group" key={item.hour}>
                    <div className="bar-track">
                      <div
                        className="bar solar-bar"
                        style={{ height: `${item.solar}%` }}
                      ></div>
                      <div
                        className="bar demand-bar"
                        style={{ height: `${item.demand}%` }}
                      ></div>
                    </div>
                    <span>{item.hour}</span>
                  </div>
                ))}
              </div>

              <div className="chart-legend">
                <span>
                  <i className="legend-solar"></i>
                  Solar
                </span>
                <span>
                  <i className="legend-demand"></i>
                  Demand
                </span>
              </div>
            </div>

            <div className="schedule-note">
              <span>ⓘ</span>
              <p>
                Sample visualization. Live schedule data will be connected
                to the optimization API.
              </p>
            </div>
          </div>

          <div className="panel directive-panel" id="directives">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">OPERATOR INPUT</p>
                <h2>Optimization Directives</h2>
              </div>
            </div>

            <label htmlFor="notes">
              Enter your energy instructions
            </label>

            <textarea
              id="notes"
              placeholder="e.g. Do not charge the battery between 2 PM and 4 PM."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            ></textarea>

            <div className="input-hint">
              Natural language instructions will be interpreted by the LLM.
            </div>

            <button className="optimize-btn" onClick={handleOptimize}>
              <span>✦</span>
              Optimize Schedule
            </button>

            <div className={`result-status ${optimized ? "success" : ""}`}>
              <span className="status-dot"></span>
              {status}
            </div>
          </div>
        </section>

        <section className="panel table-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">SCHEDULE BREAKDOWN</p>
              <h2>Hourly Energy Plan</h2>
            </div>
            <span className="panel-tag">SAMPLE DATA</span>
          </div>

          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Hour</th>
                  <th>Solar (kWh)</th>
                  <th>Demand (kWh)</th>
                  <th>Grid (kWh)</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {hourlyData.map((item) => (
                  <tr key={item.hour}>
                    <td>{item.hour}</td>
                    <td>{item.solar}</td>
                    <td>{item.demand}</td>
                    <td>{item.grid}</td>
                    <td>
                      <span className="table-status">Sample</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className="footer">
          <span>GridWise LLM</span>
          <span>Energy Intelligence Platform • Prototype</span>
        </footer>
      </main>
    </div>
  );
}

export default App;