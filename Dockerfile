FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements ./requirements
RUN pip install --no-cache-dir --only-binary=imageio-ffmpeg -r requirements/runtime.lock

COPY pyproject.toml README.md LICENSE ./

COPY src ./src
RUN pip install --no-cache-dir --no-deps .
RUN useradd --system --no-create-home app

USER app

EXPOSE 8000
CMD ["python", "-m", "coeiroink_openai_tts.server"]
