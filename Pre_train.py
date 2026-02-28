import pandas as pd
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import os

FILE_NAME = './dataset/Pre_train_Dataset.csv'
COL_TIME = 'timestamp'
COL_TEMP = 'temperature'
COL_HUM = 'humidity'

WINDOW_SIZE = 4
N_FEATURES = 3   # temp, hum, time_n
N_IN = WINDOW_SIZE * N_FEATURES  # 12
H1_SIZE = 64
H2_SIZE = 32


def train_offline_mlp(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    df = pd.read_csv(file_path)
    df = df.dropna()

    df[COL_TIME] = pd.to_datetime(df[COL_TIME].str.replace('T', ' '))
    df['time_n'] = (df[COL_TIME].dt.hour * 3600 + df[COL_TIME].dt.minute * 60 + df[COL_TIME].dt.second) / 86400.0

    features = df[[COL_TEMP, COL_HUM, 'time_n']].values

    X, y = [], []
    for i in range(WINDOW_SIZE, len(features)):
        window = features[i - WINDOW_SIZE:i].flatten()
        X.append(window)
        y.append(features[i, :2])

    X = np.array(X)
    y = np.array(y)

    print(f"Dataset: {len(X)} samples, Input dim: {N_IN}, Output dim: 2")

    scaler_X = StandardScaler()
    scaler_y = StandardScaler()
    X_scaled = scaler_X.fit_transform(X)
    y_scaled = scaler_y.fit_transform(y)

    mlp = MLPRegressor(
        hidden_layer_sizes=(H1_SIZE, H2_SIZE),
        activation='relu',
        solver='adam',
        learning_rate_init=0.001,
        max_iter=10000,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=50,
        random_state=42,
    )

    print(f"Training Rolling Window MLP ({N_IN}-{H1_SIZE}-{H2_SIZE}-2, ReLU, window={WINDOW_SIZE})...")
    mlp.fit(X_scaled, y_scaled)
    print(f"Converged at iteration: {mlp.n_iter_}")

    W1 = mlp.coefs_[0]       # 12 x 64
    B1 = mlp.intercepts_[0]  # 64
    W2 = mlp.coefs_[1]       # 64 x 32
    B2 = mlp.intercepts_[1]  # 32
    W3 = mlp.coefs_[2]       # 32 x 2
    B3 = mlp.intercepts_[2]  # 2

    total_params = W1.size + B1.size + W2.size + B2.size + W3.size + B3.size
    print(f"Total parameters: {total_params} ({total_params * 4 / 1024:.1f} KB)")

    # ===================== ESP32 코드 출력 =====================
    print("\n" + "=" * 60)
    print(f"   ESP32 Code for {N_IN}-{H1_SIZE}-{H2_SIZE}-2 ReLU Model")
    print("=" * 60)

    print("// Scalers")
    print(f"float x_mean[{N_IN}] = {{{', '.join([f'{v:.6f}f' for v in scaler_X.mean_])}}};")
    print(f"float x_std[{N_IN}]  = {{{', '.join([f'{v:.6f}f' for v in np.sqrt(scaler_X.var_)])}}};")
    print(f"float y_mean[2] = {{{', '.join([f'{v:.6f}f' for v in scaler_y.mean_])}}};")
    print(f"float y_std[2]  = {{{', '.join([f'{v:.6f}f' for v in np.sqrt(scaler_y.var_)])}}};")

    print(f"\nfloat W1[{N_IN}][{H1_SIZE}] = {{")
    for i in range(N_IN):
        row = ", ".join([f"{val:.6f}f" for val in W1[i]])
        print(f"  {{{row}}}" + ("," if i < N_IN - 1 else ""))
    print("};")

    print(f"\nfloat B1[{H1_SIZE}] = {{")
    for i in range(0, H1_SIZE, 4):
        row = ", ".join([f"{val:.6f}f" for val in B1[i:i + 4]])
        print(f"  {row}" + ("," if i + 4 < H1_SIZE else ""))
    print("};")

    print(f"\nfloat W2[{H1_SIZE}][{H2_SIZE}] = {{")
    for i in range(H1_SIZE):
        row = ", ".join([f"{val:.6f}f" for val in W2[i]])
        print(f"  {{{row}}}" + ("," if i < H1_SIZE - 1 else ""))
    print("};")

    print(f"\nfloat B2[{H2_SIZE}] = {{")
    for i in range(0, H2_SIZE, 4):
        row = ", ".join([f"{val:.6f}f" for val in B2[i:i + 4]])
        print(f"  {row}" + ("," if i + 4 < H2_SIZE else ""))
    print("};")

    print(f"\nfloat W3[{H2_SIZE}][2] = {{")
    for i in range(H2_SIZE):
        row = ", ".join([f"{val:.6f}f" for val in W3[i]])
        print(f"  {{{row}}}" + ("," if i < H2_SIZE - 1 else ""))
    print("};")

    print(f"\nfloat B3[2] = {{{', '.join([f'{val:.6f}f' for val in B3])}}};")

    # ===================== Gateway Python 코드 출력 =====================
    print("\n" + "=" * 60)
    print("   Gateway Python Code")
    print("=" * 60)

    print(f"X_MEAN = {scaler_X.mean_.tolist()}")
    print(f"X_STD  = {np.sqrt(scaler_X.var_).tolist()}")
    print(f"Y_MEAN = {scaler_y.mean_.tolist()}")
    print(f"Y_STD  = {np.sqrt(scaler_y.var_).tolist()}")
    print(f"\nW1 = {W1.tolist()}")
    print(f"B1 = {B1.tolist()}")
    print(f"W2 = {W2.tolist()}")
    print(f"B2 = {B2.tolist()}")
    print(f"W3 = {W3.tolist()}")
    print(f"B3 = {B3.tolist()}")

    # ===================== 정확도 확인 =====================
    y_pred = scaler_y.inverse_transform(mlp.predict(X_scaled))
    r2 = r2_score(y, y_pred)
    mae_t = mean_absolute_error(y[:, 0], y_pred[:, 0])
    mae_h = mean_absolute_error(y[:, 1], y_pred[:, 1])
    print(f"\nModel R2 Score: {r2:.5f}")
    print(f"MAE Temp: {mae_t:.4f}°C, MAE Hum: {mae_h:.4f}%")


if __name__ == "__main__":
    train_offline_mlp(FILE_NAME)
