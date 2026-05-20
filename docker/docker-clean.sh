#!/usr/bin/env bash
# =============================================================================
# docker-clean.sh — Limpa ambiente Docker
# =============================================================================
# Uso:
#   bash docker/docker-clean.sh           # Remove containers
#   bash docker/docker-clean.sh --all     # Remove tudo (containers + imagem + outputs)
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

CLEAN_ALL=false
[[ "${1:-}" == "--all" ]] && CLEAN_ALL=true

echo -e "${BOLD}🧹 Limpeza do ambiente Docker${NC}"
echo ""

# 1. Parar containers
echo "  Parando containers..."
docker compose --profile setup --profile run --profile interface --profile shell \
    down --remove-orphans 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Containers parados e removidos"

# 2. Remover containers órfãos
docker container prune -f --filter "label=com.docker.compose.project" 2>/dev/null || true

if [ "$CLEAN_ALL" = true ]; then
    # 3. Remover imagem
    echo ""
    echo "  Removendo imagem Docker..."
    docker rmi codesmell-pipeline:latest 2>/dev/null && \
        echo -e "  ${GREEN}✓${NC} Imagem removida" || \
        echo -e "  ${YELLOW}⚠${NC} Imagem não encontrada"

    # 4. Limpar outputs
    echo ""
    echo "  Limpando diretório output/..."
    rm -rf "$PROJECT_DIR/output/fase"*/
    mkdir -p "$PROJECT_DIR/output/fase"{1,2,3,4,5}
    echo -e "  ${GREEN}✓${NC} Outputs removidos"

    # 5. Limpar repos clonados
    echo ""
    read -p "  Remover repositórios clonados (repos/)? [s/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        rm -rf "$PROJECT_DIR/repos/"*
        echo -e "  ${GREEN}✓${NC} Repositórios removidos"
    else
        echo -e "  ${YELLOW}⚠${NC} Repositórios mantidos"
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}✓ Limpeza concluída!${NC}"
echo ""
