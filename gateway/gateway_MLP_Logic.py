import numpy as np

WINDOW_SIZE = 4
N_FEATURES = 3  # temp, hum, time_n


class GatewayMLP:
    """12-64-32-2 Rolling Window MLP (ReLU, 2 hidden layers)."""

    def __init__(self, w1, b1, w2, b2, w3, b3, x_mean, x_std, y_mean, y_std):
        self.w1 = np.array(w1, dtype=np.float32)  # 12 x 64
        self.b1 = np.array(b1, dtype=np.float32)   # 64
        self.w2 = np.array(w2, dtype=np.float32)  # 64 x 32
        self.b2 = np.array(b2, dtype=np.float32)   # 32
        self.w3 = np.array(w3, dtype=np.float32)  # 32 x 2
        self.b3 = np.array(b3, dtype=np.float32)   # 2

        self.x_mean = np.array(x_mean, dtype=np.float32)
        self.x_std = np.array(x_std, dtype=np.float32)
        self.y_mean = np.array(y_mean, dtype=np.float32)
        self.y_std = np.array(y_std, dtype=np.float32)

        self.window_buf = np.zeros((WINDOW_SIZE, N_FEATURES), dtype=np.float32)
        for w in range(WINDOW_SIZE):
            self.window_buf[w] = [y_mean[0], y_mean[1], 0.5]

        self.last_in_scaled = np.zeros(WINDOW_SIZE * N_FEATURES, dtype=np.float32)
        self.last_hidden1 = np.zeros(self.w1.shape[1], dtype=np.float32)
        self.last_hidden2 = np.zeros(self.w2.shape[1], dtype=np.float32)
        # backprop에서 ReLU 미분을 위해 pre-activation 값 저장
        self.last_pre_h1 = np.zeros(self.w1.shape[1], dtype=np.float32)
        self.last_pre_h2 = np.zeros(self.w2.shape[1], dtype=np.float32)

        self.last_pred_t = y_mean[0]
        self.last_pred_h = y_mean[1]

    @staticmethod
    def relu(x):
        return np.maximum(0, x)

    def predict(self):
        flat_input = self.window_buf.flatten()
        self.last_in_scaled = (flat_input - self.x_mean) / self.x_std

        self.last_pre_h1 = np.dot(self.last_in_scaled, self.w1) + self.b1
        self.last_hidden1 = self.relu(self.last_pre_h1)

        self.last_pre_h2 = np.dot(self.last_hidden1, self.w2) + self.b2
        self.last_hidden2 = self.relu(self.last_pre_h2)

        out_scaled = np.dot(self.last_hidden2, self.w3) + self.b3
        final_pred = (out_scaled * self.y_std) + self.y_mean

        self.last_pred_t, self.last_pred_h = float(final_pred[0]), float(final_pred[1])
        return final_pred

    def shift_window(self, new_t, new_h, new_tn):
        self.window_buf[:-1] = self.window_buf[1:]
        self.window_buf[-1] = [new_t, new_h, new_tn]

    def online_update(self, actual_t, actual_h, lr=0.05):
        target_scaled = (np.array([actual_t, actual_h]) - self.y_mean) / self.y_std
        current_pred_scaled = np.dot(self.last_hidden2, self.w3) + self.b3
        out_error = target_scaled - current_pred_scaled

        # --- Output layer (W3, B3) ---
        delta_w3 = lr * np.outer(self.last_hidden2, out_error)
        self.w3 += delta_w3
        self.b3 += lr * out_error

        # --- Hidden Layer 2 (W2, B2) — ReLU derivative ---
        d_relu_h2 = (self.last_pre_h2 > 0).astype(np.float32)
        h2_error = np.dot(out_error, self.w3.T) * d_relu_h2
        delta_w2 = lr * np.outer(self.last_hidden1, h2_error)
        self.w2 += delta_w2
        self.b2 += lr * h2_error

        # --- Hidden Layer 1 (W1, B1) — ReLU derivative ---
        d_relu_h1 = (self.last_pre_h1 > 0).astype(np.float32)
        h1_error = np.dot(h2_error, self.w2.T) * d_relu_h1
        delta_w1 = lr * np.outer(self.last_in_scaled, h1_error)
        self.w1 += delta_w1
        self.b1 += lr * h1_error

        print(f"[Sync] Weights Updated (LR={lr})")
