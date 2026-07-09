FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Zeabur 自动注入 $PORT
CMD ["sh", "-c", "python3 server.py --port ${PORT:-9000}"]
