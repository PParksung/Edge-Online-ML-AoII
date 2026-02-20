#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include "SSD1306Wire.h"
#include <LoRa.h>
#include <math.h>
#include "esp_sleep.h"

// ==========================================
// 하드웨어 설정 (Heltec V2 / Las Vegas)
// ==========================================
#define SCK     5
#define MISO    19
#define MOSI    27
#define SS      18
#define RST     14
#define DI0     26
#define BAND    433E6

#define OLED_SDA 4
#define OLED_SCL 15
#define OLED_RST 16

SSD1306Wire display(0x3c, OLED_SDA, OLED_SCL);
Adafruit_AHTX0 aht;

// ==========================================
// 3-16-2 MLP 모델 설정 (High Accuracy)
// ==========================================
#define N_IN  3
#define N_HID 16 
#define N_OUT 2

// Scalers & Weights
float x_mean[3] = {11.951440f, 34.796511f, 0.518765f};
float x_std[3]  = {5.192832f, 19.254291f, 0.287677f};
float y_mean[2] = {11.952372f, 34.792687f};
float y_std[2]  = {5.192482f, 19.253258f};

float W1[3][16] = {
  {-0.556351f, 0.189494f, -0.093627f, 0.395785f, -0.577321f, 0.007591f, -0.283381f, 0.373759f, 0.595335f, 0.768831f, -1.089705f, 0.857749f, 0.713353f, -0.719686f, 0.349461f, -0.002144f},
  {0.278056f, 0.605283f, 0.425705f, -0.529407f, 0.397235f, 0.428362f, -0.667639f, -0.575691f, -0.201403f, -0.094113f, -1.041557f, 0.074900f, -0.057000f, -0.186813f, 0.802223f, -0.792138f},
  {-0.169951f, 0.177320f, 0.187231f, 0.182245f, -0.020823f, -0.040330f, 0.068759f, -0.062626f, -0.239455f, -0.115023f, 0.069360f, 0.001581f, -0.151701f, 0.057098f, 0.121142f, -0.038202f}
};

float bias1[16] = {
  -0.103147f, -0.179799f, 0.235186f, 0.303573f, 0.055328f, 0.258825f, 0.170623f, 0.350530f,
  -0.223219f, -0.245579f, 0.069463f, -0.026183f, -0.112913f, -0.009116f, -0.218366f, 0.355398f
};

float W2[16][2] = {
  {-0.581072f, 0.426290f}, {0.057667f, 0.765215f}, {-0.253485f, 0.757576f}, {0.497511f, -0.597305f},
  {-0.727013f, 0.628422f}, {-0.086437f, 0.533692f}, {-0.198910f, -0.838062f}, {0.272927f, -0.631084f},
  {0.702924f, -0.230831f}, {0.447056f, -0.067041f}, {-0.786047f, -0.775605f}, {0.624468f, -0.028861f},
  {0.764573f, -0.091280f}, {-0.834101f, 0.028377f}, {0.166062f, 0.657976f}, {0.060482f, -0.581994f}
};

float B2[2] = {0.004370f, 0.191009f};

float lr = 0.05f;           
float beta_temp = 0.5f;
float beta_hum  = 3.0f;
const float epsilon = 0.001f;  // float 비교 오차 방지 (0.5 "이상" = >= 0.499)

float hidden_layer[N_HID];
float pred_scaled[N_OUT];

unsigned long last_sync_unix = 0;
unsigned long sync_millis = 0;

// [하트비트용 변수 추가]
unsigned long last_send_millis = 0;
const unsigned long HEARTBEAT_INTERVAL = 600000; // 10분 (밀리초)

float sigmoid(float x) { return 1.0f / (1.0f + exp(-constrain(x, -20.0f, 20.0f))); }
float d_sigmoid(float x) { return x * (1.0f - x); } 

void forward(float t, float h, float tn) {
  float in_s[3] = {(t - x_mean[0])/x_std[0], (h - x_mean[1])/x_std[1], (tn - x_mean[2])/x_std[2]};
  for(int j=0; j < N_HID; j++) {
    float sum = bias1[j];
    for(int i=0; i < N_IN; i++) sum += in_s[i] * W1[i][j];
    hidden_layer[j] = sigmoid(sum);
  }
  for(int j=0; j < N_OUT; j++) {
    float sum = B2[j];
    for(int i=0; i < N_HID; i++) sum += hidden_layer[i] * W2[i][j];
    pred_scaled[j] = sum;
  }
}

void update_model(float t, float h, float tn) {
  float target_s[2] = {(t - y_mean[0])/y_std[0], (h - y_mean[1])/y_std[1]};
  float in_s[3]     = {(t - x_mean[0])/x_std[0], (h - x_mean[1])/x_std[1], (tn - x_mean[2])/x_std[2]};
  float out_err[N_OUT];
  for(int i=0; i < N_OUT; i++) out_err[i] = target_s[i] - pred_scaled[i];

  for(int i=0; i < N_OUT; i++) {
    for(int j=0; j < N_HID; j++) W2[j][i] += lr * out_err[i] * hidden_layer[j];
    B2[i] += lr * out_err[i];
  }
  for(int j=0; j < N_HID; j++) {
    float error_sum = 0.0f;
    for(int i=0; i < N_OUT; i++) error_sum += out_err[i] * W2[j][i];
    float delta = error_sum * d_sigmoid(hidden_layer[j]);
    for(int i=0; i < N_IN; i++) W1[i][j] += lr * delta * in_s[i];
    bias1[j] += lr * delta;
  }
}

float get_time_n() {
  if (last_sync_unix == 0) return 0.5f;
  unsigned long current_unix = last_sync_unix + (millis() - sync_millis) / 1000;
  long local_sec = (current_unix - 28800) % 86400; // UTC-8
  if (local_sec < 0) local_sec += 86400;
  return (float)local_sec / 86400.0f;
}

void waitForTimeSync() {
  display.clear();
  display.drawString(0, 0, "Syncing Time...");
  display.display();

  int retries = 0;
  while (last_sync_unix == 0) {
    LoRa.beginPacket();
    LoRa.print("0.0,0.0"); 
    LoRa.endPacket();

    long start = millis();
    bool received = false;
    while (millis() - start < 3000) {
      int p_size = LoRa.parsePacket();
      if (p_size) {
        String income = "";
        while (LoRa.available()) income += (char)LoRa.read();

        if (income.length() > 8) {
           last_sync_unix = income.toInt();
           sync_millis = millis();
           received = true;
           break;
        }
      }
    }

    if (received) {
      display.drawString(0, 20, "Success!");
      display.drawString(0, 40, "TS: " + String(last_sync_unix));
      display.display();
      delay(1000);
      break; 
    } else {
      retries++;
      display.drawString(0, 20, "Retry: " + String(retries));
      display.display();
      delay(1000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(OLED_RST, OUTPUT); digitalWrite(OLED_RST, HIGH);
  Wire.begin(OLED_SDA, OLED_SCL);
  display.init(); display.flipScreenVertically();
  
  if (!aht.begin()) { display.drawString(0,0,"Sensor Error"); display.display(); while(1); }

  SPI.begin(SCK, MISO, MOSI, SS);
  LoRa.setPins(SS, RST, DI0);
  if (!LoRa.begin(BAND)) { display.drawString(0,0,"LoRa Error"); display.display(); while(1); }

  display.drawString(0, 0, "Model: 3-16-2 MLP");
  display.display();
  delay(1000);

  waitForTimeSync();
  last_send_millis = millis(); // 첫 동기화 시점부터 하트비트 타이머 시작
}

void loop() {
  sensors_event_t h_event, t_event;
  aht.getEvent(&h_event, &t_event);
  float cur_t = t_event.temperature;
  float cur_h = h_event.relative_humidity;
  float time_n = get_time_n();

  forward(cur_t, cur_h, time_n);

  float pred_t = (pred_scaled[0] * y_std[0]) + y_mean[0];
  float pred_h = (pred_scaled[1] * y_std[1]) + y_mean[1];

  // float 절댓값은 fabsf() 사용 (abs()는 정수용이라 소수 잘림)
  float err_t = fabsf(cur_t - pred_t);
  float err_h = fabsf(cur_h - pred_h);

  // 하트비트 체크: 10분이 지났는가?
  bool is_heartbeat = (millis() - last_send_millis >= HEARTBEAT_INTERVAL);

  // 전송 조건: 오차가 임계값 이상이거나, 10분 하트비트, 또는 시간 미동기화. "이상" = >= (epsilon 반영)
  bool send_data = (err_t >= beta_temp - epsilon) || (err_h >= beta_hum - epsilon) || (last_sync_unix == 0) || is_heartbeat;

  String status = "SKIP";

  if (send_data) {
    if (is_heartbeat && err_t <= beta_temp && err_h <= beta_hum) {
      status = "HEARTBEAT"; // 오차는 정상인데 10분 돼서 보내는 경우
    } else {
      status = "SEND & TRAIN"; // 오차가 발생해서 보내는 경우
    }
    
    last_send_millis = millis();

    LoRa.beginPacket();
    LoRa.print(String(cur_t) + "," + String(cur_h));
    LoRa.endPacket();

    long start = millis();
    while (millis() - start < 1000) {
      int p_size = LoRa.parsePacket();
      if (p_size) {
        String income = "";
        while (LoRa.available()) income += (char)LoRa.read();
        if (income.length() > 5) {
           last_sync_unix = income.toInt();
           sync_millis = millis();
        }
        break;
      }
    }

    update_model(cur_t, cur_h, time_n);
  }

  display.clear();
  display.drawString(0, 0, "Err T:" + String(err_t, 3) + " H:" + String(err_h, 3));
  display.drawString(0, 15, "P_T:" + String(pred_t, 1) + " P_H:" + String(pred_h, 1));
  display.drawString(0, 30, "R_T:" + String(cur_t, 1) + " R_H:" + String(cur_h, 1));
  display.drawString(0, 45, ">> " + status);
  display.display();

  // USB 시리얼 로그: edge_serial_logger.py로 SKIP/HEARTBEAT/SEND 전부 저장 (cur_t, cur_h, pred_t, pred_h, err_t, err_h, status)
  Serial.println(String(cur_t) + "," + String(cur_h) + "," + String(pred_t) + "," + String(pred_h) + "," + String(err_t, 3) + "," + String(err_h, 3) + "," + status);

  // 전력 절감: 디스플레이/LoRa 슬립 후 5분 경과 시 깨어남
  // display.displayOff();
  LoRa.sleep();

  uint64_t sleep_time_us = 60ULL * 1000ULL * 1000ULL;  // 1분
  esp_sleep_enable_timer_wakeup(sleep_time_us);
  esp_light_sleep_start();

  display.displayOn();
}
