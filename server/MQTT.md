# MQTT 설정 및 실행

## 개요

- Gateway는 수신 데이터를 **MQTT로만 발행**하고, DB/CSV 저장은 **구독자**가 담당한다.
- **브로커**: 라즈베리파이에 Mosquitto 실행. 별도 등록 없이 토픽 `aoii/readings` 사용.
- **설정**: 프로젝트 루트 `.env` 한 파일만 사용 (git 제외, 팀원에게 내용 공유).

---

## 토픽·페이로드

| 항목 | 내용 |
|------|------|
| 토픽 | `aoii/readings` |
| 페이로드 | JSON. `event`(RX/EST), `timestamp`, `time_n`, `actual_t`, `actual_h`, `pred_t`, `pred_h`, `error_t`, `error_h`, `total_tx` |

---

## 역할 정리

| 구성요소 | 실행 위치 | 역할 |
|----------|-----------|------|
| **gateway/gateway.py** | **라즈베리파이** (수신용 LoRa ESP32가 Pi USB에 연결됨) | 시리얼 수신 → MQTT publish |
| **server/mqtt_to_csv.py** | 라즈베리파이 | 구독 → `experiment_log_online.csv` 저장 |
| **server/mqtt_to_mysql.py** | 맥북 | 구독 → MySQL `readings` 저장 |
| **Mosquitto** | 라즈베리파이 | MQTT 브로커 (port 1883) |

- **하드웨어**: 수신용 LoRa(게이트웨이 ESP32) → **라즈베리파이 USB**. 온습도(엣지 ESP32) → **맥북 USB만** (전원·시리얼 로그용).

---

## .env에 넣을 키 (팀원 공유용)

```
# MySQL (맥북 로컬 DB)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=비밀번호
MYSQL_DATABASE=aoii

# MQTT (맥북에서 실행할 때 브로커 = 라즈베리파이 IP)
MQTT_BROKER=192.168.x.x
MQTT_PORT=1883

# 시리얼 (gateway.py는 Pi에서만 실행 → Pi: /dev/ttyUSB0)
SERIAL_PORT=/dev/ttyUSB0
```

---

## 실행 순서

### 라즈베리파이

```bash
# Mosquitto 설치 (최초 1회)
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto

# 외부 접속 허용 (맥북 등에서 구독하려면)
sudo nano /etc/mosquitto/mosquitto.conf
# 맨 아래 추가: listener 1883 0.0.0.0  /  allow_anonymous true
sudo systemctl restart mosquitto

# 구독자 (CSV만; DB는 맥북에서 처리)
cd ~/Edge-Online-ML-AoII
source venv/bin/activate
python server/mqtt_to_csv.py &
```

### 라즈베리파이 (gateway 실행)

```bash
# 수신용 LoRa ESP32를 Pi USB에 연결한 뒤
cd ~/Edge-Online-ML-AoII
source venv/bin/activate
python gateway/gateway.py
```

- Pi에서는 `.env`에 `SERIAL_PORT=/dev/ttyUSB0` (또는 `ls /dev/ttyUSB*`로 확인한 포트) 설정. `MQTT_BROKER=localhost`면 됨.

### 맥북

```bash
# 1) MySQL 실행, DB 생성 (aoii)
# 2) 온습도(엣지)는 맥북 USB에만 연결 (전원·시리얼 로그용). gateway는 Pi에서 실행하므로 맥북에서는 gateway 실행 안 함.
# 3) DB 구독자 실행 (Pi 브로커 구독 → 맥북 MySQL 저장)
.venv/bin/python server/mqtt_to_mysql.py
```

- 맥북 `.env`에 `MQTT_BROKER=라즈베리파이IP` 필요. **mqtt_to_mysql**만 맥북에서 실행해 맥북 MySQL에 저장.

---

## Mosquitto만 Pi에서 켜기

```bash
sudo systemctl start mosquitto
```

기본 포트 1883. `.env`에 `MQTT_BROKER`, `MQTT_PORT` 없으면 각 스크립트 기본값(localhost, 1883) 사용.
