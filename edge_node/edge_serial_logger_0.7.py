#!/usr/bin/env python3
"""
엣지(ESP32)를 USB로 연결한 뒤, 시리얼로 출력되는 매 주기 데이터를 읽어
쉼표 기준으로 파싱한 후 CSV 파일에 저장합니다.
"""
import os
import sys
import time
import csv
import serial
from datetime import datetime, timezone, timedelta

# ==========================================
# 1. 설정 (이곳에 포트 번호와 CSV 경로를 직접 적어주세요!)
# ==========================================
SERIAL_PORT = "/dev/tty.usbserial-3"  # 파이/맥: "/dev/ttyUSB0" 또는 "/dev/ttyACM0" | 윈도우: "COM3"
CSV_FILE_PATH = "./edge_log_0.7.csv"  # 저장할 CSV 파일 이름 (원하는 경로로 수정)

# ==========================================

LV_TIMEZONE = timezone(timedelta(hours=-8))

CSV_HEADER = [
    "timestamp",
    "actual_t", "actual_h", "pred_t", "pred_h", "error_t", "error_h",
    "status", "inference_time_us", "free_heap", "total_heap",
]


def ensure_csv_file(csv_path):
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADER)


def append_csv_row(csv_path, row):
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
    ensure_csv_file(CSV_FILE_PATH)
    print(f"CSV 로그 저장 경로: {CSV_FILE_PATH}")

    try:
        ser = serial.Serial(SERIAL_PORT, 115200, timeout=1)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"❌ 시리얼 포트({SERIAL_PORT}) 열기 실패: {e}")
        print("포트 번호가 맞는지, 권한이 있는지 확인해주세요.")
        sys.exit(1)

    print(f"✅ Edge Serial Logger 시작 (포트: {SERIAL_PORT}). 종료하려면 Ctrl+C를 누르세요.")

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
                        print(f"  skip (parse fail): {line[:70]}...")
                    continue

                (actual_t, actual_h, pred_t, pred_h, error_t, error_h,
                 status, inference_time_us, free_heap, total_heap) = parsed

                now_lv = datetime.now(LV_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

                row = [
                    now_lv, actual_t, actual_h, pred_t, pred_h, error_t, error_h, status,
                    inference_time_us if inference_time_us is not None else "",
                    free_heap if free_heap is not None else "",
                    total_heap if total_heap is not None else ""
                ]

                append_csv_row(CSV_FILE_PATH, row)

                inf_str = f"{inference_time_us}µs" if inference_time_us is not None else "-"
                mem_str = f"{free_heap}/{total_heap}" if (free_heap is not None and total_heap is not None) else "-"
                print(f"  [{status}] T={actual_t:.2f} H={actual_h:.2f} | {inf_str} | heap {mem_str}")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 로깅 종료.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()