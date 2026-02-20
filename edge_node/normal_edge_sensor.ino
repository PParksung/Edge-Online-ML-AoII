#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include "SSD1306Wire.h"

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
  sensors_event_t h_event, t_event;
  aht.getEvent(&h_event, &t_event);
  
  float cur_t = t_event.temperature;
  float cur_h = h_event.relative_humidity;

  // 1. 파이썬 스크립트가 파싱하기 좋게 "온도,습도" 포맷으로 시리얼 출력
  Serial.println(String(cur_t, 2) + "," + String(cur_h, 2));

  // 2. OLED 화면 표시
  display.clear();
  display.drawString(0, 0, "Logging Raw Data...");
  display.drawString(0, 20, "T: " + String(cur_t, 2) + " C");
  display.drawString(0, 40, "H: " + String(cur_h, 2) + " %");
  display.display();

  // 3. 정확히 1분 대기 (수집용이므로 Sleep 안 하고 delay 써도 무방)
  delay(60000); 
}