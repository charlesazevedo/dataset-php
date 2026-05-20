#!/usr/bin/env bash
# =============================================================================
# docker-enter.sh — Entra no container interativamente
# =============================================================================
# Uso:
#   bash docker/docker-enter.sh           # Shell interativo
#   bash docker/docker-enter.sh php -v    # Executa comando específico
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Verificar se a imagem existe, senão build
if ! docker images codesmell-pipeline:latest --format '{{.ID}}' | grep -q .; then
    echo "⏳ Construindo imagem Docker..."
    docker compose build app
fi

if [ $# -eq 0 ]; then
    echo "🐳 Entrando no container (shell interativo)..."
    echo "   Digite 'exit' para sair."
    echo ""
    docker compose --profile shell run --rm shell
else
    echo "🐳 Executando: $*"
    docker compose --profile shell run --rm shell bash -c "$*"
fi
