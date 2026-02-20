# 모니터링 시스템 구축 (Grafana + Prometheus)

## 개요

- **Prometheus**: Flask 앱의 `/metrics`를 주기적으로 스크래핑해 메트릭 수집.
- **Grafana**: Prometheus를 데이터 소스로 연결해 대시보드·알람 구성.

---

## 1. 앱에서 Prometheus 메트릭 노출

### 의존성
```bash
pip install flask prometheus_client
```

### 실행
```bash
python server/app.py
```
- 대시보드: http://127.0.0.1:5001  
- 메트릭: http://127.0.0.1:5001/metrics  
- (기본 포트 5001 — macOS에서 5000은 AirPlay가 사용할 수 있음)  

### 노출 메트릭 (예시)
| 메트릭 이름 | 타입 | 설명 |
|------------|------|------|
| `aoii_readings_total` | Gauge | 총 수신 횟수 |
| `aoii_mae_temp` | Gauge | 온도 평균 절대 오차 |
| `aoii_mae_humidity` | Gauge | 습도 평균 절대 오차 |
| `aoii_avg_temp_celsius` | Gauge | 평균 실제 온도 |
| `aoii_avg_humidity_percent` | Gauge | 평균 실제 습도 |
| `aoii_last_received_timestamp_seconds` | Gauge | 마지막 수신 시각(Unix 초) |

---

## 2. Prometheus 설치 및 설정

### 설치 (예: macOS)
```bash
brew install prometheus
```
또는 [prometheus.io/download](https://prometheus.io/download/) 에서 다운로드.

### 설정 파일 사용
프로젝트 루트에서:
```bash
prometheus --config.file=monitoring/prometheus.yml
```
기본 UI: http://localhost:9090  
- Status → Targets 에서 `localhost:5001` 이 UP 인지 확인.

### scrape 대상 변경
`monitoring/prometheus.yml` 의 `targets` 를 수정.  
예: 라즈베리파이에서 앱을 실행 중이면 `["라즈베리파이_IP:5001"]` 으로 지정.

---

## 3. Grafana 설치 및 Prometheus 연결

### 설치 (예: macOS)
```bash
brew install grafana
brew services start grafana
```
또는 [grafana.com/grafana/download](https://grafana.com/grafana/download)

### 접속
- http://localhost:3000 (기본 로그인: admin / admin)

### 데이터 소스 추가
1. **Configuration** → **Data sources** → **Add data source**
2. **Prometheus** 선택
3. **URL**: `http://localhost:9090` (Prometheus 주소)
4. **Save & test**

---

## 4. Grafana 대시보드 예시

**Dashboard** → **New** → **Add new panel**

### 패널 1: 총 수신 횟수
- Query: `aoii_readings_total`
- Visualization: Stat 또는 Gauge

### 패널 2: MAE (온도)
- Query: `aoii_mae_temp`
- Visualization: Time series 또는 Stat

### 패널 3: 마지막 수신 후 경과 시간 (데이터 끊김 감지)
- Query: `time() - aoii_last_received_timestamp_seconds`
- 단위: seconds → 필요 시 60 나누어 “분”으로 표시
- Alert: 이 값이 600 (10분) 초과 시 알람 (선택)

### 패널 4: 평균 온도/습도
- Query: `aoii_avg_temp_celsius`, `aoii_avg_humidity_percent`
- Visualization: Time series (여러 메트릭 한 그래프)

---

## 5. 알람 (Grafana Alert)

1. 패널 편집 → **Alert** 탭 → **Create alert rule**
2. 조건 예: `time() - aoii_last_received_timestamp_seconds > 600` (10분간 수신 없음)
3. **Contact points** 에서 이메일/슬랙 등 알림 채널 설정.

---

## 6. 요약 순서

1. `pip install flask prometheus_client` 후 `python server/app.py` 로 앱 실행 (기본 port 5001).
2. `prometheus --config.file=monitoring/prometheus.yml` 로 Prometheus 실행 (port 9090).
3. Grafana 설치·실행 후, Data source 로 Prometheus (`http://localhost:9090`) 추가.
4. 대시보드에서 위 메트릭으로 패널·알람 구성.

라즈베리파이에서 앱을 실행할 경우, PC의 Prometheus가 `라즈베리파이_IP:5001` 을 스크래핑하도록 `prometheus.yml` 의 `targets` 만 해당 IP로 바꾸면 됩니다.
