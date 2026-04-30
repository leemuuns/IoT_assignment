# ================================================================
# COM3505 – IoT Assignment
# Python Flask Server
#
# Endpoints:
#   POST /data       ← ESP32 sends sensor data (JSON)
#   GET  /command    ← ESP32 polls for pattern command
#   POST /pattern    ← Browser sends pattern change request
#   GET  /status     ← Browser AJAX: latest sensor data (JSON)
#   GET  /           ← Browser: main dashboard page
# ================================================================

from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ── Shared State ─────────────────────────────────────────────────
latest_data = {
    "button":       0,
    "press_count":  0,
    "pattern":      1,
    "timestamp":    "—"
}

# History buffer for live graph (keep last 30 readings)
history = deque(maxlen=30)

# Pattern command to send to ESP32 (set by browser)
pending_pattern = 1   # default: Blink

PATTERN_NAMES = {
    0: "Solid",
    1: "Blink",
    2: "Chase",
    3: "Rainbow",
    4: "Fire 🔥"
}

# ================================================================
# Dashboard HTML (single-file, no templates folder needed)
# ================================================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>COM3505 IoT Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    /* ── Reset & Base ── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 20px;
    }

    /* ── Header ── */
    header {
      text-align: center;
      padding: 18px 0 10px;
      border-bottom: 1px solid #1e293b;
      margin-bottom: 24px;
    }
    header h1 { font-size: 1.6rem; color: #7dd3fc; letter-spacing: 1px; }
    header p  { font-size: 0.85rem; color: #64748b; margin-top: 4px; }

    /* ── Grid ── */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      max-width: 1000px;
      margin: 0 auto;
    }

    /* ── Card ── */
    .card {
      background: #1e293b;
      border-radius: 14px;
      padding: 20px 24px;
      border: 1px solid #334155;
    }
    .card h2 {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: #64748b;
      margin-bottom: 12px;
    }

    /* ── Sensor Values ── */
    .val-big {
      font-size: 2.8rem;
      font-weight: 700;
      color: #38bdf8;
      line-height: 1;
    }
    .val-label {
      font-size: 0.8rem;
      color: #94a3b8;
      margin-top: 4px;
    }
    .badge {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
      margin-top: 8px;
    }
    .badge-pressed  { background: #ef4444; color: #fff; }
    .badge-released { background: #334155; color: #94a3b8; }

    /* ── Pattern Buttons ── */
    .btn-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 4px;
    }
    .btn-pattern {
      padding: 10px 6px;
      border: 2px solid #334155;
      border-radius: 10px;
      background: #0f172a;
      color: #cbd5e1;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.15s;
      text-align: center;
    }
    .btn-pattern:hover   { border-color: #38bdf8; color: #38bdf8; }
    .btn-pattern.active  {
      border-color: #7dd3fc;
      background: #0c4a6e;
      color: #7dd3fc;
      font-weight: 700;
    }

    /* ── Status dot ── */
    .status-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.85rem;
      color: #94a3b8;
      margin-top: 14px;
    }
    .dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: #22c55e;
      animation: pulse 1.6s infinite;
    }
    @keyframes pulse {
      0%,100% { opacity: 1; }
      50%      { opacity: 0.3; }
    }

    /* ── Chart ── */
    .chart-wrap { position: relative; height: 180px; margin-top: 8px; }

    /* ── Timestamp ── */
    #timestamp { font-size: 0.75rem; color: #475569; margin-top: 10px; }

    /* ── Mobile ── */
    @media (max-width: 480px) {
      .val-big { font-size: 2rem; }
      header h1 { font-size: 1.2rem; }
    }
  </style>
</head>
<body>

<header>
  <h1>🌐 COM3505 IoT Dashboard</h1>
  <p>ESP32 Live Sensor Monitor &amp; LED Controller</p>
</header>

<div class="grid">

  <!-- ── Sensor Card ── -->
  <div class="card">
    <h2>📡 Button Sensor</h2>
    <div class="val-big" id="pressCount">—</div>
    <div class="val-label">Total Presses</div>
    <div id="btnBadge" class="badge badge-released">RELEASED</div>
    <div id="timestamp" class="status-row">Last update: —</div>
  </div>

  <!-- ── Pattern Control Card ── -->
  <div class="card">
    <h2>💡 LED Pattern Control</h2>
    <div class="btn-grid">
      <button class="btn-pattern" onclick="setPattern(0)" id="btn0">⬜ Solid</button>
      <button class="btn-pattern" onclick="setPattern(1)" id="btn1">✦ Blink</button>
      <button class="btn-pattern" onclick="setPattern(2)" id="btn2">➜ Chase</button>
      <button class="btn-pattern" onclick="setPattern(3)" id="btn3">🌈 Rainbow</button>
      <button class="btn-pattern active" onclick="setPattern(4)" id="btn4" style="grid-column:span 2">🔥 Fire</button>
    </div>
    <div class="status-row">
      <span class="dot"></span>
      <span id="currentPatternLabel">Pattern: —</span>
    </div>
  </div>

  <!-- ── Chart Card ── -->
  <div class="card" style="grid-column: 1 / -1;">
    <h2>📊 Press Count – Live Graph</h2>
    <div class="chart-wrap">
      <canvas id="pressChart"></canvas>
    </div>
  </div>

</div>

<script>
  // ── Chart setup ─────────────────────────────────────────────
  const ctx = document.getElementById('pressChart').getContext('2d');
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Button Presses',
        data: [],
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56,189,248,0.12)',
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.3,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#64748b', maxTicksLimit: 8 }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' }, beginAtZero: true }
      },
      plugins: { legend: { labels: { color: '#94a3b8' } } }
    }
  });

  // ── Pattern button highlight ─────────────────────────────────
  const PATTERN_NAMES = {0:'Solid', 1:'Blink', 2:'Chase', 3:'Rainbow', 4:'Fire 🔥'};

  function highlightPattern(id) {
    for (let i = 0; i <= 4; i++) {
      document.getElementById('btn' + i).classList.toggle('active', i === id);
    }
    document.getElementById('currentPatternLabel').textContent =
      'Pattern: ' + (PATTERN_NAMES[id] || '—');
  }

  // ── Send pattern command to server ──────────────────────────
  function setPattern(id) {
    fetch('/pattern', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pattern: id })
    }).then(() => highlightPattern(id));
  }

  // ── AJAX: poll /status every 2 seconds ──────────────────────
  function updateDashboard() {
    fetch('/status')
      .then(r => r.json())
      .then(data => {
        // Sensor values
        document.getElementById('pressCount').textContent = data.press_count;

        const badge = document.getElementById('btnBadge');
        if (data.button === 1) {
          badge.textContent = 'PRESSED';
          badge.className = 'badge badge-pressed';
        } else {
          badge.textContent = 'RELEASED';
          badge.className = 'badge badge-released';
        }

        document.getElementById('timestamp').textContent =
          'Last update: ' + data.timestamp;

        // Pattern highlight
        highlightPattern(data.pattern);

        // Chart update
        const now = new Date().toLocaleTimeString();
        chart.data.labels.push(now);
        chart.data.datasets[0].data.push(data.press_count);
        if (chart.data.labels.length > 30) {
          chart.data.labels.shift();
          chart.data.datasets[0].data.shift();
        }
        chart.update('none');
      })
      .catch(() => {});
  }

  setInterval(updateDashboard, 2000);
  updateDashboard();
</script>
</body>
</html>
"""

# ================================================================
# Routes
# ================================================================

# ── GET /  →  Dashboard ─────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


# ── POST /data  ←  ESP32 sends sensor readings ──────────────────
@app.route("/data", methods=["POST"])
def receive_data():
    global latest_data, pending_pattern

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid JSON"}), 400

    latest_data["button"]      = int(payload.get("button",      0))
    latest_data["press_count"] = int(payload.get("press_count", 0))
    latest_data["pattern"]     = int(payload.get("pattern",     1))
    latest_data["timestamp"]   = datetime.now().strftime("%H:%M:%S")

    # Append to history buffer
    history.append({
        "time":        latest_data["timestamp"],
        "press_count": latest_data["press_count"]
    })

    print(f"[DATA] {latest_data}")
    return jsonify({"status": "ok", "pending_pattern": pending_pattern}), 200


# ── GET /status  →  Browser AJAX polls live data ────────────────
@app.route("/status")
def get_status():
    return jsonify({
        "button":       latest_data["button"],
        "press_count":  latest_data["press_count"],
        "pattern":      pending_pattern,        # reflect what browser set
        "timestamp":    latest_data["timestamp"],
        "history":      list(history)
    })


# ── POST /pattern  ←  Browser sets new LED pattern ──────────────
@app.route("/pattern", methods=["POST"])
def set_pattern():
    global pending_pattern

    payload = request.get_json(silent=True)
    if not payload or "pattern" not in payload:
        return jsonify({"error": "missing pattern"}), 400

    new_id = int(payload["pattern"])
    if new_id not in PATTERN_NAMES:
        return jsonify({"error": "invalid pattern id"}), 400

    pending_pattern = new_id
    print(f"[CMD] Pattern set to {new_id} ({PATTERN_NAMES[new_id]})")
    return jsonify({"status": "ok", "pattern": pending_pattern})


# ── GET /command  ←  ESP32 polls for pattern command ────────────
@app.route("/command")
def get_command():
    # Return just the pattern number as plain text
    return str(pending_pattern), 200, {"Content-Type": "text/plain"}


# ================================================================
# Entry point
# ================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  COM3505 Flask Server Starting")
    print("  Dashboard → http://localhost:5000")
    print("=" * 50)
    # host="0.0.0.0" makes server accessible from ESP32 on same network
    app.run(host="0.0.0.0", port=9000, debug=True)
