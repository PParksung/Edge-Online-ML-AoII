#!/usr/bin/env python3
"""
엣지(ESP32)를 USB로 연결한 뒤, 시리얼로 출력되는 매 주기 데이터를 읽어
쉼표 기준으로 파싱한 후 CSV 파일 및/또는 MySQL edge_log 테이블에 저장합니다.

시리얼 한 줄 형식 (10필드):
  actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap

실행:
  python edge_node/edge_serial_logger.py [시리얼포트]
  EDGE_SERIAL_PORT=/dev/ttyUSB0 python edge_node/edge_serial_logger.py
  EDGE_CSV_PATH=./edge_perf_log.csv python edge_node/edge_serial_logger.py /dev/ttyUSB0

옵션:
  환경변수 EDGE_CSV_PATH 가 설정되면 해당 경로에 CSV 추적 (헤더 자동 기록).
  환경변수 EDGE_DB=0 이면 DB 저장 비활성화 (CSV만).
"""
import os
import sys
import time
import csv

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# .env 로드
_env_path = os.path.join(ROOT, ".env")
if os.path.isfile(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _file:
        for _line in _file:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip()
                if _k.startswith("MYSQL_"):
                    os.environ[_k] = _v

import serial
from server.db import init_db, insert_edge_log


CSV_HEADER = [
    "actual_t", "actual_h", "pred_t", "pred_h", "error_t", "error_h",
    "status", "inference_time_us", "free_heap", "total_heap",
]


def ensure_csv_file(csv_path):
    """CSV 파일이 없으면 헤더만 써서 생성."""
    if not csv_path or os.path.exists(csv_path):
        return
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CSV_HEADER)


def append_csv_row(csv_path, row):
    """CSV 파일에 한 줄 추가 (row는 10개 필드 리스트)."""
    if not csv_path:
        return
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def parse_line(line):
    """
    쉼표 기준 파싱. 10필드: actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap
    반환: (actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap) 또는 None
    """
    line = line.strip()
    if not line or "," not in line:
        return None
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 10:
        # 구 형식(7필드) 호환: actual_t, actual_h, pred_t, pred_h, err_t, err_h, status
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
        print("  환경변수: EDGE_SERIAL_PORT, EDGE_CSV_PATH, EDGE_DB=0")
        sys.exit(1)

    csv_path = os.environ.get("EDGE_CSV_PATH")
    use_db = os.environ.get("EDGE_DB", "1").strip().lower() not in ("0", "false", "no")

    if csv_path:
        ensure_csv_file(csv_path)
        print(f"CSV 로그: {csv_path}")

    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"시리얼 열기 실패: {e}")
        sys.exit(1)

    if use_db:
        init_db()
        print("DB(MySQL) edge_log 저장 활성화.")
    else:
        print("DB 저장 비활성화 (EDGE_DB=0).")

    print(f"Edge Serial Logger 시작 (포트: {port}). 10필드 CSV 파싱 → CSV/DB 저장. Ctrl+C 종료.")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                parsed = parse_line(line) if line else None
                if parsed is None:
                    if line and "," in line:
                        print(f"  skip (parse): {line[:70]}...")
                    continue

                (actual_t, actual_h, pred_t, pred_h, error_t, error_h,
                 status, inference_time_us, free_heap, total_heap) = parsed

                # CSV 파일 저장
                row = [actual_t, actual_h, pred_t, pred_h, error_t, error_h,
                       status,
                       inference_time_us if inference_time_us is not None else "",
                       free_heap if free_heap is not None else "",
                       total_heap if total_heap is not None else ""]
                append_csv_row(csv_path, row)

                # DB 저장
                if use_db:
                    triggered = 1 if ("SEND" in status.upper() or "HEARTBEAT" in status.upper()) else 0
                    insert_edge_log(
                        actual_temp=actual_t,
                        actual_humidity=actual_h,
                        pred_temp=pred_t,
                        pred_humidity=pred_h,
                        error_temp=error_t,
                        triggered=triggered,
                        error_humidity=error_h,
                        status=status,
                        inference_time_us=inference_time_us,
                        free_heap=free_heap,
                        total_heap=total_heap,
                    )

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
