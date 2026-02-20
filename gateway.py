import sys
import serial
import time
import json
import os
from datetime import datetime, timezone, timedelta
from gateway_MLP_Logic import GatewayMLP
import paho.mqtt.client as mqtt

# 프로젝트 루트 (설정 파일 등)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# MQTT 설정 (라즈베리파이에서 broker 같은 기기면 localhost, PC에서 실행 시 Pi IP로 변경)
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC_READINGS = "aoii/readings"

# =========================================================
# 1. 3-16-2 모델 파라미터
# =========================================================
X_MEAN = [11.951440, 34.796511, 0.518765]
X_STD  = [5.192832, 19.254291, 0.287677]
Y_MEAN = [11.952372, 34.792687]
Y_STD  = [5.192482, 19.253258]

W1 = [
  [-0.556351, 0.189494, -0.093627, 0.395785, -0.577321, 0.007591, -0.283381, 0.373759, 0.595335, 0.768831, -1.089705, 0.857749, 0.713353, -0.719686, 0.349461, -0.002144],
  [0.278056, 0.605283, 0.425705, -0.529407, 0.397235, 0.428362, -0.667639, -0.575691, -0.201403, -0.094113, -1.041557, 0.074900, -0.057000, -0.186813, 0.802223, -0.792138],
  [-0.169951, 0.177320, 0.187231, 0.182245, -0.020823, -0.040330, 0.068759, -0.062626, -0.239455, -0.115023, 0.069360, 0.001581, -0.151701, 0.057098, 0.121142, -0.038202]
]
B1 = [-0.103147, -0.179799, 0.235186, 0.303573, 0.055328, 0.258825, 0.170623, 0.350530, -0.223219, -0.245579, 0.069463, -0.026183, -0.112913, -0.009116, -0.218366, 0.355398]
W2 = [[-0.581072, 0.426290], [0.057667, 0.765215], [-0.253485, 0.757576], [0.497511, -0.597305], [-0.727013, 0.628422], [-0.086437, 0.533692], [-0.198910, -0.838062], [0.272927, -0.631084], [0.702924, -0.230831], [0.447056, -0.067041], [-0.786047, -0.775605], [0.624468, -0.028861], [0.764573, -0.091280], [-0.834101, 0.028377], [0.166062, 0.657976], [0.060482, -0.581994]]
B2 = [0.004370, 0.191009]

model = GatewayMLP(W1, B1, W2, B2, X_MEAN, X_STD, Y_MEAN, Y_STD)

# =========================================================
# 2. MQTT 클라이언트 (수신 데이터는 MQTT로만 전달, DB/CSV는 구독자에서 처리)
# =========================================================
def _mqtt_publish(client, payload_dict):
    try:
        client.publish(MQTT_TOPIC_READINGS, json.dumps(payload_dict), qos=0)
    except Exception as e:
        try:
            client.reconnect()
            client.publish(MQTT_TOPIC_READINGS, json.dumps(payload_dict), qos=0)
        except Exception as e2:
            print(f"   MQTT publish error: {e2}")

mqtt_client = mqtt.Client()
try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print(f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
except Exception as e:
    print(f"MQTT connect warning: {e} (계속 실행, 나중에 publish 시도)")

# =========================================================
# 3. 시스템 초기화
# =========================================================
try:
    ser = serial.Serial('/dev/tty.usbserial-3', 115200, timeout=1)
    ser.flush()
except Exception:
    print("Error: Serial Port not found. Check connections.")
    exit()

print("=== Gateway (Las Vegas Time / 3-16-2 Model) Started ===")
LV_TIMEZONE = timezone(timedelta(hours=-8))
print("=== Logging via MQTT topic:", MQTT_TOPIC_READINGS, "===")

# 누적 전송 횟수 카운터
total_tx_count = 0
last_est_log_time = time.time()

try:
    while True:
        now_lv = datetime.now(LV_TIMEZONE)
        time_n = ((now_lv.hour * 3600) + (now_lv.minute * 60) + now_lv.second) / 86400.0
        
        # 1. 모델 예측 (현재 상태)
        pred = model.predict(model.last_pred_t, model.last_pred_h, time_n)
        
        # 2. 60초마다 게이트웨이 자체 예측값(EST) MQTT 발행
        if time.time() - last_est_log_time >= 60:
            _mqtt_publish(mqtt_client, {
                "event": "EST",
                "timestamp": now_lv.strftime("%Y-%m-%d %H:%M:%S"),
                "time_n": round(time_n, 4),
                "actual_t": None,
                "actual_h": None,
                "pred_t": round(pred[0], 2),
                "pred_h": round(pred[1], 2),
                "error_t": None,
                "error_h": None,
                "total_tx": total_tx_count,
            })
            last_est_log_time = time.time()

        # 3. 데이터 수신 처리 (RX)
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if "Received:" in line:
                try:
                    payload = line.split("Received: ")[1]
                    parts = payload.split(",")
                    actual_t = float(parts[0])
                    actual_h = float(parts[1])

                    # (1) Ping (0.0, 0.0) 필터링
                    if actual_t == 0.0 and actual_h == 0.0:
                        print(f"[{now_lv.strftime('%H:%M:%S')}] Sync Ping - Only Time Sent")
                        ser.write(f"{int(time.time())}\n".encode())
                        continue

                    # (2) 실제 데이터 수신 (전송 횟수 증가!)
                    total_tx_count += 1
                    err_t = abs(actual_t - pred[0])
                    err_h = abs(actual_h - pred[1])

                    print(f"\n[{now_lv.strftime('%H:%M:%S')}] Data RX! (TX Count: {total_tx_count})")
                    print(f"   Actual: {actual_t:.2f}C / {actual_h:.2f}% | Pred: {pred[0]:.2f}C / {pred[1]:.2f}%")

                    # MQTT로 한 번만 발행 (DB/CSV는 구독자 mqtt_to_mysql, mqtt_to_csv에서 처리)
                    _mqtt_publish(mqtt_client, {
                        "event": "RX",
                        "timestamp": now_lv.strftime("%Y-%m-%d %H:%M:%S"),
                        "time_n": round(time_n, 4),
                        "actual_t": round(actual_t, 2),
                        "actual_h": round(actual_h, 2),
                        "pred_t": round(pred[0], 2),
                        "pred_h": round(pred[1], 2),
                        "error_t": round(err_t, 2),
                        "error_h": round(err_h, 2),
                        "total_tx": total_tx_count,
                    })

                    # (3) 모델 동기화 및 학습
                    # *** 비교군(Offline TinyML) 실험 시에는 아래 한 줄을 주석 처리(#) 하세요! ***
                    print(f"\n[{now_lv.strftime('%H:%M:%S')}] Data RX")
                    print(f"   Actual: {actual_t:.2f}C / {actual_h:.2f}%")
                    print(f"   MyEst : {pred[0]:.2f}C / {pred[1]:.2f}%")

                    # 온라인 학습 (가중치 동기화)
                    model.online_update(actual_t, actual_h, lr=0.05)
                    
                    # 상태 강제 갱신 및 시간 응답 (ACK)
                    model.last_pred_t = actual_t
                    model.last_pred_h = actual_h
                    ser.write(f"{int(time.time())}\n".encode())

                    # 데이터 받았으므로 EST 로깅 타이머 리셋
                    last_est_log_time = time.time()

                except Exception as e:
                    print(f"Error parsing: {e}")

        time.sleep(1)

except KeyboardInterrupt:
    print(f"\nGateway Stopped. Total TX: {total_tx_count}")
    ser.close()