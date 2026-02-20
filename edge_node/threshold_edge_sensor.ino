#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include "SSD1306Wire.h"
#include <math.h>
#include <Esp.h>

// ==========================================
// 하드웨어 설정 
// ==========================================
#define OLED_SDA 4
#define OLED_SCL 15
#define OLED_RST 16

SSD1306Wire display(0x3c, OLED_SDA, OLED_SCL);
Adafruit_AHTX0 aht;

// ==========================================
// 임계값 및 상태 변수 설정
// ==========================================
float beta_temp = 0.5f;  // 온도 허용 오차
float beta_hum  = 3.0f;  // 습도 허용 오차

float last_sent_t = -100.0f; 
float last_sent_h = -100.0f;

unsigned long last_send_millis = 0;
const unsigned long HEARTBEAT_INTERVAL = 600000; // 10분

// ==========================================
// 초기 셋업
// ==========================================
void setup() {
  Serial.begin(115200); // 파이썬과 통신할 시리얼 포트
  
  pinMode(OLED_RST, OUTPUT); digitalWrite(OLED_RST, HIGH);
  Wire.begin(OLED_SDA, OLED_SCL);
  display.init(); display.flipScreenVertically();
  
  if (!aht.begin()) { display.drawString(0,0,"Sensor Error"); display.display(); while(1); }

  display.drawString(0, 0, "Mode: Threshold(USB)");
  display.drawString(0, 20, "Beta: 0.5C / 3.0%");
  display.display();
  delay(2000);

  last_send_millis = millis();
}

// ==========================================
// 메인 루프 (1분 주기)
// ==========================================
void loop() {
  sensors_event_t h_event, t_event;
  aht.getEvent(&h_event, &t_event);
  float cur_t = t_event.temperature;
  float cur_h = h_event.relative_humidity;

  // 1. 연산 시간 측정 (오차 계산 + 전송 조건 판단)
  unsigned long t_start = micros();

  float err_t = fabs(cur_t - last_sent_t);
  float err_h = fabs(cur_h - last_sent_h);

  bool is_heartbeat = (millis() - last_send_millis >= HEARTBEAT_INTERVAL);
  bool send_data = (err_t > beta_temp) || (err_h > beta_hum) || is_heartbeat;

  String status = "SKIP";

  if (send_data) {
    if (is_heartbeat && err_t <= beta_temp && err_h <= beta_hum) {
      status = "HEARTBEAT";
    } else {
      status = "SEND (DELTA)";
    }

    last_sent_t = cur_t;
    last_sent_h = cur_h;
    last_send_millis = millis();
  }

  unsigned long t_end = micros();
  unsigned long inference_time_us = t_end - t_start;

  // 2. 힙 메모리 (bytes)
  uint32_t free_heap = ESP.getFreeHeap();
  uint32_t total_heap = ESP.getHeapSize();

  // 3. CSV 한 줄: actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap
  //    (Threshold 정책: pred = last_sent)
  Serial.println(
    String(cur_t, 2) + "," + String(cur_h, 2) + "," +
    String(last_sent_t, 2) + "," + String(last_sent_h, 2) + "," +
    String(err_t, 3) + "," + String(err_h, 3) + "," +
    status + "," +
    String(inference_time_us) + "," + String(free_heap) + "," + String(total_heap)
  );

  // 4. OLED 디스플레이 출력 (현장 모니터링용)
  display.clear();
  display.drawString(0, 0, "Err T:" + String(err_t, 1) + " / H:" + String(err_h, 1));
  display.drawString(0, 15, "Last T:" + String(last_sent_t, 1) + " H:" + String(last_sent_h, 1));
  display.drawString(0, 30, "Cur  T:" + String(cur_t, 1) + " H:" + String(cur_h, 1));
  display.drawString(0, 45, ">> " + status);
  display.display();

  delay(60000);
}