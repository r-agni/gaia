FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[agents]"

# Copy source
COPY geoguess/ geoguess/
COPY agents/ agents/
COPY client/ client/

# OpenEnv standard: expose port 8001
EXPOSE 8001

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

CMD ["uvicorn", "geoguess.server:app", "--host", "0.0.0.0", "--port", "8001"]
