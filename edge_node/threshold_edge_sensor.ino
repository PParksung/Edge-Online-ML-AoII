#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include "SSD1306Wire.h"
#include <math.h>

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

  // 1. 단순 오차 계산
  float err_t = fabs(cur_t - last_sent_t);
  float err_h = fabs(cur_h - last_sent_h);
  
  // 2. 전송(로깅) 조건 판단
  bool is_heartbeat = (millis() - last_send_millis >= HEARTBEAT_INTERVAL);
  bool send_data = (err_t > beta_temp) || (err_h > beta_hum) || is_heartbeat;

  String status = "SKIP";

  if (send_data) {
    if (is_heartbeat && err_t <= beta_temp && err_h <= beta_hum) {
      status = "HEARTBEAT";
    } else {
      status = "SEND (DELTA)";
    }
    
    // OLED 표시 및 가상 전송을 위해 상태 갱신
    last_sent_t = cur_t;
    last_sent_h = cur_h;
    last_send_millis = millis();
  }

  // 3. 파이썬 로거에게 매분 무조건 센서값 전달
  // (파이썬 스크립트가 알아서 로깅 여부를 판단하게 됨)
  Serial.println(String(cur_t, 2) + "," + String(cur_h, 2));

  // 4. OLED 디스플레이 출력 (현장 모니터링용)
  display.clear();
  display.drawString(0, 0, "Err T:" + String(err_t, 1) + " / H:" + String(err_h, 1));
  display.drawString(0, 15, "Last T:" + String(last_sent_t, 1) + " H:" + String(last_sent_h, 1));
  display.drawString(0, 30, "Cur  T:" + String(cur_t, 1) + " H:" + String(cur_h, 1));
  display.drawString(0, 45, ">> " + status);
  display.display();

  // 5. 1분 대기
  delay(60000); 
}