FROM python:3.12-slim

# Forces stdout/stderr to be unbuffered. Without this, Python buffers output
# when it's not attached to a real terminal (exactly the situation inside a
# container), which means print() statements can sit invisibly in a buffer
# indefinitely at low request volume instead of reaching `docker compose
# logs` in real time. This is why background-thread diagnostic logging
# (mailer/SMS) could go completely silent even when the code was correct.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

# Run as a non-root user. UID 1000 is used deliberately (not just "any free
# UID") so it matches the typical first non-root user on the Ubuntu host,
# making the bind-mounted ./data directory's ownership predictable and easy
# to fix with `chown -R 1000:1000 data/` on the host if permissions ever
# look wrong after a fresh clone.
RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -m appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8082/', timeout=3)" || exit 1

CMD ["gunicorn", "-b", "0.0.0.0:8082", "-w", "3", "--worker-class", "gthread", "--threads", "4", "--timeout", "30", "wsgi:app"]
