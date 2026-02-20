# server/mqtt_to_mysql.py
"""MQTT 구독: aoii/readings 수신 시 RX 이벤트만 MySQL readings 테이블에 저장."""
import os
import sys
import json

# 프로젝트 루트 추가 (db import 및 .env 로드)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

# .env / mysql_example.env 에서 MYSQL_* 로드
for _env_file in (os.path.join(_project_root, ".env"), os.path.join(_project_root, "server", "mysql_example.env")):
    if os.path.isfile(_env_file):
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip()
                    if _k.startswith("MYSQL_") or _k.startswith("MQTT_"):
                        os.environ[_k] = _v
        break

import paho.mqtt.client as mqtt
from server.db import init_db, insert_reading

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = "aoii/readings"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("mqtt_to_mysql: MQTT connected.")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"mqtt_to_mysql: MQTT connect failed rc={rc}")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        if data.get("event") != "RX":
            return
        actual_t = float(data["actual_t"])
        actual_h = float(data["actual_h"])
        pred_t = float(data["pred_t"])
        pred_h = float(data["pred_h"])
        insert_reading(actual_t, actual_h, pred_t, pred_h)
        print(f"mqtt_to_mysql: saved 1 reading (T={actual_t:.2f}, H={actual_h:.2f})")
    except Exception as e:
        print(f"mqtt_to_mysql: on_message error: {e}")


def main():
    try:
        init_db()
        print("DB (MySQL) init OK.")
    except Exception as e:
        print(f"DB init warning: {e}")

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
