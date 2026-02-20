#!/usr/bin/env python3
"""
모니터링: Flask 대시보드 + Prometheus /metrics.
실행: python server/app.py  →  http://127.0.0.1:5001  /  Prometheus는 http://127.0.0.1:5001/metrics 스크래핑 (기본 5001, macOS AirPlay 회피)
"""
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _f in (os.path.join(ROOT, ".env"), os.path.join(ROOT, "server", "mysql_example.env")):
    if os.path.isfile(_f):
        with open(_f, "r", encoding="utf-8") as _file:
            for _line in _file:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip()
                    if _k.startswith("MYSQL_"):
                        os.environ[_k] = _v
        break

from flask import Flask, render_template_string, jsonify, request, Response
from server.db import get_recent, get_stats

try:
    from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

app = Flask(__name__)

# Prometheus 메트릭 (스크래핑 시 DB 값으로 갱신)
if PROMETHEUS_AVAILABLE:
    METRIC_READINGS_TOTAL = Gauge("aoii_readings_total", "Total number of readings received")
    METRIC_MAE_TEMP = Gauge("aoii_mae_temp", "Mean absolute error (temperature)")
    METRIC_MAE_HUMIDITY = Gauge("aoii_mae_humidity", "Mean absolute error (humidity)")
    METRIC_AVG_TEMP = Gauge("aoii_avg_temp_celsius", "Average actual temperature")
    METRIC_AVG_HUMIDITY = Gauge("aoii_avg_humidity_percent", "Average actual humidity")
    METRIC_LAST_RECEIVED = Gauge("aoii_last_received_timestamp_seconds", "Unix timestamp of last reading")


def _update_prometheus_metrics():
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        s = get_stats()
        METRIC_READINGS_TOTAL.set(s["total"])
        if s["total"] > 0:
            METRIC_MAE_TEMP.set(s["mae_temp"])
            METRIC_MAE_HUMIDITY.set(s["mae_humidity"])
            METRIC_AVG_TEMP.set(s["avg_temp"])
            METRIC_AVG_HUMIDITY.set(s["avg_humidity"])
            if s.get("last_at"):
                try:
                    if isinstance(s["last_at"], str):
                        dt = datetime.fromisoformat(s["last_at"].replace("Z", "+00:00"))
                    else:
                        dt = s["last_at"]
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    METRIC_LAST_RECEIVED.set(dt.timestamp())
                except Exception:
                    pass
    except Exception:
        pass  # DB 등 오류 시 메트릭만 갱신 생략, 500 내지 않음


HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AoII 모니터링</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }
    h1 { color: #eee; }
    .cards { display: flex; flex-wrap: wrap; gap: 16px; margin: 20px 0; }
    .card { background: #16213e; padding: 16px 24px; border-radius: 8px; min-width: 140px; }
    .card .val { font-size: 1.5rem; font-weight: bold; color: #0f4c81; }
    .card .label { font-size: 0.85rem; color: #888; }
    #chartWrap { max-width: 900px; height: 400px; margin-top: 24px; }
    .meta { color: #888; font-size: 0.9rem; margin-top: 16px; }
    a { color: #0f4c81; }
  </style>
</head>
<body>
  <h1>Edge–Gateway 모니터링</h1>
  <p><a href="/metrics">Prometheus /metrics</a></p>
  <div class="cards">
    <div class="card"><div class="label">총 수신 횟수</div><div class="val" id="total">-</div></div>
    <div class="card"><div class="label">평균 온도 (°C)</div><div class="val" id="avg_temp">-</div></div>
    <div class="card"><div class="label">평균 습도 (%)</div><div class="val" id="avg_humidity">-</div></div>
    <div class="card"><div class="label">MAE (온도)</div><div class="val" id="mae_temp">-</div></div>
    <div class="card"><div class="label">MAE (습도)</div><div class="val" id="mae_humidity">-</div></div>
  </div>
  <div class="meta">첫 수신: <span id="first_at">-</span> &nbsp;|&nbsp; 마지막: <span id="last_at">-</span></div>
  <div id="chartWrap"><canvas id="chart"></canvas></div>
  <script>
    function refresh() {
      fetch('/api/stats').then(r=>r.json()).then(s=>{
        document.getElementById('total').textContent = s.total;
        if (s.total === 0) return;
        document.getElementById('avg_temp').textContent = s.avg_temp;
        document.getElementById('avg_humidity').textContent = s.avg_humidity;
        document.getElementById('mae_temp').textContent = s.mae_temp;
        document.getElementById('mae_humidity').textContent = s.mae_humidity;
        document.getElementById('first_at').textContent = s.first_at || '-';
        document.getElementById('last_at').textContent = s.last_at || '-';
      });
      fetch('/api/recent?limit=200').then(r=>r.json()).then(data=>{
        const labels = data.map(d=> d.created_at ? d.created_at.replace('T',' ').slice(0,19) : '');
        window.chartObj.data.labels = labels;
        window.chartObj.data.datasets[0].data = data.map(d=> d.actual_temp);
        window.chartObj.data.datasets[1].data = data.map(d=> d.pred_temp);
        window.chartObj.data.datasets[2].data = data.map(d=> d.actual_humidity);
        window.chartObj.data.datasets[3].data = data.map(d=> d.pred_humidity);
        window.chartObj.update();
      });
    }
    const ctx = document.getElementById('chart').getContext('2d');
    window.chartObj = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Actual T (°C)', data: [], borderColor: '#e94560', tension: 0.2 },
          { label: 'Pred T (°C)', data: [], borderColor: '#0f4c81', tension: 0.2 },
          { label: 'Actual H (%)', data: [], borderColor: '#533483', tension: 0.2, yAxisID: 'y1' },
          { label: 'Pred H (%)', data: [], borderColor: '#3282b8', tension: 0.2, yAxisID: 'y1' }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          y: { title: { display: true, text: 'Temperature (°C)' } },
          y1: { position: 'right', title: { display: true, text: 'Humidity (%)' } }
        }
      }
    });
    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/recent")
def api_recent():
    limit = int(request.args.get("limit", 500))
    return jsonify(get_recent(limit=limit))


@app.route("/metrics")
def metrics():
    """Prometheus가 스크래핑하는 엔드포인트. DB 통계를 메트릭으로 노출."""
    if not PROMETHEUS_AVAILABLE:
        return "prometheus_client not installed. pip install prometheus_client", 500
    try:
        _update_prometheus_metrics()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
    except Exception:
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)  # 오류 시에도 200 + 기존 메트릭


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"대시보드: http://127.0.0.1:{port}  |  Prometheus: http://127.0.0.1:{port}/metrics")
    app.run(host="0.0.0.0", port=port, debug=False)
