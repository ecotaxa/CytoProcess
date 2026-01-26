FROM python:3.8-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "src/CytoProcess/main.py"]

