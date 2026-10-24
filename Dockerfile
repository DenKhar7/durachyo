FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sglypa

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot ./bot
RUN mkdir -p /app/data && chown sglypa:sglypa /app/data

USER sglypa
CMD ["python", "-m", "bot"]
