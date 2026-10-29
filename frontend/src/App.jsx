import { useCallback, useEffect, useMemo, useState } from "react";

const INITIAL_DATE = "2026-01-15";
const INITIAL_CUTOFF = "11:00";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function formatDate(value) {
  if (!value) return "Choose a delivery day";
  return new Date(`${value}T12:00:00`).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatClock(value) {
  if (!value) return "No eligible snapshot";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
    timeZoneName: "short",
  });
}

function MetricCard({ label, value, unit, detail, accent = false }) {
  return (
    <article className={`metric-card${accent ? " metric-card-accent" : ""}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value}
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

function Chart({ rows }) {
  const width = 920;
  const height = 280;
  const padding = { top: 16, right: 20, bottom: 34, left: 58 };
  const values = rows.flatMap((row) =>
    [row.forecast_mw, row.actual_mw].filter(
      (value) => value !== null && Number.isFinite(value),
    ),
  );
  if (values.length === 0) {
    return <div className="chart-empty">No aligned forecast and actual data to plot.</div>;
  }

  const low = Math.min(0, ...values);
  const high = Math.max(...values);
  const range = high - low || 1;
  const x = (index) =>
    padding.left +
    (index * (width - padding.left - padding.right)) / Math.max(rows.length - 1, 1);
  const y = (value) =>
    padding.top +
    ((high - value) / range) * (height - padding.top - padding.bottom);
  const lineFor = (key) => {
    let path = "";
    let penDown = false;
    rows.forEach((row, index) => {
      const value = row[key];
      if (value === null || !Number.isFinite(value)) {
        penDown = false;
        return;
      }
      path += `${penDown ? "L" : "M"} ${x(index)} ${y(value)} `;
      penDown = true;
    });
    return path;
  };
  const ticks = Array.from({ length: 5 }, (_, index) => high - (range * index) / 4);

  return (
    <svg
      className="chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Hourly wind forecast compared with actual generation"
    >
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={y(tick)}
            y2={y(tick)}
            className="chart-grid"
          />
          <text x={padding.left - 10} y={y(tick) + 4} textAnchor="end" className="chart-axis">
            {formatNumber(tick)}
          </text>
        </g>
      ))}
      {[0, 6, 12, 18, 23].map((index) => (
        <text
          key={index}
          x={x(index)}
          y={height - 8}
          textAnchor="middle"
          className="chart-axis"
        >
          {String(index).padStart(2, "0")}:00
        </text>
      ))}
      <path d={lineFor("forecast_mw")} className="chart-forecast" />
      <path d={lineFor("actual_mw")} className="chart-actual" />
    </svg>
  );
}

function App() {
  const [deliveryDate, setDeliveryDate] = useState(INITIAL_DATE);
  const [cutoffTime, setCutoffTime] = useState(INITIAL_CUTOFF);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadAnalysis = useCallback(async () => {
    if (!deliveryDate || !cutoffTime) {
      setAnalysis(null);
      setError("Choose a delivery day and decision cutoff.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        delivery_date: deliveryDate,
        cutoff_time: cutoffTime,
      });
      const response = await fetch(`${API_BASE_URL}/api/analysis?${params}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Request failed (${response.status}).`);
      }
      setAnalysis(payload);
    } catch (requestError) {
      setAnalysis(null);
      setError(requestError.message || "Unable to load Elexon data.");
    } finally {
      setLoading(false);
    }
  }, [deliveryDate, cutoffTime]);

  useEffect(() => {
    loadAnalysis();
  }, [loadAnalysis]);

  const summary = useMemo(() => {
    if (!analysis) return null;
    const metrics = analysis.metrics;
    const completeForecast = analysis.forecast_intervals === 24;
    const completeActuals = analysis.actual_intervals === 24;
    return {
      metrics,
      coverageLabel: `${metrics.matched_intervals} of 24 hourly intervals`,
      statusLabel:
        completeForecast && completeActuals
          ? "Full-day comparison"
          : "Partial-day comparison",
    };
  }, [analysis]);

  const bias = summary?.metrics.bias_mw;
  const biasDetail =
    bias === null || bias === undefined
      ? "No matched intervals"
      : bias > 0
        ? "Forecast was higher than actual"
        : bias < 0
          ? "Forecast was lower than actual"
          : "Forecast matched actual on average";

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Wind Market Desk home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-name">wind<span>desk</span></span>
        </a>
        <div className="topbar-right">
          <span className="pilot-pill"><span /> PILOT WORKSPACE</span>
          <div className="profile-mark" aria-label="Market operations">MO</div>
        </div>
      </header>

      <main className="page-content">
        <section className="page-heading">
          <div>
            <div className="eyebrow">MARKET OPERATIONS <span>/</span> RENEWABLES</div>
            <h1>Wind forecast desk</h1>
            <p className="page-description">
              One view of the latest day-ahead wind outlook — and how it performed.
            </p>
          </div>
          <div className="scope-tag"><span className="status-dot" /> GB national · Elexon BMRS</div>
        </section>

        <section className="control-panel" aria-label="Analysis controls">
          <div className="control-date">
            <label htmlFor="delivery-date">DELIVERY DAY</label>
            <input
              id="delivery-date"
              type="date"
              min="2026-01-01"
              max="2026-01-31"
              value={deliveryDate}
              onChange={(event) => setDeliveryDate(event.target.value)}
            />
          </div>
          <div className="control-divider" />
          <div className="control-date control-cutoff">
            <label htmlFor="cutoff-time">DECISION CUTOFF · UK TIME</label>
            <input
              id="cutoff-time"
              type="time"
              value={cutoffTime}
              onChange={(event) => setCutoffTime(event.target.value)}
            />
          </div>
          <div className="control-spacer" />
          <button className="refresh-button" onClick={loadAnalysis} disabled={loading}>
            <span className={loading ? "refresh-icon spin" : "refresh-icon"} aria-hidden="true">↻</span>
            {loading ? "Loading" : "Refresh"}
          </button>
        </section>

        <section className="decision-strip">
          <div className="decision-icon" aria-hidden="true">↗</div>
          <div className="decision-copy">
            <strong>Day-ahead view for {formatDate(deliveryDate)}</strong>
            <span>
              Forecast snapshot published by {cutoffTime} UK time on the previous day.
              Generation values shown in MW.
            </span>
          </div>
          <div className="decision-cutoff">
            <span>SNAPSHOT SELECTED</span>
            <strong>{analysis ? formatClock(analysis.latest_publish_time) : "—"}</strong>
          </div>
        </section>

        {error && (
          <div className="alert alert-error" role="alert">
            <strong>Could not load the analysis.</strong>
            <span>{error}</span>
          </div>
        )}

        {loading && !analysis && (
          <div className="loading-panel" role="status">Loading Elexon forecast and actual generation…</div>
        )}

        {analysis && summary && (
          <>
            <section className="metrics-grid" aria-label="Forecast accuracy metrics">
              <MetricCard
                label="MEAN ABSOLUTE ERROR"
                value={formatNumber(summary.metrics.mae_mw)}
                unit="MW"
                detail={`Average absolute miss · ${summary.coverageLabel}`}
                accent
              />
              <MetricCard
                label="WEIGHTED ABSOLUTE ERROR"
                value={formatNumber(summary.metrics.wape_percent, 1)}
                unit="%"
                detail="Absolute error ÷ total actual generation"
              />
              <MetricCard
                label="FORECAST BIAS"
                value={formatNumber(summary.metrics.bias_mw, 0)}
                unit="MW"
                detail={biasDetail}
              />
              <MetricCard
                label="ROOT MEAN SQUARED ERROR"
                value={formatNumber(summary.metrics.rmse_mw)}
                unit="MW"
                detail={`Larger misses carry more weight`}
              />
            </section>

            {analysis.forecast_intervals === 0 && (
              <div className="alert alert-warning" role="status">
                <strong>No forecast snapshot found before this cutoff.</strong>
                <span>
                  Elexon returned no WINDFOR values for {deliveryDate} published by{" "}
                  {cutoffTime} UK time on the preceding day. Try a later decision cutoff.
                </span>
              </div>
            )}
            {analysis.forecast_intervals > 0 && analysis.forecast_intervals < 24 && (
              <div className="alert alert-warning" role="status">
                <strong>Partial forecast snapshot.</strong>
                <span>
                  {analysis.forecast_intervals} of 24 hourly forecast values are available;
                  metrics use matched actual/forecast intervals only.
                </span>
              </div>
            )}
            {analysis.actual_intervals < 24 && (
              <div className="alert alert-warning" role="status">
                <strong>Actual generation coverage is incomplete.</strong>
                <span>
                  Actual values are available for {analysis.actual_intervals} of 24 hourly intervals.
                </span>
              </div>
            )}
            {analysis.actual_source_intervals < 48 && (
              <div className="alert alert-warning" role="status">
                <strong>Half-hourly actual records are incomplete.</strong>
                <span>
                  Elexon returned {analysis.actual_source_intervals} of 48 expected FUELHH intervals.
                  Hourly actuals are averaged from the available records.
                </span>
              </div>
            )}

            <section className="chart-panel">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">FORECAST PERFORMANCE</div>
                  <h2>Wind generation · hourly profile</h2>
                  <p>{formatDate(deliveryDate)} <span>·</span> MW</p>
                </div>
                <div className="chart-legend">
                  <span><i className="legend-line forecast-line" /> Day-ahead forecast</span>
                  <span><i className="legend-line actual-line" /> Actual generation</span>
                </div>
              </div>
              <Chart rows={analysis.series} />
              <div className="chart-note">
                Elexon FUELHH actuals are averaged from half-hourly to hourly to align with WINDFOR forecast resolution.
              </div>
            </section>

            <section className="table-panel">
              <div className="panel-heading table-heading">
                <div>
                  <div className="eyebrow">INTERVAL DETAIL</div>
                  <h2>{summary.statusLabel}</h2>
                </div>
                <span className="coverage-chip">{summary.coverageLabel}</span>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>START (UK)</th>
                      <th>FORECAST</th>
                      <th>ACTUAL</th>
                      <th>ERROR · F − A</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.series.map((row) => {
                      const forecast = row.forecast_mw;
                      const actual = row.actual_mw;
                      const errorValue =
                        forecast !== null && actual !== null ? forecast - actual : null;
                      return (
                        <tr key={row.start_time}>
                          <td>
                            {new Date(row.start_time).toLocaleTimeString("en-GB", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "Europe/London",
                            })}
                          </td>
                          <td>{forecast === null ? "—" : `${formatNumber(forecast)} MW`}</td>
                          <td>{actual === null ? "—" : `${formatNumber(actual)} MW`}</td>
                          <td className={errorValue === null ? "" : errorValue > 0 ? "error-positive" : "error-negative"}>
                            {errorValue === null ? "—" : `${errorValue > 0 ? "+" : ""}${formatNumber(errorValue)} MW`}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}

        <section className="method-note">
          <div className="method-icon" aria-hidden="true">i</div>
          <div>
            <strong>How to read this view</strong>
            <p>
              Bias is forecast minus actual (positive means over-forecast). MAE, RMSE and WAPE
              use intervals with both values. This pilot covers wind generation only; demand,
              other generation, prices and a net procurement requirement are not included.
            </p>
          </div>
        </section>
      </main>

      <footer className="footer">
        <span>WINDDESK <i>·</i> January 2026 pilot</span>
        <span className="source-links">
          Data:{" "}
          <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream" target="_blank" rel="noreferrer">Elexon WINDFOR</a>
          {" · "}
          <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream" target="_blank" rel="noreferrer">FUELHH</a>
        </span>
      </footer>
    </div>
  );
}

export default App;
