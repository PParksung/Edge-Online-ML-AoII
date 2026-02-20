import serial
import time
import csv
import os
from datetime import datetime

# ==========================================
# 1. 환경 설정 (임계값 전용)
# ==========================================
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/tty.usbserial-3")
BAUD_RATE = 115200
CSV_FILENAME = "experiment_log_threshold.csv"

BETA_TEMP = 0.5
BETA_HUM = 3.0
HEARTBEAT_MINS = 10

# ==========================================
# 2. CSV 헤더 초기화
# ==========================================
if not os.path.exists(CSV_FILENAME):
    with open(CSV_FILENAME, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Time_n", "Event", "Actual_T", "Actual_H", "Pred_T", "Pred_H", "Error_T", "Error_H", "Total_TX"])

# ==========================================
# 3. 상태 변수
# ==========================================
pred_t = -100.0  
pred_h = -100.0  
total_tx = 0
minute_counter = 0

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    ser.flush()
    print(f"✅ [THRESHOLD MODE] Serial Connected: {SERIAL_PORT}")
    print(f"✅ Logging to: {CSV_FILENAME}")
except Exception as e:
    print(f"❌ Serial Port Error: {e}")
    exit()

try:
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if "," in line:
                try:
                    parts = line.split(",")
                    cur_t = float(parts[0])
                    cur_h = float(parts[1])
                    
                    now = datetime.now()
                    time_n = ((now.hour * 3600) + (now.minute * 60) + now.second) / 86400.0
                    timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

                    # 초기값 세팅 (최초 1회)
                    if pred_t == -100.0:
                        pred_t, pred_h = cur_t, cur_h

                    # 오차 계산 (마지막 전송값 vs 현재값)
                    err_t = abs(cur_t - pred_t)
                    err_h = abs(cur_h - pred_h)

                    # ESP32에서 1분마다 데이터가 들어오므로 카운터 1 증가
                    minute_counter += 1 

                    # ==========================================
                    # 4. 임계값 전송 조건 판단
                    # ==========================================
                    send_data = False
                    
                    if (err_t > BETA_TEMP) or (err_h > BETA_HUM) or (minute_counter >= HEARTBEAT_MINS):
                        send_data = True

                    # ==========================================
                    # 5. 이벤트 처리 및 기록
                    # ==========================================
                    if send_data:
                        event = "RX"
                        total_tx += 1
                        minute_counter = 0  # 전송했으므로 하트비트 타이머 초기화
                        pred_t, pred_h = cur_t, cur_h  # 기준값 갱신
                        print(f"[{timestamp_str}] 🚀 {event} (TX: {total_tx}) | Err_T: {err_t:.1f}, Err_H: {err_h:.1f}")
                    else:
                        event = "EST"
                        print(f"[{timestamp_str}] 💤 {event} (SKIP) | Err_T: {err_t:.1f}, Err_H: {err_h:.1f}")

                    with open(CSV_FILENAME, mode='a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            timestamp_str, 
                            f"{time_n:.4f}", 
                            event, 
                            f"{cur_t:.2f}", 
                            f"{cur_h:.2f}", 
                            f"{pred_t:.2f}", 
                            f"{pred_h:.2f}", 
                            f"{err_t:.2f}", 
                            f"{err_h:.2f}", 
                            total_tx
                        ])
                    
                except ValueError:
                    pass
        
        time.sleep(0.1)

except KeyboardInterrupt:
    print(f"\n🛑 Logging Stopped. Total TX: {total_tx}")
    ser.close()