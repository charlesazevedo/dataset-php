#!/usr/bin/env bash
# =============================================================================
# docker-exec.sh — Executa um comando específico no container
# =============================================================================
# Uso:
#   bash docker/docker-exec.sh python3 scripts/fase1_selecionar_repositorio.py --help
#   bash docker/docker-exec.sh php -v
#   bash docker/docker-exec.sh phpmd --version
# =============================================================================
set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Uso: bash docker/docker-exec.sh <comando> [args...]"
    echo ""
    echo "Exemplos:"
    echo "  bash docker/docker-exec.sh php -v"
    echo "  bash docker/docker-exec.sh python3 --version"
    echo "  bash docker/docker-exec.sh phpmd --version"
    echo "  bash docker/docker-exec.sh python3 scripts/fase1_selecionar_repositorio.py --repo FakerPHP/Faker"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Build se necessário
if ! docker images codesmell-pipeline:latest --format '{{.ID}}' | grep -q .; then
    echo "⏳ Construindo imagem Docker..."
    docker compose build app
fi

echo "🐳 Executando: $*"
docker compose --profile shell run --rm shell bash -c "$*"
