-- =====================================================
-- 서울시 대기질 예측 결과 저장 스키마 (MySQL / MariaDB)
-- =====================================================

CREATE TABLE IF NOT EXISTS hourly_air_quality (
    id           BIGINT UNSIGNED  AUTO_INCREMENT PRIMARY KEY,
    district     VARCHAR(20)      NOT NULL COMMENT '서울시 자치구명',
    pred_date    DATE             NOT NULL COMMENT '예측 대상 날짜',
    hour         TINYINT UNSIGNED NOT NULL COMMENT '시간 (0~23)',
    pm10         DECIMAL(7, 2)    NOT NULL COMMENT 'PM10 예측 농도 (㎍/㎥)',
    pm25         DECIMAL(7, 2)    NOT NULL COMMENT 'PM2.5 예측 농도 (㎍/㎥)',
    o3           DECIMAL(6, 4)    DEFAULT NULL COMMENT '오존 예측 농도 (ppm), 현재 미지원',
    level        ENUM('green', 'yellow', 'red') NOT NULL COMMENT '운동 적합 등급',
    generated_at DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '추론 실행 시각',

    CONSTRAINT uq_district_date_hour UNIQUE (district, pred_date, hour),
    CONSTRAINT chk_hour  CHECK (hour  BETWEEN 0 AND 23),
    CONSTRAINT chk_pm10  CHECK (pm10  >= 0),
    CONSTRAINT chk_pm25  CHECK (pm25  >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_haq_district_date ON hourly_air_quality (district, pred_date);
