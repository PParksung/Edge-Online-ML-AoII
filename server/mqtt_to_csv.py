# server/mqtt_to_csv.py
"""MQTT 구독: aoii/readings 수신 시 RX/EST 모두 experiment_log_online.csv에 한 줄씩 추가."""
import os
import sys
import csv
import json

# 프로젝트 루트 (실행 위치를 루트로 맞추고 CSV는 루트에 생성)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

for _env_file in (os.path.join(_project_root, ".env"), os.path.join(_project_root, "server", "mysql_example.env")):
    if os.path.isfile(_env_file):
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip()
                    if _k.startswith("MQTT_"):
                        os.environ[_k] = _v
        break

import paho.mqtt.client as mqtt

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = "aoii/readings"
CSV_FILENAME = "experiment_log_online.csv"

# CSV 헤더 (기존 gateway와 동일)
HEADER = ["Timestamp", "Time_n", "Event", "Actual_T", "Actual_H", "Pred_T", "Pred_H", "Error_T", "Error_H", "Total_TX"]


def ensure_csv():
    if not os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode="w", newline="") as f:
            csv.writer(f).writerow(HEADER)


def row_from_payload(data):
    def v(key, default=""):
        x = data.get(key)
        return f"{x:.2f}" if isinstance(x, (int, float)) else (x if x is not None else default)

    return [
        data.get("timestamp", ""),
        str(data.get("time_n", "")),
        data.get("event", ""),
        v("actual_t"),
        v("actual_h"),
        v("pred_t"),
        v("pred_h"),
        v("error_t"),
        v("error_h"),
        data.get("total_tx", ""),
    ]


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("mqtt_to_csv: MQTT connected.")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"mqtt_to_csv: MQTT connect failed rc={rc}")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        ensure_csv()
        with open(CSV_FILENAME, mode="a", newline="") as f:
            csv.writer(f).writerow(row_from_payload(data))
        print(f"mqtt_to_csv: appended 1 row (event={data.get('event')})")
    except Exception as e:
        print(f"mqtt_to_csv: on_message error: {e}")


def main():
    ensure_csv()
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"MQTT connect error: {e}")
        sys.exit(1)
    client.loop_forever()


if __name__ == "__main__":
    main()
