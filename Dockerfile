FROM python:3.12-slim

WORKDIR /app

# 의존성 레이어 (소스 변경 시 캐시 재사용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스
COPY server.py .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# DB 자격증명은 런타임에 환경변수로 주입 (-e 또는 --env-file)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
