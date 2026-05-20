# =============================================================================
# Makefile — Pipeline de Construção de Dataset de Code Smells PHP
# =============================================================================
# Uso:
#   make help        → Lista todos os comandos
#   make build       → Constrói a imagem Docker
#   make setup       → Verifica o ambiente
#   make run         → Executa todas as 5 fases
#   make interface   → Sobe interface web na porta 8080
#   make shell       → Terminal interativo no container
# =============================================================================

.PHONY: help build build-no-cache setup run run-repo fase1 fase2 fase3 fase4 fase5 \
        interface shell exec logs clean clean-all stop status

#SHELL := /bin/bash

# Variáveis
IMAGE_NAME    := codesmell-pipeline
COMPOSE       := docker compose
REPO          ?=
INTERFACE_PORT ?= 8080

# Cores
CYAN   := \033[36m
GREEN  := \033[32m
YELLOW := \033[33m
BOLD   := \033[1m
NC     := \033[0m

# ─── Help ───────────────────────────────────────────────────
help: ## Mostra esta ajuda
	@echo ""
	@echo "$(BOLD)  Pipeline de Code Smells PHP — Comandos Docker$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-18s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "  $(YELLOW)Exemplos:$(NC)"
	@echo "    make run REPO=laravel/framework"
	@echo "    make interface INTERFACE_PORT=9090"
	@echo "    make exec CMD='python3 scripts/fase1_selecionar_repositorio.py --help'"
	@echo ""

# ─── Build ──────────────────────────────────────────────────
build: ## Constrói a imagem Docker
	$(COMPOSE) build app

build-no-cache: ## Reconstrói sem cache
	$(COMPOSE) build --no-cache app

# ─── Execução ───────────────────────────────────────────────
setup: build ## Verifica o ambiente dentro do container
	$(COMPOSE) --profile setup up setup

run: build ## Executa todas as 5 fases
	REPO=$(REPO) $(COMPOSE) --profile run up run-all

run-repo: build ## Executa com repo específico (REPO=owner/name)
	@if [ -z "$(REPO)" ]; then echo "Uso: make run-repo REPO=owner/name"; exit 1; fi
	REPO=$(REPO) $(COMPOSE) --profile run up run-all

# ─── Fases individuais ──────────────────────────────────────
fase1: build ## Executa apenas a Fase 1
	REPO=$(REPO) $(COMPOSE) --profile fase1 up fase1

fase2: build ## Executa apenas a Fase 2
	$(COMPOSE) --profile fase2 up fase2

fase3: build ## Executa apenas a Fase 3
	$(COMPOSE) --profile fase3 up fase3

fase4: build ## Executa apenas a Fase 4
	$(COMPOSE) --profile fase4 up fase4

fase5: build ## Executa apenas a Fase 5
	$(COMPOSE) --profile fase5 up fase5

# ─── Interface ──────────────────────────────────────────────
interface: build ## Sobe interface web (porta 8080)
	@echo "$(GREEN)Interface acessível em: http://localhost:$(INTERFACE_PORT)$(NC)"
	INTERFACE_PORT=$(INTERFACE_PORT) $(COMPOSE) --profile interface up interface

# ─── Interativo ─────────────────────────────────────────────
shell: build ## Terminal interativo no container
	$(COMPOSE) --profile shell run --rm shell

exec: build ## Executa comando no container (CMD='...')
	@if [ -z "$(CMD)" ]; then echo "Uso: make exec CMD='comando'"; exit 1; fi
	$(COMPOSE) --profile shell run --rm shell bash -c "$(CMD)"

# ─── Manutenção ─────────────────────────────────────────────
stop: ## Parar todos os containers
	$(COMPOSE) --profile setup --profile run --profile interface --profile shell down

logs: ## Mostra logs dos containers
	$(COMPOSE) logs -f 2>/dev/null || echo "Nenhum container em execução."

status: ## Mostra status dos containers
	@echo "$(BOLD)Containers:$(NC)"
	@docker ps --filter "name=codesmell" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  Nenhum container ativo."
	@echo ""
	@echo "$(BOLD)Imagem:$(NC)"
	@docker images $(IMAGE_NAME) --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" 2>/dev/null || echo "  Imagem não encontrada."
	@echo ""
	@echo "$(BOLD)Volumes (output):$(NC)"
	@du -sh output/ 2>/dev/null || echo "  Diretório output/ vazio."

clean: ## Remove containers parados
	$(COMPOSE) --profile setup --profile run --profile interface --profile shell down --remove-orphans
	docker container prune -f --filter "label=com.docker.compose.project=php-codesmell-dataset" 2>/dev/null || true
	@echo "$(GREEN)✓ Containers removidos$(NC)"

clean-all: clean ## Remove tudo (containers, imagem, outputs)
	docker rmi $(IMAGE_NAME):latest 2>/dev/null || true
	rm -rf output/fase*/
	for i in 1 2 3 4 5; do mkdir -p output/fase$$i; done
	@echo "$(GREEN)✓ Imagem e outputs removidos$(NC)"
