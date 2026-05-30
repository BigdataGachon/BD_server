"""
pkl 모델로 24시간 대기질 예측 후 DB INSERT용 딕셔너리 리스트 반환.

사용법:
    python inference.py --district 강남구 --date 2026-05-30

외부에서 호출할 때:
    from inference import predict
    rows = predict(district="강남구", pred_date="2026-05-30",
                   weather=weather_dict, init_pm=init_pm_dict)
"""

import argparse
import json
import pickle
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).parent / "model"

# ── 신호등 기준 (PM2.5 기준 우선, PM10 보조) ──────────────────────────────
def _calc_level(pm10: float, pm25: float) -> str:
    if pm25 <= 15 and pm10 <= 30:
        return "green"
    if pm25 <= 35 and pm10 <= 80:
        return "yellow"
    return "red"


def _season(month: int) -> int:
    return {12: 4, 1: 4, 2: 4}.get(month, (month - 3) // 3 + 1)


def _load_models():
    with open(MODEL_DIR / "model_pm10.pkl", "rb") as f:
        m10 = pickle.load(f)
    with open(MODEL_DIR / "model_pm25.pkl", "rb") as f:
        m25 = pickle.load(f)
    with open(MODEL_DIR / "features.pkl", "rb") as f:
        features = pickle.load(f)
    return m10, m25, features


def predict(
    district: str,
    pred_date: str,
    weather: dict,
    init_pm: dict,
) -> list[dict]:
    """
    Parameters
    ----------
    district : 자치구명 (예: "강남구")
    pred_date : "YYYY-MM-DD"
    weather : 시간별 기상 예보. 키 = hour(int), 값 = {temp, humidity,
              wind_speed, wind_dir, precip} dict.
              24개 항목 없으면 가용 값으로 forward-fill.
    init_pm : 직전 24시간 PM 실측/예측값.
              {"pm10": [h-24, h-23, ..., h-1], "pm25": [...]} (길이 24)

    Returns
    -------
    list of dict — hourly_air_quality 테이블 INSERT 대상 행
        {district, pred_date, hour, pm10, pm25, o3, level, generated_at}
    """
    m10, m25, features = _load_models()

    d = date.fromisoformat(pred_date)
    month   = d.month
    weekday = d.weekday()   # 0=월 … 6=일
    season  = _season(month)

    pm10_hist = list(init_pm["pm10"])   # 길이 24 (인덱스 0 = 24시간 전)
    pm25_hist = list(init_pm["pm25"])

    # weather forward-fill
    last_w = weather.get(0, {"temp": 20, "humidity": 60,
                              "wind_speed": 2, "wind_dir": 180, "precip": 0})
    hourly_w = {}
    for h in range(24):
        hourly_w[h] = weather.get(h, last_w)
        last_w = hourly_w[h]

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    for hour in range(24):
        w = hourly_w[hour]

        def _lag(hist, n):
            idx = len(hist) - n
            return hist[idx] if idx >= 0 else hist[0]

        def _roll(hist, n):
            return float(np.mean(hist[-n:]) if len(hist) >= n else np.mean(hist))

        row_feat = [
            hour,
            month,
            weekday,
            season,
            w["temp"],
            w["humidity"],
            w["wind_speed"],
            w["wind_dir"],
            w["precip"],
            _lag(pm10_hist, 1),
            _lag(pm10_hist, 2),
            _lag(pm10_hist, 3),
            _lag(pm10_hist, 6),
            _lag(pm10_hist, 12),
            _lag(pm10_hist, 24),
            _lag(pm25_hist, 1),
            _lag(pm25_hist, 2),
            _lag(pm25_hist, 3),
            _lag(pm25_hist, 6),
            _lag(pm25_hist, 12),
            _lag(pm25_hist, 24),
            _roll(pm10_hist, 3),
            _roll(pm25_hist, 3),
            _roll(pm10_hist, 24),
            _roll(pm25_hist, 24),
        ]

        X = pd.DataFrame([row_feat], columns=features)
        pred_pm10 = float(m10.predict(X)[0])
        pred_pm25 = float(m25.predict(X)[0])

        pred_pm10 = max(0.0, round(pred_pm10, 2))
        pred_pm25 = max(0.0, round(pred_pm25, 2))

        pm10_hist.append(pred_pm10)
        pm25_hist.append(pred_pm25)

        rows.append({
            "district":     district,
            "pred_date":    pred_date,
            "hour":         hour,
            "pm10":         pred_pm10,
            "pm25":         pred_pm25,
            "o3":           None,
            "level":        _calc_level(pred_pm10, pred_pm25),
            "generated_at": generated_at,
        })

    return rows


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--district", required=True)
    parser.add_argument("--date",     required=True, help="YYYY-MM-DD")
    parser.add_argument("--weather",  default=None,
                        help="JSON 파일 경로 (없으면 기본값 사용)")
    parser.add_argument("--init-pm",  default=None,
                        help="JSON 파일 경로 (없으면 기본값 사용)")
    args = parser.parse_args()

    # 기본 더미 기상 (실제 서비스에선 외부 API로 교체)
    default_weather = {
        h: {"temp": 20, "humidity": 55, "wind_speed": 2.5,
            "wind_dir": 180, "precip": 0}
        for h in range(24)
    }
    # 기본 초기 PM (실제 서비스에선 에어코리아 API 또는 DB에서 조회)
    default_init_pm = {
        "pm10": [30.0] * 24,
        "pm25": [15.0] * 24,
    }

    weather  = json.load(open(args.weather))  if args.weather  else default_weather
    init_pm  = json.load(open(args.init_pm))  if args.init_pm  else default_init_pm

    # weather 키가 문자열일 경우 int로 변환
    if weather and isinstance(next(iter(weather)), str):
        weather = {int(k): v for k, v in weather.items()}

    results = predict(args.district, args.date, weather, init_pm)
    print(json.dumps(results, ensure_ascii=False, indent=2))
