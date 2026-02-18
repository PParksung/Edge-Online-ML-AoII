import pandas as pd
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import os

# 데이터셋 경로 설정 (성근님 환경에 맞게 수정)
FILE_NAME = './dataset/Pre_train_Dataset.csv'
COL_TIME = 'timestamp'
COL_TEMP = 'temperature'
COL_HUM = 'humidity'

def train_offline_mlp_16(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    df = pd.read_csv(file_path)
    df = df.dropna()

    # 시간 피처 변환 (라스베이거스 패턴 학습용)
    df[COL_TIME] = pd.to_datetime(df[COL_TIME].str.replace('T', ' '))
    df['time_n'] = (df[COL_TIME].dt.hour * 3600 + df[COL_TIME].dt.minute * 60 + df[COL_TIME].dt.second) / 86400.0

    # Input: [Temp, Hum, Time] -> Output: [Next_Temp, Next_Hum]
    X = df[[COL_TEMP, COL_HUM, 'time_n']].values[:-1]
    y = df[[COL_TEMP, COL_HUM]].values[1:]

    # 스케일링 (필수)
    scaler_X = StandardScaler()
    scaler_y = StandardScaler()
    X_scaled = scaler_X.fit_transform(X)
    y_scaled = scaler_y.fit_transform(y)

    # ==========================================================
    # 핵심 변경: 은닉층 뉴런 개수 16개로 증가 (3-16-2 구조)
    # ==========================================================
    HIDDEN_SIZE = 16
    mlp = MLPRegressor(hidden_layer_sizes=(HIDDEN_SIZE,), activation='logistic', 
                       solver='adam', max_iter=5000, random_state=42)
    
    print(f"Training Scaled MLP (3-{HIDDEN_SIZE}-2 structure)...")
    mlp.fit(X_scaled, y_scaled)

    # 가중치 추출
    W1 = mlp.coefs_[0]      # 3 x 16
    B1 = mlp.intercepts_[0] # 16
    W2 = mlp.coefs_[1]      # 16 x 2
    B2 = mlp.intercepts_[1] # 2

    print("\n" + "="*50)
    print(f"   ESP32 Code for 3-{HIDDEN_SIZE}-2 Model")
    print("="*50)
    
    print("// Scalers")
    print(f"float x_mean[3] = {{{', '.join([f'{v:.6f}f' for v in scaler_X.mean_])}}};")
    print(f"float x_std[3] = {{{', '.join([f'{v:.6f}f' for v in np.sqrt(scaler_X.var_)])}}};")
    print(f"float y_mean[2] = {{{', '.join([f'{v:.6f}f' for v in scaler_y.mean_])}}};")
    print(f"float y_std[2] = {{{', '.join([f'{v:.6f}f' for v in np.sqrt(scaler_y.var_)])}}};")

    print(f"\n// Weights (Hidden Nodes: {HIDDEN_SIZE})")
    
    # W1 (3x16)
    print(f"float W1[3][{HIDDEN_SIZE}] = {{")
    for i in range(3):
        row = ", ".join([f"{val:.6f}f" for val in W1[i]])
        print(f"  {{{row}}}" + ("," if i < 2 else ""))
    print("};")

    # B1 (16)
    print(f"\nfloat B1[{HIDDEN_SIZE}] = {{")
    for i in range(0, HIDDEN_SIZE, 4): # 가독성을 위해 4개씩 끊어서 출력
        row = ", ".join([f"{val:.6f}f" for val in B1[i:i+4]])
        print(f"  {row}" + ("," if i < HIDDEN_SIZE-4 else ""))
    print("};")

    # W2 (16x2)
    print(f"\nfloat W2[{HIDDEN_SIZE}][2] = {{")
    for i in range(HIDDEN_SIZE):
        row = ", ".join([f"{val:.6f}f" for val in W2[i]])
        print(f"  {{{row}}}" + ("," if i < HIDDEN_SIZE-1 else ""))
    print("};")

    # B2 (2)
    print(f"\nfloat B2[2] = {{{', '.join([f'{val:.6f}f' for val in B2])}}};")

    # 정확도 확인
    y_pred = scaler_y.inverse_transform(mlp.predict(X_scaled))
    r2 = r2_score(y, y_pred)
    print(f"\nModel R2 Score: {r2:.5f} (Higher is better)")

if __name__ == "__main__":
    train_offline_mlp_16(FILE_NAME)