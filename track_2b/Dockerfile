# Review app: Python standard library only, so the image builds without pip and runs without internet.
FROM python:3.12-slim
WORKDIR /app
COPY src/ src/
COPY data/sample/ data/sample/
COPY data/benchmark/ data/benchmark/
ENV PYTHONUNBUFFERED=1 OUTPUT_DIR=/app/outputs PORT=8000
EXPOSE 8000
CMD ["python", "-m", "src.app"]
