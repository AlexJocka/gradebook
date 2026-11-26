# Образ приложения GradeBook: сборка и запуск из исходных файлов
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LOG_DIR=/app/logs

WORKDIR /app

# Зависимости ставятся отдельным слоем, чтобы не пересобирать его при изменении кода
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY docker-entrypoint.sh .

# Приложение работает от непривилегированного пользователя
RUN useradd --system --uid 1000 --home /app gradebook \
    && mkdir -p /app/logs \
    && chown -R gradebook:gradebook /app \
    && chmod +x docker-entrypoint.sh
USER gradebook

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
