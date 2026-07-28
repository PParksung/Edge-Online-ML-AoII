# Edge-Online-ML-AoII

> ESP32 엣지 디바이스에서 경량 MLP로 온·습도를 예측하고, 예측 오차가 임계값(δ)을 초과할 때만 전송하는 **이벤트 구동 IoT + 온라인 ML 파이프라인**.
> 주기 전송 대비 **최대 84.9% 전송 절감** (δ=0.5°C 기준 73.8% 절감, 온도 오차 0.71%). — KCC 학회 투고

## 핵심 결과

| 정책 | 전송 횟수/24h | 온도 오차 | 습도 오차 |
|---|---|---|---|
| 주기 전송 (1분마다) | 1,440 | — | — |
| Online ML (δ=0.5°C) | **377 (−73.8%)** | 0.71% | 2.96% |
| Online ML (δ=0.7°C) | **218 (−84.9%)** | 1.08% | 4.28% |

## 시스템 구성

```
[ESP32 + DHT 센서]           [라즈베리파이 게이트웨이]          [서버]
 경량 MLP 추론·온라인 학습 ─LoRa─▶ 동일 MLP 미러링·검증 ─MQTT─▶ Flask + MySQL/CSV 저장
 오차 δ 초과 시에만 전송            (gateway.py)             Prometheus + Grafana 모니터링
```

- **엣지의 MLP는 C++ float 배열로 직접 구현** — 수십 KB 메모리 제약에서 동작 (Rolling Window 12-64-32-2, ReLU)
- **온라인 학습을 전송 트리거 시점에만 적용** — 엣지·게이트웨이 양단 모델이 동일 이벤트로 갱신되어, 별도 동기화 통신 없이 정합성 유지
- MQTT 단일 발행 → 구독자 분리 구조 (CSV 로거 / MySQL 로거 / 모니터링)

## 디렉터리 안내

| 경로 | 내용 |
|---|---|
| `edge_node/` | ESP32 펌웨어(`.ino`) — δ=0.3/0.5/0.7 실험 버전, 비교군(주기 전송·단순 임계값) 및 시리얼 로거 |
| `gateway/` | 라즈베리파이 게이트웨이 — LoRa 수신, MLP 미러 로직, MQTT 발행 |
| `server/` | Flask 앱, MQTT→CSV/MySQL 파이프라인 (`MQTT.md`, `MONITORING.md` 문서 포함) |
| `monitoring/` | Prometheus 설정 |
| `compare_group_logging/` | 비교군(주기 전송·단순 임계값) 로깅 스크립트 |
| `dataset/` + `Pre_train.py` | 사전 학습 데이터셋 및 초기 가중치 학습 스크립트 |
| `장애_보완_사항.md` | 운영 중 발견한 장애 포인트와 보완 내역 |

## 실행 방법

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. .env 작성 (MySQL·MQTT 브로커·시리얼 포트 설정)

# 3. 사전 학습 → 초기 가중치 생성
python Pre_train.py

# 4. ESP32에 edge_node/MLP_edge_sensor.ino 업로드 (Arduino IDE)

# 5. 게이트웨이·서버 기동
python gateway/gateway.py          # 라즈베리파이
python server/mqtt_to_mysql.py     # 서버
python server/app.py               # Flask + Prometheus 엔드포인트
```

## 실험 재현

δ 임계값별 절감률 vs 예측 오차 트레이드오프 실험은 `edge_node/`의 `MLP_edge_sensor_0.3 / 0.5 / 0.7.ino`와 각 로그 CSV로 재현할 수 있습니다. 비교군(1분 주기 전송, 단순 임계값 전송)은 `compare_group_logging/`을 사용합니다.

## 관련 문서

- 논문: KCC 2026 투고 (1저자)
- 프로젝트 상세: 포트폴리오 노션 페이지 참고
