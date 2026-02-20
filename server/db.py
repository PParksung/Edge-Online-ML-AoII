# server/db.py
"""MySQL: 엣지 수신 데이터 및 게이트웨이 예측 저장. AoII/모니터링용."""
import os
from datetime import datetime
from contextlib import contextmanager

try:
    import pymysql
except ImportError:
    pymysql = None


def _config():
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": os.environ.get("MYSQL_DATABASE", "aoii"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor if pymysql else None,
    }


@contextmanager
def get_connection():
    if not pymysql:
        raise RuntimeError("PyMySQL not installed. Run: pip install pymysql")
    conn = pymysql.connect(**_config())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _add_readings_columns_if_missing(conn):
    """기존 readings 테이블에 transmission_delay_ms 등 컬럼이 없으면 추가."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'readings'"
        )
        existing = {row["COLUMN_NAME"] for row in cur.fetchall()}
    if "transmission_delay_ms" not in existing:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE readings ADD COLUMN transmission_delay_ms INT NULL")
        conn.commit()


def _add_edge_log_columns_if_missing(conn):
    """기존 DB에 성능 컬럼이 없으면 추가 (마이그레이션)."""
    columns_to_add = [
        ("error_humidity", "DOUBLE NULL"),
        ("status", "VARCHAR(32) NULL"),
        ("inference_time_us", "BIGINT UNSIGNED NULL"),
        ("free_heap", "INT UNSIGNED NULL"),
        ("total_heap", "INT UNSIGNED NULL"),
    ]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'edge_log'"
        )
        existing = {row["COLUMN_NAME"] for row in cur.fetchall()}
    for col_name, col_def in columns_to_add:
        if col_name not in existing:
            with conn.cursor() as cur:
                cur.execute(f"ALTER TABLE edge_log ADD COLUMN {col_name} {col_def}")
            conn.commit()


def init_db():
    """테이블 생성 (최초 1회)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    created_at DATETIME(6) NOT NULL,
                    actual_temp DOUBLE NOT NULL,
                    actual_humidity DOUBLE NOT NULL,
                    pred_temp DOUBLE NOT NULL,
                    pred_humidity DOUBLE NOT NULL,
                    error_temp DOUBLE NOT NULL,
                    error_humidity DOUBLE NOT NULL,
                    transmission_delay_ms INT NULL,
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            _add_readings_columns_if_missing(conn)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edge_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    created_at DATETIME(6) NOT NULL,
                    actual_temp DOUBLE NOT NULL,
                    actual_humidity DOUBLE NOT NULL,
                    pred_temp DOUBLE NOT NULL,
                    pred_humidity DOUBLE NOT NULL,
                    error_temp DOUBLE NOT NULL,
                    error_humidity DOUBLE NULL,
                    triggered TINYINT NOT NULL COMMENT '1=SEND, 0=SKIP',
                    status VARCHAR(32) NULL,
                    inference_time_us BIGINT UNSIGNED NULL,
                    free_heap INT UNSIGNED NULL,
                    total_heap INT UNSIGNED NULL,
                    INDEX idx_created_at (created_at),
                    INDEX idx_triggered (triggered),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            _add_edge_log_columns_if_missing(conn)


def insert_edge_log(
    actual_temp,
    actual_humidity,
    pred_temp,
    pred_humidity,
    error_temp,
    triggered,
    error_humidity=None,
    status=None,
    inference_time_us=None,
    free_heap=None,
    total_heap=None,
):
    """엣지 시리얼 로그용: SEND/SKIP 전부 저장. triggered: 1=SEND, 0=SKIP. 성능 지표(μs, heap) 선택."""
    created_at = datetime.now()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO edge_log
                   (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity,
                    error_temp, error_humidity, triggered, status, inference_time_us, free_heap, total_heap)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    created_at,
                    actual_temp,
                    actual_humidity,
                    pred_temp,
                    pred_humidity,
                    error_temp,
                    error_humidity if error_humidity is not None else 0.0,
                    1 if triggered else 0,
                    status,
                    inference_time_us,
                    free_heap,
                    total_heap,
                ),
            )


def insert_reading(actual_temp, actual_humidity, pred_temp, pred_humidity, transmission_delay_ms=None):
    """수신된 한 건 + 그 시점 게이트웨이 예측값 저장. transmission_delay_ms: 엣지→게이트웨이 전송 지연(ms)."""
    created_at = datetime.now()
    error_temp = actual_temp - pred_temp
    error_humidity = actual_humidity - pred_humidity
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO readings
                   (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, error_humidity, transmission_delay_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, error_humidity, transmission_delay_ms),
            )


def get_recent(limit=500, since_iso=None):
    """모니터링/차트용 최근 데이터 (시간순)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if since_iso:
                cur.execute(
                    """SELECT id, created_at, actual_temp, actual_humidity,
                              pred_temp, pred_humidity, error_temp, error_humidity
                       FROM readings WHERE created_at >= %s ORDER BY created_at DESC LIMIT %s""",
                    (since_iso, limit),
                )
            else:
                cur.execute(
                    """SELECT id, created_at, actual_temp, actual_humidity,
                              pred_temp, pred_humidity, error_temp, error_humidity
                       FROM readings ORDER BY created_at DESC LIMIT %s""",
                    (limit,),
                )
            rows = cur.fetchall()
    # DictCursor: created_at이 datetime이면 ISO로 변환
    out = []
    for r in rows:
        d = dict(r)
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return list(reversed(out))


def get_stats():
    """대시보드용 요약 통계."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM readings")
            total = cur.fetchone()["total"]
            if total == 0:
                return {"total": 0}
            cur.execute(
                """SELECT
                     AVG(actual_temp) AS avg_temp,
                     AVG(actual_humidity) AS avg_humidity,
                     AVG(ABS(error_temp)) AS mae_temp,
                     AVG(ABS(error_humidity)) AS mae_humidity,
                     MIN(created_at) AS first_at,
                     MAX(created_at) AS last_at
                   FROM readings"""
            )
            row = cur.fetchone()
    return {
        "total": total,
        "avg_temp": round(float(row["avg_temp"]), 2),
        "avg_humidity": round(float(row["avg_humidity"]), 2),
        "mae_temp": round(float(row["mae_temp"]), 4),
        "mae_humidity": round(float(row["mae_humidity"]), 4),
        "first_at": row["first_at"].isoformat() if hasattr(row["first_at"], "isoformat") else row["first_at"],
        "last_at": row["last_at"].isoformat() if hasattr(row["last_at"], "isoformat") else row["last_at"],
    }
