"""
server.py 목 테스트
실행: pytest test_server.py -v
"""

import os

# server 임포트 전에 필수 환경변수 설정 (실제 DB 연결 없이 테스트)
os.environ.setdefault("DB_USER", "test_user")
os.environ.setdefault("DB_PASSWORD", "test_password")

import pytest
from contextlib import contextmanager
from datetime import datetime as real_datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from server import app, _hour_label, _recommend, DURATION_MAP

client = TestClient(app)

KST   = timezone(timedelta(hours=9))
TODAY    = "2026-05-30"
TOMORROW = "2026-05-31"


# ── 픽스처 / 헬퍼 ──────────────────────────────────────────────────────────────

def _make_rows(level_map: dict | None = None) -> list[dict]:
    """24시간 mock DB 행 생성. level_map = {hour: level} (미지정 시 yellow)"""
    level_map = level_map or {}
    base_dt = real_datetime(2026, 5, 30, 11, 53, 4)
    return [
        {
            "hour":         h,
            "pm10":         float(28 + h * 0.2),
            "pm25":         float(15 + h * 0.1),
            "o3":           None,
            "level":        level_map.get(h, "yellow"),
            "generated_at": base_dt,
        }
        for h in range(24)
    ]


@pytest.fixture
def normal_rows():
    """일부 시간대 green 포함 24행."""
    return _make_rows({5: "green", 6: "green", 7: "green"})


@pytest.fixture
def mock_conn(normal_rows):
    """fetchall → normal_rows 를 반환하는 mock DB 커넥션."""
    cursor = MagicMock()
    cursor.fetchall.return_value = normal_rows
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def freeze_today(today_str: str = TODAY):
    """server._today() 가 today_str 에 해당하는 date 를 반환하도록 패치."""
    today = real_datetime.strptime(today_str, "%Y-%m-%d").date()
    return patch("server._today", return_value=today)


# ── 1. 순수 함수 단위 테스트 ───────────────────────────────────────────────────

class TestHourLabel:
    def test_midnight(self):
        assert _hour_label(0) == "자정(0시)"

    def test_am_1(self):
        assert _hour_label(1) == "오전 1시"

    def test_am_11(self):
        assert _hour_label(11) == "오전 11시"

    def test_noon(self):
        assert _hour_label(12) == "오후 12시"

    def test_pm_1(self):
        assert _hour_label(13) == "오후 1시"

    def test_pm_11(self):
        assert _hour_label(23) == "오후 11시"


class TestRecommend:
    def _tl(self, level_map: dict) -> list[dict]:
        return [
            {"hour": h, "level": level_map.get(h, "yellow"),
             "pm25": 15.0 + h * 0.1, "pm10": 28.0}
            for h in range(24)
        ]

    def test_green_preferred_over_yellow(self):
        tl = self._tl({5: "green", 6: "green"})
        hours, best, _ = _recommend(tl)
        assert 5 in hours and 6 in hours
        assert best in {5, 6}

    def test_max_three_recommendations(self):
        tl = self._tl({i: "green" for i in range(10)})
        hours, _, _ = _recommend(tl)
        assert len(hours) <= 3

    def test_recommended_hours_sorted_asc(self):
        tl = self._tl({3: "green", 1: "green", 5: "green"})
        hours, _, _ = _recommend(tl)
        assert hours == sorted(hours)

    def test_best_hour_has_lowest_pm25(self):
        # hour 8 → pm25=12, 7 → 13, 6 → 14
        tl = [
            {"hour": h, "level": "green",
             "pm25": 20.0 - h if h in (6, 7, 8) else 30.0, "pm10": 40.0}
            for h in range(24)
        ]
        _, best, _ = _recommend(tl)
        assert best == 8

    def test_all_red_still_returns_result(self):
        tl = [{"hour": h, "level": "red", "pm25": 60.0, "pm10": 120.0} for h in range(24)]
        hours, best, summary = _recommend(tl)
        assert len(hours) > 0
        assert isinstance(best, int)
        assert "자제" in summary

    def test_all_yellow_no_green_fallback(self):
        tl = self._tl({})   # 전부 yellow
        hours, best, summary = _recommend(tl)
        assert len(hours) > 0
        assert "추천" in summary

    def test_summary_contains_hour_label_for_green(self):
        tl = self._tl({7: "green"})
        _, best, summary = _recommend(tl)
        assert _hour_label(best) in summary


# ── 2. API 정상 응답 테스트 ────────────────────────────────────────────────────

class TestRecommendSuccess:
    def test_status_200(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}")
        assert r.status_code == 200

    def test_response_has_all_required_fields(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            data = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}").json()
        for field in ("district", "exercise", "date", "generated_at",
                      "timeline", "recommended_hours", "best_hour",
                      "summary", "recommended_duration_min"):
            assert field in data, f"필드 누락: {field}"

    def test_timeline_has_24_items(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            data = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}").json()
        assert len(data["timeline"]) == 24

    def test_timeline_item_fields(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            item = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}").json()["timeline"][0]
        for field in ("hour", "level", "pm10", "pm25", "o3"):
            assert field in item

    def test_echoes_district_and_exercise(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            data = client.get(f"/api/recommend?district=송파구&exercise=hiking&date={TODAY}").json()
        assert data["district"] == "송파구"
        assert data["exercise"] == "hiking"

    def test_tomorrow_date_accepted(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TOMORROW}")
        assert r.status_code == 200

    def test_o3_null_passed_through(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            tl = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}").json()["timeline"]
        assert all(item["o3"] is None for item in tl)

    def test_green_hours_appear_in_recommended(self, mock_conn):
        rows = _make_rows({5: "green", 6: "green", 7: "green"})
        mock_conn.cursor.return_value.fetchall.return_value = rows
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            data = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}").json()
        assert any(h in data["recommended_hours"] for h in [5, 6, 7])

    @pytest.mark.parametrize("exercise,expected_min", DURATION_MAP.items())
    def test_duration_map_all_exercises(self, mock_conn, exercise, expected_min):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            data = client.get(
                f"/api/recommend?district=강남구&exercise={exercise}&date={TODAY}"
            ).json()
        assert data["recommended_duration_min"] == expected_min


# ── 3. 유효성 검사 오류 테스트 (400) ──────────────────────────────────────────

class TestValidationErrors:
    def test_invalid_district_returns_400(self):
        with freeze_today():
            r = client.get(f"/api/recommend?district=없는구&exercise=jogging&date={TODAY}")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_DISTRICT"

    def test_invalid_exercise_returns_400(self):
        with freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise=swimming&date={TODAY}")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_EXERCISE"

    def test_date_wrong_format_returns_400(self):
        with freeze_today():
            r = client.get("/api/recommend?district=강남구&exercise=jogging&date=30-05-2026")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_DATE"

    def test_past_date_returns_400(self):
        with freeze_today():
            r = client.get("/api/recommend?district=강남구&exercise=jogging&date=2020-01-01")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_DATE"

    def test_far_future_date_returns_400(self):
        with freeze_today():
            r = client.get("/api/recommend?district=강남구&exercise=jogging&date=2099-12-31")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_DATE"

    @pytest.mark.parametrize("district", ["강남구", "종로구", "중구", "송파구", "은평구"])
    def test_valid_districts_pass_validation(self, mock_conn, district):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            r = client.get(f"/api/recommend?district={district}&exercise=jogging&date={TODAY}")
        assert r.status_code == 200

    @pytest.mark.parametrize("exercise", ["walking", "jogging", "cycling", "hiking", "ball"])
    def test_valid_exercises_pass_validation(self, mock_conn, exercise):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise={exercise}&date={TODAY}")
        assert r.status_code == 200

    def test_error_response_structure(self):
        with freeze_today():
            body = client.get(f"/api/recommend?district=없는구&exercise=jogging&date={TODAY}").json()
        assert set(body.keys()) == {"error"}
        assert "code" in body["error"]
        assert "message" in body["error"]


# ── 4. DB 오류 테스트 ─────────────────────────────────────────────────────────

class TestDBErrors:
    def test_db_connection_error_returns_503(self):
        import mysql.connector as mc
        with patch("mysql.connector.connect", side_effect=mc.Error("연결 실패")), \
             freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "MODEL_UNAVAILABLE"

    def test_empty_db_result_returns_503(self, mock_conn):
        mock_conn.cursor.return_value.fetchall.return_value = []
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "MODEL_UNAVAILABLE"

    def test_unexpected_exception_returns_500(self):
        with patch("mysql.connector.connect", side_effect=RuntimeError("알 수 없는 오류")), \
             freeze_today():
            r = client.get(f"/api/recommend?district=강남구&exercise=jogging&date={TODAY}")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "INTERNAL_ERROR"

    def test_db_queried_with_correct_params(self, mock_conn):
        with patch("mysql.connector.connect", return_value=mock_conn), freeze_today():
            client.get(f"/api/recommend?district=마포구&exercise=cycling&date={TODAY}")
        cursor = mock_conn.cursor.return_value
        args = cursor.execute.call_args[0][1]   # (district, date) 튜플
        assert args == ("마포구", TODAY)
