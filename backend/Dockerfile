FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Static files are collected into the image; serving them is left to the
# compose setup (reverse proxy or a static-file middleware).
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "mysite.wsgi:application", "-b", "0.0.0.0:8000"]
