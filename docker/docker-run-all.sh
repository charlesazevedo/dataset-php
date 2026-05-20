#!/usr/bin/env bash
# =============================================================================
# docker-run-all.sh — Executa todas as 5 fases dentro do container Docker
# =============================================================================
# Uso (via docker compose):
#   docker compose --profile run up run-all
#   REPO=laravel/framework docker compose --profile run up run-all
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log_phase() {
    echo ""
    echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║  $1${NC}"
    echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}
log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_info() { echo -e "  ${BLUE}ℹ${NC} $1"; }
log_fail() { echo -e "  ${RED}✗${NC} $1"; }

PROJECT_DIR="/app"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
OUTPUT_DIR="$PROJECT_DIR/output"
REPOS_DIR="$PROJECT_DIR/repos"
REPO_ARG="${REPO:-}"

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Pipeline de Code Smells PHP — Execução Docker             ║"
echo "║   Todas as 5 Fases                                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

START_TIME=$(date +%s)

# Garantir estrutura
mkdir -p "$OUTPUT_DIR/fase"{1,2,3,4,5} "$REPOS_DIR"

# ═══════════════════════════════════════════════════════════════
# FASE 1 — Seleção do Repositório
# ═══════════════════════════════════════════════════════════════
log_phase "FASE 1 — Seleção e Validação do Repositório"

if [ -n "$REPO_ARG" ]; then
    python3 "$SCRIPTS_DIR/fase1_selecionar_repositorio.py" --repo "$REPO_ARG" --output "$OUTPUT_DIR/fase1"
else
    python3 "$SCRIPTS_DIR/fase1_selecionar_repositorio.py" --output "$OUTPUT_DIR/fase1"
fi

METADATA_FILE="$OUTPUT_DIR/fase1/repositorio_metadata.json"
if [ ! -f "$METADATA_FILE" ]; then
    log_fail "Metadados da Fase 1 não encontrados"
    exit 1
fi

REPO_URL=$(python3 -c "import json; d=json.load(open('$METADATA_FILE')); print(d.get('github_url',''))")
REPO_NAME=$(python3 -c "import json; d=json.load(open('$METADATA_FILE')); print(d.get('repo_name','unknown').replace('/','_'))")
log_ok "Repositório: $REPO_URL"

# ═══════════════════════════════════════════════════════════════
# Clone
# ═══════════════════════════════════════════════════════════════
REPO_LOCAL="$REPOS_DIR/$REPO_NAME"
if [ -d "$REPO_LOCAL" ]; then
    log_info "Repositório já clonado: $REPO_LOCAL"
else
    log_info "Clonando repositório..."
    git clone --depth 1 "${REPO_URL}.git" "$REPO_LOCAL"
    log_ok "Clone concluído"
fi

# ═══════════════════════════════════════════════════════════════
# FASE 2 — Extração de Snippets
# ═══════════════════════════════════════════════════════════════
log_phase "FASE 2 — Extração de Snippets e Métricas"
php "$SCRIPTS_DIR/fase2_extrair_snippets.php" "$REPO_LOCAL"
log_ok "Snippets extraídos"

# ═══════════════════════════════════════════════════════════════
# FASE 3 — Análise Estática
# ═══════════════════════════════════════════════════════════════
log_phase "FASE 3 — Análise Estática (5 Ferramentas)"
bash "$SCRIPTS_DIR/fase3_analise_estatica.sh" "$REPO_LOCAL" "$OUTPUT_DIR/fase2/snippets_com_metricas.json"
log_ok "Análise estática concluída"

# ═══════════════════════════════════════════════════════════════
# FASE 4 — Interface de Anotação
# ═══════════════════════════════════════════════════════════════
log_phase "FASE 4 — Preparação da Interface de Anotação"
python3 "$SCRIPTS_DIR/fase4_preparar_interface.py" \
    --snippets "$OUTPUT_DIR/fase2/snippets_com_metricas.json" \
    --labels "$OUTPUT_DIR/fase3/pre_rotulacao.json" \
    --output "$OUTPUT_DIR/fase4"
log_ok "Interface de anotação gerada"
log_info "Acesse via: docker compose --profile interface up interface"

# ═══════════════════════════════════════════════════════════════
# FASE 5 — Validação e Dataset Final
# ═══════════════════════════════════════════════════════════════
log_phase "FASE 5 — Validação e Geração do Dataset Final"
ANN_ARGS=()
if [ -f "$OUTPUT_DIR/fase4/anotacoes_final.json" ]; then
    ANN_ARGS=(--annotations "$OUTPUT_DIR/fase4/anotacoes_final.json")
    log_info "Usando anotações manuais (com desempate)"
elif [ -f "$OUTPUT_DIR/fase4/anotacoes_consolidadas.json" ]; then
    ANN_ARGS=(--annotations "$OUTPUT_DIR/fase4/anotacoes_consolidadas.json")
    log_info "Usando anotações consolidadas (sem desempate)"
fi
python3 "$SCRIPTS_DIR/fase5_validar_dataset.py" \
    --fase1 "$OUTPUT_DIR/fase1/repositorio_metadata.json" \
    --fase2 "$OUTPUT_DIR/fase2/snippets_com_metricas.json" \
    --fase3 "$OUTPUT_DIR/fase3/pre_rotulacao.json" \
    --output "$OUTPUT_DIR/fase5" \
    "${ANN_ARGS[@]}"

# ═══════════════════════════════════════════════════════════════
# Resumo
# ═══════════════════════════════════════════════════════════════
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

log_phase "Pipeline Concluído!"

echo "  Repositório:  $REPO_URL"
echo "  Tempo total:  ${MINUTES}m ${SECONDS}s"
echo ""
echo "  Artefatos em output/ (persistidos via volume):"
echo "  ┌─────────────────────────────────────────────────────┐"

for f in \
    "$OUTPUT_DIR/fase1/repositorio_metadata.json" \
    "$OUTPUT_DIR/fase2/snippets_com_metricas.json" \
    "$OUTPUT_DIR/fase3/pre_rotulacao.json" \
    "$OUTPUT_DIR/fase4/interface_anotacao.html" \
    "$OUTPUT_DIR/fase5/dataset_final.csv" \
    "$OUTPUT_DIR/fase5/validation_report.json"; do
    if [ -f "$f" ]; then
        SIZE=$(du -h "$f" | cut -f1)
        REL=$(echo "$f" | sed "s|$PROJECT_DIR/||")
        printf "  │ %-42s %6s │\n" "$REL" "$SIZE"
    fi
done

echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo -e "  ${GREEN}${BOLD}Dataset final: output/fase5/dataset_final.csv${NC}"
echo ""
