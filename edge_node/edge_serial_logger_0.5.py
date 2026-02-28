#!/usr/bin/env python3
import serial
import csv
import time
from datetime import datetime, timezone, timedelta

# ==========================================
# 설정
# ==========================================
SERIAL_PORT = "/dev/tty.usbserial-0001"
BAUD_RATE   = 115200
CSV_PATH    = "./edge_log_0.5.csv"
TIMEZONE    = timezone(timedelta(hours=-8))  # Las Vegas (UTC-8)
# ==========================================

CSV_HEADER = [
    "timestamp",
    "actual_t", "actual_h", "pred_t", "pred_h", "error_t", "error_h",
    "status", "inference_time_us", "free_heap", "total_heap",
]


def ensure_csv_file():
    import os
    if os.path.exists(CSV_PATH):
        return
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CSV_HEADER)


def append_csv_row(row):
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def parse_line(line):
    # ino Serial.println 포맷 (정확히 10 필드):
    # cur_t, cur_h, pred_t, pred_h, err_t, err_h, status,
    # inference_time_us, free_heap, total_heap
    line = line.strip()
    if not line:
        return None
    parts = line.split(",")
    if len(parts) != 10:
        return None
    try:
        actual_t          = float(parts[0])
        actual_h          = float(parts[1])
        pred_t            = float(parts[2])
        pred_h            = float(parts[3])
        error_t           = float(parts[4])
        error_h           = float(parts[5])
        status            = parts[6].strip()
        inference_time_us = int(parts[7])
        free_heap         = int(parts[8])
        total_heap        = int(parts[9])
    except (ValueError, IndexError):
        return None
    return (actual_t, actual_h, pred_t, pred_h,
            error_t, error_h, status,
            inference_time_us, free_heap, total_heap)


def main():
    ensure_csv_file()
    print(f"CSV 로그: {CSV_PATH}")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"시리얼 열기 실패: {e}")
        return

    print(f"Edge Serial Logger 시작 (포트: {SERIAL_PORT}). Ctrl+C 종료.")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                parsed = parse_line(line)
                if parsed is None:
                    if line:
                        print(f"  skip: {line[:80]}")
                    continue

                (actual_t, actual_h, pred_t, pred_h,
                 error_t, error_h, status,
                 inference_time_us, free_heap, total_heap) = parsed

                now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
                row = [now,
                       actual_t, actual_h,
                       pred_t,   pred_h,
                       error_t,  error_h,
                       status,
                       inference_time_us, free_heap, total_heap]
                append_csv_row(row)

                print(f"  [{status}] T={actual_t:.2f} H={actual_h:.2f}"
                      f" | inf={inference_time_us}µs"
                      f" | heap={free_heap}/{total_heap}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n종료.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
