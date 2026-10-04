ARG PYTHON_BASE=python:3.11-slim
FROM ${PYTHON_BASE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --create-home runner
USER 10001:10001
WORKDIR /episode
