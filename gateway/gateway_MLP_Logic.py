import numpy as np

class GatewayMLP:
    def __init__(self, w1, b1, w2, b2, x_mean, x_std, y_mean, y_std):
        # 데이터 타입 명시 (ESP32 float32와 일치)
        self.w1 = np.array(w1, dtype=np.float32)
        self.b1 = np.array(b1, dtype=np.float32)
        self.w2 = np.array(w2, dtype=np.float32)
        self.b2 = np.array(b2, dtype=np.float32)
        
        self.x_mean = np.array(x_mean, dtype=np.float32)
        self.x_std = np.array(x_std, dtype=np.float32)
        self.y_mean = np.array(y_mean, dtype=np.float32)
        self.y_std = np.array(y_std, dtype=np.float32)
        
        # 역전파용 상태 저장
        self.last_in_scaled = np.zeros(3)
        self.last_hidden = np.zeros(16) # 16개로 자동 확장됨
        
        # 초기 예측값
        self.last_pred_t = y_mean[0]
        self.last_pred_h = y_mean[1]

    def sigmoid(self, x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))

    def d_sigmoid(self, x):
        return x * (1.0 - x)

    def predict(self, temp, hum, time_n):
        self.last_in_scaled = (np.array([temp, hum, time_n]) - self.x_mean) / self.x_std
        
        # Input -> Hidden (자동으로 16개 뉴런 계산)
        hidden_input = np.dot(self.last_in_scaled, self.w1) + self.b1
        self.last_hidden = self.sigmoid(hidden_input)
        
        # Hidden -> Output
        out_scaled = np.dot(self.last_hidden, self.w2) + self.b2
        
        final_pred = (out_scaled * self.y_std) + self.y_mean
        self.last_pred_t, self.last_pred_h = final_pred[0], final_pred[1]
        return final_pred

    def online_update(self, actual_t, actual_h, lr=0.05):
        # 타겟 스케일링
        target_scaled = (np.array([actual_t, actual_h]) - self.y_mean) / self.y_std
        
        # 오차 계산
        current_pred_scaled = np.dot(self.last_hidden, self.w2) + self.b2
        out_error = target_scaled - current_pred_scaled
        
        # --- 역전파 (Backpropagation) ---
        
        # Output Layer (W2, B2) 업데이트
        # delta_w2는 (16, 2) 크기가 됨
        delta_w2 = lr * np.outer(self.last_hidden, out_error)
        self.w2 += delta_w2
        self.b2 += lr * out_error

        # Hidden Layer 오차 전파
        # hidden_error는 (16,) 크기가 됨
        hidden_error = np.dot(out_error, self.w2.T) 
        delta_hidden = hidden_error * self.d_sigmoid(self.last_hidden)

        # Hidden Layer (W1, B1) 업데이트
        # delta_w1은 (3, 16) 크기가 됨
        delta_w1 = lr * np.outer(self.last_in_scaled, delta_hidden)
        self.w1 += delta_w1
        self.b1 += lr * delta_hidden
        
        print(f"[Sync] Weights Updated (LR={lr})")