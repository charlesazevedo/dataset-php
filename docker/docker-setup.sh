#!/usr/bin/env bash
# =============================================================================
# docker-setup.sh — Verificação do ambiente Docker
# Executa dentro do container para validar que tudo está instalado
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_fail() { echo -e "  ${RED}✗${NC} $1"; }
log_info() { echo -e "  ${BLUE}ℹ${NC} $1"; }
section()  { echo -e "\n${BOLD}${BLUE}━━━ $1 ━━━${NC}"; }

ERRORS=0

echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Docker Setup — Dataset de Code Smells PHP             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"

# ── 1. Verificar runtime ──
section "1/5  Runtime"

if php -v &>/dev/null; then
    log_ok "PHP: $(php -r 'echo PHP_VERSION;')"
else
    log_fail "PHP não encontrado"; ERRORS=$((ERRORS+1))
fi

if python3 --version &>/dev/null; then
    log_ok "Python: $(python3 --version 2>&1)"
else
    log_fail "Python3 não encontrado"; ERRORS=$((ERRORS+1))
fi

if git --version &>/dev/null; then
    log_ok "Git: $(git --version | head -1)"
else
    log_fail "Git não encontrado"; ERRORS=$((ERRORS+1))
fi

if composer --version &>/dev/null 2>&1; then
    log_ok "Composer: $(composer --version 2>/dev/null | head -1)"
else
    log_fail "Composer não encontrado"; ERRORS=$((ERRORS+1))
fi

# ── 2. Extensões PHP ──
section "2/5  Extensões PHP"

for ext in xml tokenizer mbstring; do
    if php -m 2>/dev/null | grep -qi "$ext"; then
        log_ok "php-$ext"
    else
        log_warn "php-$ext não encontrado"; ERRORS=$((ERRORS+1))
    fi
done

# ── 3. Ferramentas de análise estática ──
section "3/5  Ferramentas de Análise Estática"

for tool in phpmd phpstan psalm phpcs; do
    if command -v "$tool" &>/dev/null || [ -f "/app/tools/${tool}.phar" ]; then
        log_ok "$tool"
    else
        log_fail "$tool não encontrado"; ERRORS=$((ERRORS+1))
    fi
done

if [ -f "/app/tools/sonar-scanner/bin/sonar-scanner" ]; then
    log_ok "sonar-scanner (SonarQube via /tools)"
else
    log_warn "sonar-scanner não encontrado em /tools/sonar-scanner/"
fi

# ── 4. Dependências Python ──
section "4/5  Dependências Python"

if python3 -c "import requests" 2>/dev/null; then
    log_ok "requests"
else
    log_warn "requests não instalado"
fi

# ── 5. Estrutura de diretórios ──
section "5/5  Estrutura de Diretórios"

for dir in output output/fase1 output/fase2 output/fase3 output/fase4 output/fase5 repos scripts config tools; do
    if [ -d "/app/$dir" ]; then
        log_ok "$dir/"
    else
        mkdir -p "/app/$dir"
        log_info "$dir/ (criado)"
    fi
done

# Verificar scripts
SCRIPT_COUNT=$(find /app/scripts -type f | wc -l)
log_ok "$SCRIPT_COUNT scripts encontrados em /app/scripts/"

# ── Resumo ──
echo ""
echo -e "${BOLD}━━━ Resumo ━━━${NC}"
echo ""

if [ $ERRORS -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}✓ Ambiente Docker configurado e pronto!${NC}"
    echo ""
    echo "  Execute o pipeline:"
    echo "    docker compose --profile run up run-all"
    echo ""
    echo "  Ou com repositório específico:"
    echo "    REPO=laravel/framework docker compose --profile run up run-all"
else
    echo -e "  ${YELLOW}${BOLD}⚠ $ERRORS problema(s) encontrado(s).${NC}"
    echo "  A imagem pode precisar ser reconstruída: docker compose build --no-cache"
fi
echo ""
