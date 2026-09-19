FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# Settings come from the environment (compose env_file); data/ is a mounted volume.
CMD ["python", "-m", "bot_loker_wfh", "run-bot"]
