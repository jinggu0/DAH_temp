FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN python -m pip install --no-cache-dir -e .

RUN mkdir -p output logs

EXPOSE 8080 9000

CMD ["uas-utm-service", "--host", "0.0.0.0", "--port", "8080", "--scenario", "scenarios/korea_defense_uas_utm_ops.json"]
