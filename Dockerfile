FROM ghcr.io/project-unisonos/unison-common-wheel:latest AS common_wheel
FROM python:3.12-slim@sha256:fdab368dc2e04fab3180d04508b41732756cc442586f708021560ee1341f3d29

ARG REPO_PATH="."
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates build-essential linux-libc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ${REPO_PATH}/constraints.txt ./constraints.txt
COPY ${REPO_PATH}/requirements.txt ./requirements.txt
COPY --from=common_wheel /tmp/wheels /tmp/wheels
RUN pip install --no-cache-dir -c ./constraints.txt /tmp/wheels/unison_common-*.whl \
    && pip install --no-cache-dir -c ./constraints.txt -r requirements.txt

COPY ${REPO_PATH}/src/ ./src/

ENV PYTHONPATH=/app/src
EXPOSE 8089
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8089"]
