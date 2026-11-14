FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El contexto de build es ./backend (ver docker-compose.yml), así que aquí
# dentro los módulos quedan en /app/api/ (no en /app/backend/api/).
COPY . .

EXPOSE 8000

# Se ejecuta desde /app/api como módulo principal: main.py detecta que no hay
# paquete 'backend' y cae al import relativo (from database import ...).
CMD ["sh", "-c", "cd /app/api && uvicorn main:app --host 0.0.0.0 --port 8000"]
