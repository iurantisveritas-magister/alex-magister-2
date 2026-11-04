FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m alex && mkdir -p /data && chown -R alex /data /app
USER alex
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
# Un solo proceso con varios hilos: la base SQLite y el límite de intentos de acceso viven en ese proceso.
CMD ["sh", "-c", "gunicorn -w 1 --threads 8 --timeout 120 -b 0.0.0.0:${PORT:-10000} app_web:application"]
