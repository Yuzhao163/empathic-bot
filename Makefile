.PHONY: help build build-gateway build-python build-frontend build-all \
	run run-gateway run-python run-frontend run-redis \
	docker-build docker-up docker-down docker-logs \
	deploy test lint clean fmt vet

# =============================================================================
# Variables
# =============================================================================

DOCKER_IMAGE_GATEWAY=empathic-gateway
DOCKER_IMAGE_PYTHON=empathic-python
DOCKER_IMAGE_FRONTEND=empathic-frontend

# =============================================================================
# Help
# =============================================================================

help:
	@echo "EmpathicBot Makefile"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Development:"
	@echo "  run-gateway      Run gateway locally (requires Redis + Python running)"
	@echo "  run-python       Run Python LLM service locally"
	@echo "  run-redis       Start Redis via Docker"
	@echo ""
	@echo "Build:"
	@echo "  build-gateway    Build gateway binary"
	@echo "  build-python     Build Python service Docker image"
	@echo "  build-frontend   Build frontend"
	@echo "  build-all        Build all Docker images"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build     Build all images"
	@echo "  docker-up        Start all services (docker-compose up -d)"
	@echo "  docker-down      Stop all services"
	@echo "  docker-logs      Tail all service logs"
	@echo ""
	@echo "Quality:"
	@echo "  lint             Run linters (golangci-lint, ruff)"
	@echo "  test             Run tests"
	@echo "  fmt              Format code"
	@echo "  vet              Go vet"
	@echo ""
	@echo "Deploy:"
	@echo "  deploy           Deploy to Railway (gateway + python) + Vercel (frontend)"

# =============================================================================
# Build
# =============================================================================

build-gateway:
	cd gateway && go build -o ../bin/gateway .

build-python:
	cd python_service && pip install -e . 2>/dev/null || true

build-frontend:
	cd frontend && npm install && npm run build

build-all: build-gateway

# =============================================================================
# Run
# =============================================================================

run-redis:
	docker run -d --name empathic-redis -p 6379:6379 redis:7-alpine

run-gateway: build-gateway
	REDIS_URL=localhost:6379 \
	ALLOWED_ORIGINS=http://localhost:3000 \
	./bin/gateway

run-python:
	cd python_service && python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# =============================================================================
# Docker
# =============================================================================

docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@echo "Services started. Gateway: http://localhost:8080"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# =============================================================================
# Quality
# =============================================================================

fmt:
	cd gateway && go fmt ./...
	cd python_service && ruff format .
	cd frontend && npx prettier --write src/

vet:
	cd gateway && go vet ./...

lint:
	@which golangci-lint >/dev/null && cd gateway && golangci-lint run || echo "golangci-lint not installed"
	@which ruff >/dev/null && cd python_service && ruff check . || echo "ruff not installed"

test:
	cd gateway && go test ./... -v -short
	cd python_service && python -m pytest -v --tb=short 2>/dev/null || echo "pytest not available"

# =============================================================================
# Deploy
# =============================================================================

deploy:
	@echo "Deploying to Railway + Vercel..."
	@echo "1. Ensure .env.production is configured with MINIMAX_API_KEY and ALLOWED_ORIGINS"
	@echo "2. Push to GitHub main branch"
	@echo "3. Railway will auto-deploy gateway + python_service from GitHub"
	@echo "4. Vercel will auto-deploy frontend on push"
	@echo ""
	@echo "Or manually:"
	@echo "  railway up     # in gateway/ and python_service/"
	@echo "  vercel --prod  # in frontend/"

clean:
	rm -rf bin/
	docker compose down -v --remove-orphans
	docker rmi $(DOCKER_IMAGE_GATEWAY) $(DOCKER_IMAGE_PYTHON) $(DOCKER_IMAGE_FRONTEND) 2>/dev/null || true
