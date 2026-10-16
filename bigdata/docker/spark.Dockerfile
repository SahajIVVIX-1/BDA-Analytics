# Spark + Python image for the Big Data Lab: no local Java or Spark install needed.
#   docker compose -f docker-compose.bigdata.yml build spark
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-21-jre-headless procps \
 && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    PYTHONUNBUFFERED=1 \
    SPARK_DRIVER_MEMORY=2g \
    TZ=UTC

COPY bigdata/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /workspace
