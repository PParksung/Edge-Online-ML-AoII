# 모니터링 (Grafana + Prometheus)

## 개요

- **Prometheus**: Flask 앱 `/metrics`를 주기적으로 스크래핑해 메트릭 수집.
- **Grafana**: Prometheus를 데이터 소스로 연결해 대시보드·알람 구성.
- **설정**: 프로젝트 루트 `.env` (MySQL 등). git 제외.

---

## 1. Flask 앱 실행

```bash
pip install flask prometheus_client   # 필요 시
python server/app.py
```

- 대시보드: http://127.0.0.1:5001  
- 메트릭: http://127.0.0.1:5001/metrics  
- 포트 5001 사용 (macOS에서 5000은 AirPlay 사용 가능).

### 노출 메트릭 예시

| 메트릭 | 타입 | 설명 |
|--------|------|------|
| `aoii_readings_total` | Gauge | 총 수신 횟수 |
| `aoii_mae_temp` | Gauge | 온도 평균 절대 오차 |
| `aoii_mae_humidity` | Gauge | 습도 평균 절대 오차 |
| `aoii_avg_temp_celsius` | Gauge | 평균 실제 온도 |
| `aoii_avg_humidity_percent` | Gauge | 평균 실제 습도 |
| `aoii_last_received_timestamp_seconds` | Gauge | 마지막 수신 시각(Unix 초) |

---

## 2. Prometheus

### 설치 (macOS)

```bash
brew install prometheus
```

### 실행 (프로젝트 안에 data 폴더 안 쌓이게 하려면)

```bash
# 저장 경로를 프로젝트 밖으로 지정 (지정 안 하면 프로젝트 루트에 data/ 생성됨)
prometheus --config.file=monitoring/prometheus.yml --storage.tsdb.path=/tmp/prometheus_aoii
```

- macOS에서 재부팅 후에도 유지하려면: `--storage.tsdb.path=$HOME/prometheus_aoii_data` 등으로 지정.
- UI: http://localhost:9090  
- **Status → Targets**에서 `localhost:5001`이 UP인지 확인.  
- 앱을 라즈베리파이에서 실행하면 `prometheus.yml`의 `targets`를 `["라즈베리파이_IP:5001"]`로 변경.

---

## 3. Grafana

### 설치·실행 (macOS)

```bash
brew install grafana
brew services start grafana
```

- 접속: http://localhost:3000 (기본 로그인: admin / admin)

### 데이터 소스

1. **Configuration** → **Data sources** → **Add data source**
2. **Prometheus** 선택, **URL**: `http://localhost:9090` → **Save & test**

### 대시보드 패널 예시

- **총 수신 횟수**: Query `aoii_readings_total`, Visualization Stat
- **MAE(온도)**: Query `aoii_mae_temp`, Time series 또는 Stat
- **데이터 끊김**: Query `time() - aoii_last_received_timestamp_seconds`, 단위 seconds (필요 시 60으로 나누어 분 표시)
- **평균 온도/습도**: Query `aoii_avg_temp_celsius`, `aoii_avg_humidity_percent`, Time series

### 알람 예시

- 패널 편집 → **Alert** → 조건: `time() - aoii_last_received_timestamp_seconds > 600` (10분간 수신 없음)
- **Contact points**에서 이메일/슬랙 등 설정

---

## 4. 요약

1. `python server/app.py` (port 5001)  
2. `prometheus --config.file=monitoring/prometheus.yml` (port 9090)  
3. Grafana 실행 후 Prometheus 데이터 소스 추가 (http://localhost:9090)  
4. 대시보드에서 위 메트릭으로 패널·알람 구성  

앱을 라즈베리파이에서 실행할 경우, Prometheus `targets`만 해당 IP:5001로 설정하면 된다.
