#include <SPI.h>
#include <LoRa.h>

// 1. 하드웨어 핀 설정 (성근님 테스트 코드 기준)
#define SS      18
#define RST     14
#define DIO0    26
#define BAND    433E6  // 미국 라스베이거스 주파수

void setup() {
  Serial.begin(115200);
  while (!Serial);

  LoRa.setPins(SS, RST, DIO0);

  if (!LoRa.begin(BAND)) {
    Serial.println("LoRa init failed!");
    while (1);
  }

  Serial.println("LoRa Gateway Node Ready (433MHz)");
}

void loop() {
  // 1. 엣지 노드로부터 패킷 수신 대기
  int packetSize = LoRa.parsePacket();

  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    
    // 라즈베리 파이(Python)가 읽을 수 있도록 시리얼 출력
    // 형식: "Received: [온도],[습도]"
    Serial.println("Received: " + received);

    // 2. 라즈베리 파이로부터 Unix Timestamp 수신 대기
    // 파이썬 gateway.py가 데이터를 확인하고 즉시 시간을 시리얼로 쏴줍니다.
    unsigned long startTime = millis();
    String timestamp = "";
    
    // 최대 1초 동안 시리얼 응답 대기
    while (millis() - startTime < 1000) {
      if (Serial.available() > 0) {
        timestamp = Serial.readStringUntil('\n');
        break;
      }
    }

    // 3. 엣지 노드에게 시간 정보(Unix Timestamp) 회신
    if (timestamp.length() > 0) {
      delay(50); // 엣지 노드가 수신 모드로 전환될 시간 확보
      LoRa.beginPacket();
      LoRa.print(timestamp);
      LoRa.endPacket();
      
      Serial.println("Sync sent: " + timestamp);
    }
    Serial.println("-----------------------");
  }
}