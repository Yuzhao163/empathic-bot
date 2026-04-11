.PHONY: install dev build start clean

# 安装依赖
install:
	cd gateway && go mod tidy
	cd frontend && npm install

# 开发模式（仅前端）
dev:
	cd frontend && npm run dev

# 构建全部 Docker 镜像
build:
	docker-compose build

# 启动全部服务
start:
	docker-compose up -d

# 仅启动后端
start-backend:
	docker-compose up -d gateway python_service java_service redis

# 查看日志
logs:
	docker-compose logs -f

# 停止服务
stop:
	docker-compose down

# 清理（删除容器+镜像）
clean:
	docker-compose down --rmi all -v

# 前端单独构建
build-frontend:
	cd frontend && npm install && npm run build

# 单独测试某个服务
test-gateway:
	cd gateway && go run main.go

test-python:
	cd python_service && python main.py
