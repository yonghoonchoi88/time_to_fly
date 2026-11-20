FROM python:3.12-slim

# WITH_YOLO=1 adds CPU torch + ultralytics; the default image serves the mock engine only.
ARG WITH_YOLO=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics

WORKDIR /app

COPY requirements.txt requirements-yolo.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_YOLO" = "1" ]; then \
         apt-get update \
         && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
         && rm -rf /var/lib/apt/lists/* \
         && pip install --no-cache-dir -r requirements-yolo.txt; \
       fi

COPY . .

RUN useradd --create-home --uid 1000 app
USER app

# Weights are not baked into the image; mount them, e.g. -v $PWD/data/models:/models:ro
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
