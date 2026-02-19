import sys
import serial
import time
import csv
import os
from datetime import datetime, timezone, timedelta
from gateway_MLP_Logic import GatewayMLP

# 프로젝트 루트를 path에 추가 (server.db import용)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# MySQL 설정: .env 또는 server/mysql_example.env 에서 MYSQL_* 환경 변수 로드 (IDE에서 실행해도 비밀번호 적용)
for _env_file in (os.path.join(_project_root, ".env"), os.path.join(_project_root, "server", "mysql_example.env")):
    if os.path.isfile(_env_file):
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip()
                    if _k.startswith("MYSQL_"):
                        os.environ[_k] = _v
        break

from server.db import init_db, insert_reading

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
# 2. CSV 로깅 설정
# =========================================================
# 실험 모드에 따라 파일 이름을 바꿔주세요!
# 예: "log_online_ml.csv", "log_offline_tinyml.csv"
CSV_FILENAME = "experiment_log_online.csv"

# 파일이 없으면 헤더 생성
if not os.path.exists(CSV_FILENAME):
    with open(CSV_FILENAME, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Time_n", "Event", "Actual_T", "Actual_H", "Pred_T", "Pred_H", "Error_T", "Error_H", "Total_TX"])

# =========================================================
# 3. 시스템 초기화
# =========================================================
try:
    ser = serial.Serial('/dev/tty.usbserial-3', 115200, timeout=1)
    ser.flush()
except:
    print("Error: Serial Port not found. Check connections.")
    exit()

print("=== Gateway (Las Vegas Time / 3-16-2 Model) Started ===")

# MySQL 테이블 생성 (readings)
try:
    init_db()
    print("DB (MySQL) init OK.")
except Exception as e:
    print(f"DB init warning: {e} (계속 실행)")

# 라스베이거스 시간대 설정 (UTC-8)
LV_TIMEZONE = timezone(timedelta(hours=-8))
print(f"=== Gateway Started. Logging to '{CSV_FILENAME}' ===")

# 누적 전송 횟수 카운터
total_tx_count = 0
last_est_log_time = time.time()

try:
    while True:
        now_lv = datetime.now(LV_TIMEZONE)
        time_n = ((now_lv.hour * 3600) + (now_lv.minute * 60) + now_lv.second) / 86400.0
        
        # 1. 모델 예측 (현재 상태)
        pred = model.predict(model.last_pred_t, model.last_pred_h, time_n)
        
        # 2. 60초마다 게이트웨이 자체 예측값(EST) 로그 기록
        # (엣지가 조용할 때 게이트웨이가 혼자 어떻게 예측하고 있는지 확인용)
        if time.time() - last_est_log_time >= 60:
            with open(CSV_FILENAME, mode='a', newline='') as f:
                writer = csv.writer(f)
                # 실제값과 오차는 모르므로 빈칸 처리
                writer.writerow([now_lv.strftime('%Y-%m-%d %H:%M:%S'), f"{time_n:.4f}", "EST", "", "", f"{pred[0]:.2f}", f"{pred[1]:.2f}", "", "", total_tx_count])
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
                    
                    # CSV 기록 (RX 이벤트)
                    with open(CSV_FILENAME, mode='a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([now_lv.strftime('%Y-%m-%d %H:%M:%S'), f"{time_n:.4f}", "RX", f"{actual_t:.2f}", f"{actual_h:.2f}", f"{pred[0]:.2f}", f"{pred[1]:.2f}", f"{err_t:.2f}", f"{err_h:.2f}", total_tx_count])

                    # (3) 모델 동기화 및 학습
                    # *** 비교군(Offline TinyML) 실험 시에는 아래 한 줄을 주석 처리(#) 하세요! ***
                    print(f"\n[{now_lv.strftime('%H:%M:%S')}] Data RX")
                    print(f"   Actual: {actual_t:.2f}C / {actual_h:.2f}%")
                    print(f"   MyEst : {pred[0]:.2f}C / {pred[1]:.2f}%")

                    # MySQL 저장 (모니터링/AoII 분석용)
                    try:
                        insert_reading(actual_t, actual_h, pred[0], pred[1])
                    except Exception as e:
                        print(f"   DB save error: {e}")

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