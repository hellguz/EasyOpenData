# ./backend/Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5400", "--reload"]
