# The image is the deployable artifact: dependencies install here at build
# time from the hash-pinned file, never at deploy time. The base is pinned by
# digest for the same reason the pip installs and CI actions are hash-pinned:
# a tag can move to different code, a digest cannot. The tag comment records
# what the digest was resolved from.
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

# Run as a dedicated non-root user: a compromised app process should not own
# the container.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# Dependencies first, alone, so code edits do not invalidate this layer.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt

COPY app/ app/
COPY frontend/ frontend/
COPY seed.py ./

# Receipt storage: the only path the app writes, owned by the app user.
RUN mkdir uploads && chown appuser:appuser uploads

USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
