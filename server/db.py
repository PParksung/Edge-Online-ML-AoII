# server/db.py
"""MySQL: 엣지 수신 데이터 및 게이트웨이 예측 저장. AoII/모니터링용."""
import os
from datetime import datetime, timezone
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
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edge_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    created_at DATETIME(6) NOT NULL,
                    actual_temp DOUBLE NOT NULL,
                    actual_humidity DOUBLE NOT NULL,
                    pred_temp DOUBLE NOT NULL,
                    pred_humidity DOUBLE NOT NULL,
                    error_temp DOUBLE NOT NULL,
                    triggered TINYINT NOT NULL COMMENT '1=SEND, 0=SKIP',
                    INDEX idx_created_at (created_at),
                    INDEX idx_triggered (triggered)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)


def insert_edge_log(actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, triggered):
    """엣지 시리얼 로그용: SEND/SKIP 전부 저장. triggered: 1=SEND, 0=SKIP."""
    created_at = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO edge_log
                   (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, triggered)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, 1 if triggered else 0),
            )


def insert_reading(actual_temp, actual_humidity, pred_temp, pred_humidity):
    """수신된 한 건 + 그 시점 게이트웨이 예측값 저장."""
    created_at = datetime.now(timezone.utc)
    error_temp = actual_temp - pred_temp
    error_humidity = actual_humidity - pred_humidity
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO readings
                   (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, error_humidity)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (created_at, actual_temp, actual_humidity, pred_temp, pred_humidity, error_temp, error_humidity),
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
