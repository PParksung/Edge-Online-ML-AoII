#!/usr/bin/env python3
"""
엣지(ESP32)를 USB로 연결한 뒤, 시리얼로 출력되는 매 주기 데이터를 읽어
SKIP 포함 전부 MySQL edge_log 테이블에 저장합니다.
실행: python server/edge_serial_logger.py [시리얼포트]
  예: python server/edge_serial_logger.py /dev/tty.usbserial-3
  또는: EDGE_SERIAL_PORT=/dev/ttyUSB0 python server/edge_serial_logger.py
"""
import os
import sys
import time

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# MySQL env 로드 (.env 또는 server/mysql_example.env)
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

import serial
from server.db import init_db, insert_edge_log


def main():
    port = os.environ.get("EDGE_SERIAL_PORT") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not port:
        print("Usage: python server/edge_serial_logger.py <시리얼포트>")
        print("  예: python server/edge_serial_logger.py /dev/tty.usbserial-3")
        print("  또는 환경변수: EDGE_SERIAL_PORT=/dev/ttyUSB0")
        sys.exit(1)

    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"시리얼 열기 실패: {e}")
        sys.exit(1)

    init_db()
    print(f"Edge Serial Logger 시작 (포트: {port}). SKIP 포함 전부 edge_log 테이블에 저장합니다. Ctrl+C 종료.")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                # 형식 (7필드): cur_t, cur_h, pred_t, pred_h, err_t, err_h, status (status는 SKIP / HEARTBEAT / SEND & TRAIN)
                if not line or "," not in line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 7:
                    # 구 형식(5필드) 호환: cur_t, cur_h, pred_t, err_t, status
                    if len(parts) >= 5:
                        try:
                            actual_t = float(parts[0])
                            actual_h = float(parts[1])
                            pred_t = float(parts[2])
                            error_t = float(parts[3])
                            status = parts[4].upper()
                            triggered = 1 if ("SEND" in status or "HEARTBEAT" in status) else 0
                            insert_edge_log(actual_t, actual_h, pred_t, 0.0, error_t, triggered)
                            print(f"  [{status}] T={actual_t:.2f} pred_t={pred_t:.2f} err_t={error_t:.3f} -> edge_log")
                        except (ValueError, IndexError):
                            pass
                    continue
                try:
                    actual_t = float(parts[0])
                    actual_h = float(parts[1])
                    pred_t = float(parts[2])
                    pred_h = float(parts[3])
                    err_t = float(parts[4])
                    err_h = float(parts[5])
                    status = parts[6].upper()
                    triggered = 1 if ("SEND" in status or "HEARTBEAT" in status) else 0
                    insert_edge_log(actual_t, actual_h, pred_t, pred_h, err_t, triggered)
                    print(f"  [{status}] T={actual_t:.2f} H={actual_h:.2f} P_T={pred_t:.2f} P_H={pred_h:.2f} err_t={err_t:.3f} err_h={err_h:.3f} -> edge_log")
                except (ValueError, IndexError) as e:
                    print(f"  skip (parse error): {line[:60]}... -> {e}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n종료.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
