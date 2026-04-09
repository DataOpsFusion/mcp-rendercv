REGISTRY   := docker-local.homeserverlocal.com
PROJECT    := rendercv
IMAGE      := rendercv-mcp
TAG        ?= latest
FULL_IMAGE := $(REGISTRY)/$(PROJECT)/$(IMAGE):$(TAG)

DEPLOY_HOST := devops@192.168.0.70
DEPLOY_DIR  := /opt/rendercv-mcp

.PHONY: build push deploy release login logs restart

## Build for linux/amd64 and push directly to Harbor.
## Run this from your Mac — buildx handles the cross-compilation.
build:
	docker buildx build \
	  --platform linux/amd64 \
	  --push \
	  -t $(FULL_IMAGE) \
	  .
	@echo "Pushed: $(FULL_IMAGE)"

## Alias — build already pushes.
push: build

## Copy the deploy compose file to devops-server and bring the service up.
deploy:
	ssh $(DEPLOY_HOST) "sudo mkdir -p $(DEPLOY_DIR)/workspace && sudo chown -R devops:devops $(DEPLOY_DIR)"
	scp deploy/docker-compose.yml $(DEPLOY_HOST):$(DEPLOY_DIR)/docker-compose.yml
	scp .env $(DEPLOY_HOST):$(DEPLOY_DIR)/.env
	ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose pull && docker compose up -d --remove-orphans"
	@echo "Deployed to $(DEPLOY_HOST):$(DEPLOY_DIR)"

release: build deploy
	@echo "Released $(FULL_IMAGE) to $(DEPLOY_HOST)"

login:
	docker login $(REGISTRY) -u admin

## Stream logs from the running container on devops-server.
logs:
	ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose logs -f rendercv-mcp"

## Restart the container on devops-server (e.g. after a config change).
restart:
	ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose restart"
