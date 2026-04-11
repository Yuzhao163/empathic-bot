FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY main.py .
EXPOSE 8001
CMD ["python", "main.py"]
