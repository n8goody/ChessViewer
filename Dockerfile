FROM python:3.11-slim

RUN pip install --no-cache-dir chess

WORKDIR /app
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py"]