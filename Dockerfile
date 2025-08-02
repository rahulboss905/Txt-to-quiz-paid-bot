FROM python:3.9-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT=10000

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo '#!/bin/bash\ncurl -f http://localhost:$PORT/health || exit 1' > /healthcheck.sh && \
    chmod +x /healthcheck.sh

HEALTHCHECK --interval=30s --timeout=3s \
  CMD /healthcheck.sh

CMD ["python", "main.py"]
