"""
서울시 대기질 기반 야외운동 시간대 추천 API 서버
GET /api/recommend?district=강남구&exercise=jogging&date=2026-05-30
"""

import os
from contextlib import contextmanager
from datetime import date as date_type, datetime, timedelta, timezone

import mysql.connector
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

# ── DB 설정 ────────────────────────────────────────────────────────────────────
def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"필수 환경변수 {key} 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return val

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "192.168.3.10"),
    "database": os.getenv("DB_NAME", "aqsys"),
    "user":     _require_env("DB_USER"),
    "password": _require_env("DB_PASSWORD"),
    "port":     int(os.getenv("DB_PORT", "3306")),
}

# ── 상수 ───────────────────────────────────────────────────────────────────────
VALID_DISTRICTS = {
    "강남구", "강동구", "강북구", "강서구", "관악구",
    "광진구", "구로구", "금천구", "노원구", "도봉구",
    "동대문구", "동작구", "마포구", "서대문구", "서초구",
    "성동구", "성북구", "송파구", "양천구", "영등포구",
    "용산구", "은평구", "종로구", "중구", "중랑구",
}

VALID_EXERCISES = {"walking", "jogging", "cycling", "hiking", "ball"}

DURATION_MAP = {
    "walking": 60,
    "jogging": 40,
    "cycling": 45,
    "hiking":  90,
    "ball":    60,
}

KST = timezone(timedelta(hours=9))


def _today() -> "date_type":
    return datetime.now(KST).date()

# ── FastAPI 앱 ─────────────────────────────────────────────────────────────────
app = FastAPI(title="AQSys API", version="1.0.0")

ALLOW_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost,http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── 에러 응답 형식 통일 ────────────────────────────────────────────────────────
def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


# ── DB 헬퍼 ────────────────────────────────────────────────────────────────────
@contextmanager
def get_cursor():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor(dictionary=True)
        yield cursor
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ── 비즈니스 로직 ─────────────────────────────────────────────────────────────
def _hour_label(hour: int) -> str:
    if hour == 0:
        return "자정(0시)"
    if hour < 12:
        return f"오전 {hour}시"
    if hour == 12:
        return "오후 12시"
    return f"오후 {hour - 12}시"


def _recommend(timeline: list[dict]) -> tuple[list[int], int, str]:
    """level 우선순위(green>yellow)·pm25 오름차순으로 최대 3개 추천."""
    priority = {"green": 0, "yellow": 1, "red": 2}
    sorted_hours = sorted(timeline, key=lambda x: (priority[x["level"]], x["pm25"]))

    # red만 남은 경우에도 최선의 시간대 반환
    candidates = [h for h in sorted_hours if h["level"] != "red"] or sorted_hours
    top3 = candidates[:3]

    recommended_hours = sorted(c["hour"] for c in top3)
    best = top3[0]
    best_hour = best["hour"]

    if best["level"] == "red":
        summary = f"오늘은 대기 상태가 좋지 않아 야외운동을 자제해주세요. 부득이하다면 {_hour_label(best_hour)}가 상대적으로 낫습니다."
    else:
        summary = f"{_hour_label(best_hour)} 운동을 추천합니다. 이 시간대 PM2.5 농도가 가장 낮습니다."

    return recommended_hours, best_hour, summary


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────
@app.get("/api/recommend")
def recommend(
    district: str = Query(..., description="서울시 자치구명"),
    exercise: str = Query(..., description="walking/jogging/cycling/hiking/ball"),
    date:     str = Query(..., description="YYYY-MM-DD (오늘 또는 내일)"),
):
    # 파라미터 유효성 검사
    if district not in VALID_DISTRICTS:
        return error_response(400, "INVALID_DISTRICT", "유효하지 않은 자치구입니다.")

    if exercise not in VALID_EXERCISES:
        return error_response(400, "INVALID_EXERCISE", "유효하지 않은 운동 종류입니다.")

    try:
        req_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return error_response(400, "INVALID_DATE", "날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력하세요.")

    today = _today()
    if req_date not in (today, today + timedelta(days=1)):
        return error_response(400, "INVALID_DATE", "오늘 또는 내일 날짜만 선택 가능합니다.")

    # DB 조회
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT hour, pm10, pm25, o3, level, generated_at "
                "FROM hourly_air_quality "
                "WHERE district = %s AND pred_date = %s "
                "ORDER BY hour",
                (district, date),
            )
            rows = cursor.fetchall()
    except mysql.connector.Error:
        return error_response(503, "MODEL_UNAVAILABLE", "데이터베이스에 연결할 수 없습니다.")
    except Exception:
        return error_response(500, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다.")

    if not rows:
        return error_response(503, "MODEL_UNAVAILABLE", "해당 날짜의 예측 데이터가 없습니다.")

    # 응답 구성
    timeline = [
        {
            "hour":  r["hour"],
            "level": r["level"],
            "pm10":  float(r["pm10"]),
            "pm25":  float(r["pm25"]),
            "o3":    float(r["o3"]) if r["o3"] is not None else None,
        }
        for r in rows
    ]

    recommended_hours, best_hour, summary = _recommend(timeline)

    generated_at = rows[0]["generated_at"]
    if isinstance(generated_at, datetime):
        generated_at = generated_at.replace(tzinfo=KST).isoformat()
    else:
        generated_at = str(generated_at)

    return {
        "district":               district,
        "exercise":               exercise,
        "date":                   date,
        "generated_at":           generated_at,
        "timeline":               timeline,
        "recommended_hours":      recommended_hours,
        "best_hour":              best_hour,
        "summary":                summary,
        "recommended_duration_min": DURATION_MAP[exercise],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
