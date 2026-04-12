FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache friendly)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -r pyproject.toml bcrypt

# Copy source
COPY . .

EXPOSE 8001

# Run as non-root
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
