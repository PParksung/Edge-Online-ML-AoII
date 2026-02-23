#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include "SSD1306Wire.h"
#include <Esp.h>

#define OLED_SDA 4
#define OLED_SCL 15
#define OLED_RST 16

SSD1306Wire display(0x3c, OLED_SDA, OLED_SCL);
Adafruit_AHTX0 aht;

void setup() {
  Serial.begin(115200); // 이 통로로 파이썬이 데이터를 읽어갑니다.
  
  pinMode(OLED_RST, OUTPUT); digitalWrite(OLED_RST, HIGH);
  Wire.begin(OLED_SDA, OLED_SCL);
  display.init(); display.flipScreenVertically();
  
  if (!aht.begin()) { 
    display.drawString(0,0,"Sensor Error"); 
    display.display(); 
    while(1); 
  }

  display.drawString(0, 0, "RAW DATA LOGGER");
  display.display();
  delay(1000);
}

void loop() {
  // 연산 시간 측정: 센서 읽기
  unsigned long t_start = micros();

  sensors_event_t h_event, t_event;
  aht.getEvent(&h_event, &t_event);

  float cur_t = t_event.temperature;
  float cur_h = h_event.relative_humidity;

  unsigned long t_end = micros();
  unsigned long inference_time_us = t_end - t_start;

  uint32_t free_heap = ESP.getFreeHeap();
  uint32_t total_heap = ESP.getHeapSize();

  // CSV 한 줄: actual_t, actual_h, pred_t, pred_h, error_t, error_h, status, inference_time_us, free_heap, total_heap
  // (RAW 모드: pred/error 없음 → 0, status=RAW)
  Serial.println(
    String(cur_t, 2) + "," + String(cur_h, 2) + ",0,0,0,0,RAW," +
    String(inference_time_us) + "," + String(free_heap) + "," + String(total_heap)
  );

  display.clear();
  display.drawString(0, 0, "Logging Raw Data...");
  display.drawString(0, 20, "T: " + String(cur_t, 2) + " C");
  display.drawString(0, 40, "H: " + String(cur_h, 2) + " %");
  display.display();

  delay(60000);
}