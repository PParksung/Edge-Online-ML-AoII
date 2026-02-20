# Edge-Online-ML-AoII

엣지 디바이스(ESP32)에서 **온·습도 예측 ML**과 **온라인 학습**을 수행하고, 전송 빈도를 줄여 **AoII(Age of Incorrect Information)** 를 고려한 IoT 데이터 수집 시스템입니다.

---

## 목차

- [개요](#개요)
- [프로젝트 구조](#프로젝트-구조)
- [요구 사항](#요구-사항)
- [설정](#설정)
- [실행 방법](#실행-방법)
- [문서](#문서)

---

## 개요

- **엣지**: ESP32(Heltec) + AHT 온·습도 센서, LoRa로 게이트웨이에 전송.
- **예측 모델**: 3-16-2 MLP (입력: 온도, 습도, 시간; 출력: 다음 시점 온·습도). 오프라인 사전 학습 후 엣지/게이트웨이에서 동일 가중치로 추론.
- **온라인 학습**: 게이트웨이에서 실제 수신값으로 역전파하여 모델을 갱신하고, 엣지와 동기화(또는 엣지 자체 학습)로 전송 횟수 절감.
- **데이터 흐름**: 엣지 → 시리얼 → 게이트웨이(Python) → MQTT → MySQL/CSV, Flask 대시보드·Prometheus 메트릭.

---

## 프로젝트 구조

```
Edge-Online-ML-AoII/
├── README.md                 # 이 파일
├── requirements.txt          # Python 의존성
├── .env                      # 환경 변수 (git 제외, 팀원 공유)
│
├── edge_node/                # ESP32 (Arduino) 펌웨어
│   ├── normal_edge_sensor.ino    # RAW 데이터 로거 (예측 없음)
│   ├── threshold_edge_sensor.ino # 임계값 기반 전송 (beta, heartbeat)
│   └── MLP_edge_sensor.ino       # 3-16-2 MLP 예측 + 온라인 학습, LoRa 전송
│
├── gateway/                  # 게이트웨이 (시리얼 → MQTT)
│   ├── gateway.py            # 시리얼 수신 → MQTT publish, 게이트웨이 측 MLP 온라인 학습
│   ├── gateway_MLP_Logic.py  # MLP 추론 및 역전파(online_update)
│   ├── gateway_edge.ino      # (선택) 게이트웨이용 엣지 펌웨어
│   └── experiment_log_online.csv
│
├── server/                   # 백엔드·수집·모니터링
│   ├── app.py                # Flask 대시보드 + Prometheus /metrics
│   ├── db.py                 # MySQL 연결 및 readings 테이블
│   ├── mqtt_to_mysql.py      # MQTT 구독 → MySQL 저장
│   ├── mqtt_to_csv.py        # MQTT 구독 → CSV 저장
│   ├── edge_serial_logger.py # 시리얼 직접 로깅
│   ├── MQTT.md               # MQTT 설정·실행 가이드
│   └── MONITORING.md         # Grafana + Prometheus 가이드
│
├── compare_group_logging/    # 비교 실험용 로거
│   ├── normal_edge_logger.py     # 일반 엣지 시리얼 → CSV
│   └── threshold_edge_logger.py  # 임계값 엣지 시리얼 → CSV
│
├── monitoring/
│   └── prometheus.yml        # Prometheus 스크래핑 설정 (Flask :5001)
│
├── Pre_train.py              # 오프라인 MLP 학습 → ESP32용 C 코드(가중치·스케일러) 출력
├── dataset/
│   └── Pre_Train_Dataset.csv # 사전 학습용 시계열 (timestamp, temperature, humidity)
│
└── data/                     # 실험 데이터 (메타 등)
    └── <ulid>/
        └── meta.json
```

---

## 요구 사항

- **Python**: 3.8+
- **하드웨어**: ESP32 (Heltec 등), AHT 센서, LoRa (MLP 엣지용)
- **선택**: MySQL, Mosquitto(MQTT), Prometheus, Grafana

### Python 패키지

```bash
pip install -r requirements.txt
```

주요 의존성: `pandas`, `numpy`, `scikit-learn`, `pymysql`, `flask`, `prometheus_client`, `paho-mqtt`, `pyserial`

---

## 설정

1. **`.env`** (프로젝트 루트, git 제외)

   - MySQL: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
   - MQTT: `MQTT_BROKER`, `MQTT_PORT` (예: 라즈베리파이 IP, 1883)
   - 시리얼: `SERIAL_PORT` (맥: `/dev/cu.usbserial-3`, 라즈베리파이: `/dev/ttyUSB0`)

2. **DB 초기화**

   - MySQL에 `aoii` DB 생성 후, `server/db.py`의 `init_db()` 실행해 `readings` 테이블 생성.

3. **MQTT·모니터링 상세**

   - `server/MQTT.md`: 브로커 설치, 토픽 `aoii/readings`, 구독자(mqtt_to_csv, mqtt_to_mysql) 실행 순서.
   - `server/MONITORING.md`: Flask 앱, Prometheus, Grafana 연결 방법.

---

## 실행 방법

### 1. 오프라인 MLP 학습 (가중치 생성)

```bash
python Pre_train.py
```

- `dataset/Pre_Train_Dataset.csv` 사용.
- 학습 후 터미널에 출력되는 C 배열(스케일러, W1, B1, W2, B2)을 `edge_node/MLP_edge_sensor.ino` 및 `gateway/gateway.py` 쪽 모델 파라미터에 반영.

### 2. 엣지 펌웨어

- Arduino IDE에서 `edge_node/` 내 해당 `.ino` 열기.
- 보드·라이브러리(Adafruit_AHTX0, LoRa, SSD1306 등) 설정 후 업로드.
- **MLP 엣지**: 시리얼로 예측·실제값·이벤트(RX/EST) 전송; 게이트웨이와 시리얼로 연결.

### 3. 게이트웨이 (시리얼 → MQTT)

- ESP32 USB가 연결된 PC(맥북 또는 라즈베리파이)에서:
- 오프라인 환경이라면 시스템 시간을 수동으로 설정해주어야함 (현재 UTC 시각에 맞추어 입력)
```bash
sudo date -s "2026-02-20 14:00:00" 
```
```bash
python gateway/gateway.py
```

- 시리얼 수신 → 게이트웨이 MLP 예측/온라인 학습 → MQTT 토픽 `aoii/readings`로 publish.

### 4. MQTT 구독자 (저장)

- **CSV** (예: 라즈베리파이): `python server/mqtt_to_csv.py`
- **MySQL** (예: 맥북): `python server/mqtt_to_mysql.py`

### 5. 대시보드·메트릭

```bash
python server/app.py
```

- 대시보드: http://127.0.0.1:5001  
- Prometheus 메트릭: http://127.0.0.1:5001/metrics  

Prometheus 실행: `prometheus --config.file=monitoring/prometheus.yml`  
Grafana 연동은 `server/MONITORING.md` 참고.

### 6. 비교 실험 로깅 (임계값 vs 일반)

- 시리얼만 연결해 CSV로 남길 때:
  - `python compare_group_logging/normal_edge_logger.py`
  - `python compare_group_logging/threshold_edge_logger.py`

---

## 문서

| 문서 | 내용 |
|------|------|
| [server/MQTT.md](server/MQTT.md) | MQTT 브로커, 토픽, .env, 실행 순서(라즈베리파이/맥북) |
| [server/MONITORING.md](server/MONITORING.md) | Flask, Prometheus, Grafana 설치·연동·메트릭·알람 예시 |

---

## 라이선스 / 기여

UNLV 프로젝트 저장소입니다. 사용·수정 시 팀 내 규정을 따르세요.
