FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run_ingest.py .
COPY prune.py .
COPY trafilatura_settings.cfg .

CMD ["python", "run_ingest.py"]
