FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir poetry==1.8.2

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*
# RUN apt-get update && apt-get install -y \
#     net-tools \
#     dnsutils \
#     && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
 && poetry install --no-root --no-interaction --no-ansi

COPY ./src/ ./

ENV USER_ID="$(id -u)"
ENV GROUP_ID="$(id -g)"

EXPOSE 53/udp 80 443

CMD ["python", "server.py"]