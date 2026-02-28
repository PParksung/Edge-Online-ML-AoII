#!/usr/bin/env python3
"""
엣지(ESP32)를 USB로 연결한 뒤, 시리얼로 출력되는 매 주기 데이터를 읽어
쉼표 기준으로 파싱한 후 CSV 파일에 저장합니다.

시리얼 한 줄 형식 (10필드):
  actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap

실행:
  python edge_node/edge_serial_logger.py [시리얼포트]
  .env에 EDGE_SERIAL_PORT, EDGE_CSV_PATH 설정 후 인자 없이 실행 가능
"""
import os
import sys
import time
import csv
from datetime import datetime, timezone, timedelta

LV_TIMEZONE = timezone(timedelta(hours=-8))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_env_path = os.path.join(ROOT, ".env")
if os.path.isfile(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _file:
        for _line in _file:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip()
                if _k.startswith("EDGE_"):
                    os.environ[_k] = _v

import serial

CSV_HEADER = [
    "timestamp",
    "actual_t", "actual_h", "pred_t", "pred_h", "error_t", "error_h",
    "status", "inference_time_us", "free_heap", "total_heap",
]


def ensure_csv_file(csv_path):
    if not csv_path or os.path.exists(csv_path):
        return
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CSV_HEADER)


def append_csv_row(csv_path, row):
    if not csv_path:
        return
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def parse_line(line):
    line = line.strip()
    if not line or "," not in line:
        return None
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 10:
        if len(parts) >= 7:
            try:
                a_t, a_h = float(parts[0]), float(parts[1])
                p_t, p_h = float(parts[2]), float(parts[3])
                e_t, e_h = float(parts[4]), float(parts[5])
                status = parts[6]
                return (a_t, a_h, p_t, p_h, e_t, e_h, status, None, None, None)
            except (ValueError, IndexError):
                pass
        return None
    try:
        actual_t = float(parts[0])
        actual_h = float(parts[1])
        pred_t = float(parts[2])
        pred_h = float(parts[3])
        error_t = float(parts[4])
        error_h = float(parts[5])
        status = parts[6]
        inference_time_us = int(parts[7]) if parts[7] else None
        free_heap = int(parts[8]) if parts[8] else None
        total_heap = int(parts[9]) if parts[9] else None
        return (actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap)
    except (ValueError, IndexError):
        return None


def main():
    port = os.environ.get("EDGE_SERIAL_PORT") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not port:
        print("Usage: python edge_node/edge_serial_logger.py <시리얼포트>")
        print("  예: python edge_node/edge_serial_logger.py /dev/tty.usbserial-3")
        print("  또는 .env에 EDGE_SERIAL_PORT 설정")
        sys.exit(1)

    csv_path = os.environ.get("EDGE_CSV_PATH", "edge_log_0.5_2.csv")
    ensure_csv_file(csv_path)
    print(f"CSV 로그: {csv_path}")

    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"시리얼 열기 실패: {e}")
        sys.exit(1)

    print(f"Edge Serial Logger 시작 (포트: {port}). Ctrl+C 종료.")

    # 초기 시간 동기화 전송
    ts = int(time.time())
    ser.write(f"TIME:{ts}\n".encode("utf-8"))
    print(f"  [TIME SYNC] 초기 전송: {ts}")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if line == "TIME?":
                    ts = int(time.time())
                    ser.write(f"TIME:{ts}\n".encode("utf-8"))
                    print(f"  [TIME SYNC] 요청 응답: {ts}")
                    continue
                parsed = parse_line(line) if line else None
                if parsed is None:
                    if line and "," in line:
                        print(f"  skip (parse): {line[:70]}...")
                    continue

                (actual_t, actual_h, pred_t, pred_h, error_t, error_h,
                 status, inference_time_us, free_heap, total_heap) = parsed

                now_lv = datetime.now(LV_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
                row = [now_lv, actual_t, actual_h, pred_t, pred_h, error_t, error_h,
                       status,
                       inference_time_us if inference_time_us is not None else "",
                       free_heap if free_heap is not None else "",
                       total_heap if total_heap is not None else ""]
                append_csv_row(csv_path, row)

                inf_str = f"{inference_time_us}µs" if inference_time_us is not None else "-"
                mem_str = f"{free_heap}/{total_heap}" if (free_heap is not None and total_heap is not None) else "-"
                print(f"  [{status}] T={actual_t:.2f} H={actual_h:.2f} | {inf_str} | heap {mem_str}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n종료.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
