import serial
import time
import csv
import os
from datetime import datetime

# ==========================================
# 1. 설정 (포트와 파일명)
# ==========================================
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/tty.usbserial-3")
BAUD_RATE = 115200
CSV_FILENAME = 'raw_24h_dataset.csv'

# ==========================================
# 2. CSV 헤더 초기화
# ==========================================
if not os.path.exists(CSV_FILENAME):
    with open(CSV_FILENAME, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Time_n", "Temperature", "Humidity"])

# ==========================================
# 3. 시리얼 연결 및 수집 루프
# ==========================================
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    ser.flush()
    print(f"✅ Serial Connected: {SERIAL_PORT}")
    print(f"✅ Logging data to '{CSV_FILENAME}' (Press Ctrl+C to stop)")
except Exception as e:
    print(f"❌ Serial Port Error: {e}")
    exit()

try:
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            # ESP32에서 "20.5,45.2" 형태로 데이터가 온다고 가정
            if "," in line:
                try:
                    parts = line.split(",")
                    cur_t = float(parts[0])
                    cur_h = float(parts[1])
                    
                    # 현재 라스베이거스 시간 및 time_n 계산
                    now = datetime.now()
                    time_n = ((now.hour * 3600) + (now.minute * 60) + now.second) / 86400.0
                    timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

                    # CSV 파일에 한 줄 쓰기
                    with open(CSV_FILENAME, mode='a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([timestamp_str, f"{time_n:.4f}", f"{cur_t:.2f}", f"{cur_h:.2f}"])
                    
                    print(f"[{timestamp_str}] Logged -> Temp: {cur_t:.2f}C, Hum: {cur_h:.2f}%")
                    
                except ValueError:
                    # 숫자가 아닌 이상한 문자열이 들어오면 무시
                    pass
        
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n🛑 Data Logging Stopped.")
    ser.close()