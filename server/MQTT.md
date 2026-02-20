# MQTT 적용 요약: 변경 사항 및 실행 순서

## 0. 라즈베리파이에서 할 명령어 (요약)

**라즈베리파이 SSH 접속 후** 아래만 순서대로 실행하면 됩니다.  
`/home/pi/Edge-Online-ML-AoII` 대신 실제 프로젝트 경로로 바꿔서 쓰세요.

```bash
# 1) Mosquitto 설치 (최초 1회)
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto

# 2) Python 패키지 (paho-mqtt 등, 최초 1회)
cd /home/pi/Edge-Online-ML-AoII
pip install -r requirements.txt

# 3) 브로커 켜기
sudo systemctl start mosquitto

# 4) 구독자 2개 백그라운드 실행 (DB 저장, CSV 저장)
cd /home/pi/Edge-Online-ML-AoII
python3 server/mqtt_to_mysql.py &
python3 server/mqtt_to_csv.py &

# 5) 게이트웨이 실행 (시리얼 → MQTT). USB 시리얼 연결된 상태에서
python3 gateway/gateway.py
```

이후 엣지에서 데이터가 오면 gateway가 MQTT로 보내고, 구독자들이 DB/CSV에 저장합니다.

---

## 1. 바꾼 코드 요약

| 대상 | 변경 내용 |
|------|-----------|
| **gateway/gateway.py** | DB(`insert_reading`)·CSV 직접 쓰기 제거 → 수신/EST 발생 시 **MQTT로 한 번만** `aoii/readings`에 JSON publish |
| **server/mqtt_to_mysql.py** (신규) | `aoii/readings` 구독 → `event == "RX"`일 때만 `db.insert_reading()` 호출 |
| **server/mqtt_to_csv.py** (신규) | `aoii/readings` 구독 → RX/EST 모두 `experiment_log_online.csv`에 한 줄씩 append |
| **requirements.txt** | `paho-mqtt` 추가 |

Gateway는 이제 **MQTT 브로커에만 메시지를 보내고**, DB·CSV 기록은 각 구독자 스크립트가 담당합니다.

---

## 2. MQTT “등록”이란?

**별도 등록 절차 없습니다.**  
MQTT는 브로커(예: Mosquitto)만 떠 있으면, 클라이언트가 **같은 브로커 주소**로 접속해 publish/ subscribe 하면 됩니다.  
토픽 `aoii/readings`도 사전 등록 없이, 처음 메시지를 보내는 순간 사용됩니다.

---

## 3. 라즈베리파이랑 “먼저 연결”해야 하나?

- **실제 데이터 흐름**:  
  - **엣지(ESP32)** → LoRa → **게이트웨이(ESP32)** → USB 시리얼 → **라즈베리파이**  
  - 라즈베리파이에서 `gateway.py`가 돌아가므로, **gateway와 MQTT 브로커는 같은 기기(라즈베리파이)에서 동작**하는 구성을 권장합니다.
- **권장 순서**  
  1. **라즈베리파이에 SSH 접속** (코드 배포·실행용).  
  2. **라즈베리파이에 MQTT 브로커(Mosquitto) 설치·실행.**  
  3. **같은 라즈베리파이에서** 구독자 2개 실행 → 그 다음 gateway 실행.  
  즉, “라즈베리파이랑 먼저 연결(SSH)”한 뒤, 그 위에서 브로커 → 구독자 → gateway 순으로 켜면 됩니다.

---

## 4. 실행 순서 (라즈베리파이 기준)

1. **브로커 기동**  
   ```bash
   sudo systemctl start mosquitto
   # 또는: mosquitto -v
   ```
2. **구독자 실행** (DB 저장, CSV 저장)  
   ```bash
   cd /path/to/Edge-Online-ML-AoII
   python server/mqtt_to_mysql.py &   # 백그라운드
   python server/mqtt_to_csv.py &    # 백그라운드
   ```
3. **게이트웨이 실행** (시리얼 수신 → MQTT publish)  
   ```bash
   python gateway/gateway.py
   ```

PC에서 구독자만 실행하려면, PC와 라즈베리파이가 같은 네트워크에 있어야 하고, `MQTT_BROKER`를 라즈베리파이 IP로 설정한 뒤 위 2번만 PC에서 실행하면 됩니다.

---

## 5. Mosquitto 설치 (라즈베리파이)

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```

기본 포트 **1883** 사용.  
필요 시 `.env` 또는 환경 변수로 `MQTT_BROKER=localhost`, `MQTT_PORT=1883` 지정 (기본값이므로 생략 가능).

---

## 6. 토픽·페이로드

- **토픽**: `aoii/readings`  
- **페이로드**: JSON  
  - `event`: `"RX"` (엣지 수신) 또는 `"EST"` (게이트웨이 추정)  
  - `timestamp`, `time_n`, `actual_t`, `actual_h`, `pred_t`, `pred_h`, `error_t`, `error_h`, `total_tx`  
  - EST일 때 `actual_t`/`actual_h`/`error_t`/`error_h`는 `null` 가능.

이제 **코드에서 바꾼 것**, **MQTT 등록 없음**, **라즈베리파이 연결 후 브로커 → 구독자 → gateway 순서**만 지키면 됩니다.
