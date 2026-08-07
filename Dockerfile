FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y sqlite3 curl procps && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start_fargate.sh

EXPOSE 8000

ENTRYPOINT ["./start_fargate.sh"]
