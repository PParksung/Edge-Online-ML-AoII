import os
import sys
import serial
import time
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
# 1. 3-16-2 모델 파라미터 (성근님의 최신 값 유지)
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

B1 = [
  -0.103147, -0.179799, 0.235186, 0.303573, 0.055328, 0.258825, 0.170623, 0.350530, 
  -0.223219, -0.245579, 0.069463, -0.026183, -0.112913, -0.009116, -0.218366, 0.355398
]

W2 = [
  [-0.581072, 0.426290], [0.057667, 0.765215], [-0.253485, 0.757576], [0.497511, -0.597305],
  [-0.727013, 0.628422], [-0.086437, 0.533692], [-0.198910, -0.838062], [0.272927, -0.631084],
  [0.702924, -0.230831], [0.447056, -0.067041], [-0.786047, -0.775605], [0.624468, -0.028861],
  [0.764573, -0.091280], [-0.834101, 0.028377], [0.166062, 0.657976], [0.060482, -0.581994]
]

B2 = [0.004370, 0.191009]

# =========================================================

# 모델 초기화
model = GatewayMLP(W1, B1, W2, B2, X_MEAN, X_STD, Y_MEAN, Y_STD)

# 시리얼 설정 (포트 확인 필수)
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

try:
    while True:
        # -----------------------------------------------------
        # 1. 라스베이거스 기준 시간 계산 (정확도 핵심)
        # -----------------------------------------------------
        now_lv = datetime.now(LV_TIMEZONE)
        
        # 자정으로부터 지난 초 계산
        seconds_from_midnight = (now_lv.hour * 3600) + (now_lv.minute * 60) + now_lv.second
        
        # 정규화 (0.0 ~ 1.0)
        time_n = seconds_from_midnight / 86400.0
        
        # 게이트웨이 자체 예측 (엣지가 조용할 때)
        pred = model.predict(model.last_pred_t, model.last_pred_h, time_n)
        
        # -----------------------------------------------------
        # 2. 데이터 수신 및 동기화
        # -----------------------------------------------------
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if "Received:" in line:
                try:
                    payload = line.split("Received: ")[1]
                    parts = payload.split(",")
                    actual_t = float(parts[0])
                    actual_h = float(parts[1])
                    if actual_t == 0.0 and actual_h == 0.0:
                        print(f"\n[{now_lv.strftime('%H:%M:%S')}] Sync Request (Ping) Received!")
                        
                        # 1. 학습(online_update)은 절대 하지 않음! (SKIP)
                        
                        # 2. 시간만 즉시 전송
                        utc_now = int(time.time())
                        ser.write(f"{utc_now}\n".encode())
                        print(f"   -> Only Time Sent (UTC: {utc_now})")
                        
                        continue # 루프의 처음으로 돌아감 (아래 코드 실행 X)
                    
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
                    
                    # 모델 상태 강제 동기화
                    model.last_pred_t = actual_t
                    model.last_pred_h = actual_h
                    
                    # 시간 동기화용 패킷 전송 (ESP32에게는 UTC 타임스탬프를 줍니다)
                    # ESP32 코드 내부에서 -28800(UTC-8)을 계산하므로 여기선 UTC를 줘야 함
                    utc_now = int(time.time())
                    ser.write(f"{utc_now}\n".encode())
                    print(f"   -> Sync Sent (UTC: {utc_now})")
                    
                except Exception as e:
                    print(f"Error parsing: {e}")

        time.sleep(1)

except KeyboardInterrupt:
    print("\nGateway Stopped.")
    ser.close()