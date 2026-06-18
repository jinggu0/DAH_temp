FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN python -m pip install --no-cache-dir -e .

RUN mkdir -p output

CMD ["dah-harness", "--scenario", "scenarios/uav_ugv_convoy.json", "--output", "output/harness_summary.json"]
