FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir poetry==1.8.2

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies without creating a virtual environment in Docker
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-dev

COPY ./src/ ./

EXPOSE 8080

CMD ["python", "server.py"]