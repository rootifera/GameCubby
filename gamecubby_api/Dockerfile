# Debian release pinned so a new Debian version never arrives with a routine rebuild.
FROM python:3.14-slim-trixie

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates lsb-release \
  && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
  && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt \
      $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
  && apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Starts as root only to fix /storage ownership, then runs as a non-root user.
COPY gamecubby_api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
# Liveness only (/health never touches the DB, and stays up during maintenance/restore).
# start-period covers `alembic upgrade head` on boot.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# `exec` so uvicorn (not bash) is the main process and receives stop signals.
CMD ["bash","-c","alembic upgrade head && exec uvicorn gamecubby_api.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-2} --limit-concurrency ${LIMIT_CONCURRENCY:-80} --no-server-header --proxy-headers"]
