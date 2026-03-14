# Build context: python-impl/
# docker build python-impl/

FROM python:3.14-slim

WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./

EXPOSE 8085

# WEB_CONCURRENCY: number of worker processes.
# Defaults to nproc (one per logical core) so Python uses all available CPU —
# the fair equivalent of Java's virtual-thread pool / Kotlin's Dispatchers.Default.
# Override at runtime: docker run -e WEB_CONCURRENCY=4 ...
ENV WEB_CONCURRENCY=""

# Shell form is required to resolve $(nproc) at container start time.
#   --loop uvloop      → libuv event loop (same engine as Node.js)
#   --http httptools    → C-based HTTP parser (C extension, replaces h11)
#   --no-access-log    → eliminates per-request log I/O from benchmark noise
CMD sh -c "uvicorn main:app \
     --host 0.0.0.0 \
     --port 8085 \
     --loop uvloop \
     --http httptools \
     --workers ${WEB_CONCURRENCY:-$(nproc)} \
     --no-access-log"
