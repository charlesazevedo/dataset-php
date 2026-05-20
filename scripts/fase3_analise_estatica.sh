#!/usr/bin/env bash
# =============================================================================
# Fase 3 — Análise Estática com 5 Ferramentas + Consolidação
# =============================================================================
# Executa PHPMD, PHPStan, Psalm, PHPCS e SonarQube Scanner sobre o repositório clonado,
# depois consolida tudo mapeando findings para os snippets da Fase 2.
#
# Uso:
#   bash fase3_analise_estatica.sh <repo_dir> [snippets_json]
#
# Argumentos:
#   repo_dir      — Caminho do repositório clonado (ex: ../repos/meu-repo)
#   snippets_json — JSON da Fase 2 (padrão: ../output/fase2/snippets_com_metricas.json)
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'
log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_fail() { echo -e "  ${RED}✗${NC} $1"; }
log_info() { echo -e "  ${BLUE}ℹ${NC} $1"; }
section()  { echo -e "\n${BOLD}${BLUE}━━━ $1 ━━━${NC}"; }

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"
OUTPUT_DIR="$PROJECT_DIR/output/fase3"
TOOLS_DIR="$PROJECT_DIR/tools"

REPO_DIR="${1:?Uso: bash fase3_analise_estatica.sh <repo_dir> [snippets_json]}"
SNIPPETS_JSON="${2:-$PROJECT_DIR/output/fase2/snippets_com_metricas.json}"

if [ ! -d "$REPO_DIR" ]; then
    echo "ERRO: Diretório do repositório não encontrado: $REPO_DIR"
    exit 1
fi
REPO_DIR="$(cd "$REPO_DIR" && pwd)"

if [ ! -f "$SNIPPETS_JSON" ]; then
    echo "ERRO: JSON de snippets da Fase 2 não encontrado: $SNIPPETS_JSON"
    echo "Execute a Fase 2 primeiro."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Fase 3 — Análise Estática (5 Ferramentas)              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Repositório:  $REPO_DIR"
log_info "Snippets:     $SNIPPETS_JSON"
log_info "Saída:        $OUTPUT_DIR"

# ── Função auxiliar: encontrar ferramenta ──
find_tool() {
    local name="$1"
    local phar_name="$2"
    # 1. Global (PATH)
    if command -v "$name" &>/dev/null; then echo "$(command -v "$name")"; return 0; fi
    # 2. tools/ local
    if [ -f "$TOOLS_DIR/${phar_name}.phar" ]; then echo "php $TOOLS_DIR/${phar_name}.phar"; return 0; fi
    # 3. Composer vendor
    if [ -f "$CONFIG_DIR/vendor/bin/$name" ]; then echo "$CONFIG_DIR/vendor/bin/$name"; return 0; fi
    return 1
}

# ──────────────────────────────────────────────────────────
# 1. PHPMD
# ──────────────────────────────────────────────────────────
section "1/5  PHPMD (PHP Mess Detector)"

PHPMD_CMD=$(find_tool "phpmd" "phpmd" 2>/dev/null || echo "")
if [ -n "$PHPMD_CMD" ]; then
    log_info "Usando: $PHPMD_CMD"
    PHPMD_RULES="$CONFIG_DIR/phpmd_rules.xml"
    if [ ! -f "$PHPMD_RULES" ]; then
        PHPMD_RULES="cleancode,codesize,design,naming,unusedcode,controversial"
        log_warn "phpmd_rules.xml não encontrado, usando rulesets padrão"
    fi

    $PHPMD_CMD "$REPO_DIR/src" json "$PHPMD_RULES" \
        --exclude "vendor,tests,test,node_modules" \
        2>/dev/null | grep -v "^Deprecated:" > "$OUTPUT_DIR/phpmd_output.json" || true

    if [ -f "$OUTPUT_DIR/phpmd_output.json" ]; then
        PHPMD_COUNT=$(python3 -c "
import json
with open('$OUTPUT_DIR/phpmd_output.json') as f:
    data = json.load(f)
total = sum(len(fe.get('violations',[])) for fe in data.get('files',[]))
print(total)
" 2>/dev/null || echo "?")
        log_ok "PHPMD: $PHPMD_COUNT violations encontradas"
    else
        log_warn "PHPMD não produziu saída"
        echo '{"files":[]}' > "$OUTPUT_DIR/phpmd_output.json"
    fi
else
    log_fail "PHPMD não encontrado. Execute setup.sh para instalar."
    echo '{"files":[]}' > "$OUTPUT_DIR/phpmd_output.json"
fi

# ──────────────────────────────────────────────────────────
# 2. PHPStan
# ──────────────────────────────────────────────────────────
section "2/5  PHPStan (Static Analysis)"

PHPSTAN_CMD=$(find_tool "phpstan" "phpstan" 2>/dev/null || echo "")
if [ -n "$PHPSTAN_CMD" ]; then
    log_info "Usando: $PHPSTAN_CMD"

    # Usar nível 5 (bom equilíbrio entre rigor e praticidade)
    $PHPSTAN_CMD analyse "$REPO_DIR/src" \
        --level=5 \
        --error-format=json \
        --no-progress \
        --memory-limit=1G \
        > "$OUTPUT_DIR/phpstan_output.json" 2>/dev/null || true

    if [ -f "$OUTPUT_DIR/phpstan_output.json" ] && [ -s "$OUTPUT_DIR/phpstan_output.json" ]; then
        PHPSTAN_COUNT=$(python3 -c "
import json
with open('$OUTPUT_DIR/phpstan_output.json') as f:
    data = json.load(f)
total = sum(len(fe.get('messages',[])) for fe in data.get('files',{}).values())
print(total)
" 2>/dev/null || echo "?")
        log_ok "PHPStan: $PHPSTAN_COUNT erros/warnings encontrados"
    else
        log_warn "PHPStan não produziu saída válida"
        echo '{"totals":{"errors":0},"files":{}}' > "$OUTPUT_DIR/phpstan_output.json"
    fi
else
    log_fail "PHPStan não encontrado. Execute setup.sh para instalar."
    echo '{"totals":{"errors":0},"files":{}}' > "$OUTPUT_DIR/phpstan_output.json"
fi

# ──────────────────────────────────────────────────────────
# 3. Psalm
# ──────────────────────────────────────────────────────────
section "3/5  Psalm (Static Analysis)"

PSALM_CMD=$(find_tool "psalm" "psalm" 2>/dev/null || echo "")
if [ -n "$PSALM_CMD" ]; then
    log_info "Usando: $PSALM_CMD"

    # Verificar se o repo tem psalm.xml; se não, criar temporário
    PSALM_CONFIG=""
    if [ -f "$REPO_DIR/psalm.xml" ]; then
        PSALM_CONFIG="--config=$REPO_DIR/psalm.xml"
    elif [ -f "$REPO_DIR/psalm.xml.dist" ]; then
        PSALM_CONFIG="--config=$REPO_DIR/psalm.xml.dist"
    else
        # Criar config temporária
        TEMP_PSALM="$OUTPUT_DIR/_psalm_temp.xml"
        cat > "$TEMP_PSALM" <<PSEOF
<?xml version="1.0"?>
<psalm errorLevel="2" resolveFromConfigFile="false" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns="https://getpsalm.org/schema/config" xsi:schemaLocation="https://getpsalm.org/schema/config vendor/vimeo/psalm/config.xsd">
    <projectFiles>
        <directory name="$REPO_DIR/src"/>
    </projectFiles>
</psalm>
PSEOF
        PSALM_CONFIG="--config=$TEMP_PSALM"
    fi

    $PSALM_CMD $PSALM_CONFIG \
        --output-format=json \
        --no-progress \
        --no-cache \
        > "$OUTPUT_DIR/psalm_output.json" 2>/dev/null || true

    # Limpar config temporária
    rm -f "$OUTPUT_DIR/_psalm_temp.xml"

    if [ -f "$OUTPUT_DIR/psalm_output.json" ] && [ -s "$OUTPUT_DIR/psalm_output.json" ]; then
        PSALM_COUNT=$(python3 -c "
import json
with open('$OUTPUT_DIR/psalm_output.json') as f:
    data = json.load(f)
print(len(data) if isinstance(data, list) else 0)
" 2>/dev/null || echo "?")
        if [ "$PSALM_COUNT" = "?" ]; then
            log_warn "Psalm: JSON inválido, gerando fallback vazio"
            echo '[]' > "$OUTPUT_DIR/psalm_output.json"
        else
            log_ok "Psalm: $PSALM_COUNT issues encontradas"
        fi
    else
        log_warn "Psalm não produziu saída"
        echo '[]' > "$OUTPUT_DIR/psalm_output.json"
    fi
else
    log_fail "Psalm não encontrado. Execute setup.sh para instalar."
    echo '[]' > "$OUTPUT_DIR/psalm_output.json"
fi

# ──────────────────────────────────────────────────────────
# 4. PHPCS (PHP CodeSniffer)
# ──────────────────────────────────────────────────────────
section "4/5  PHPCS (PHP CodeSniffer)"

PHPCS_CMD=$(find_tool "phpcs" "phpcs" 2>/dev/null || echo "")
if [ -n "$PHPCS_CMD" ]; then
    log_info "Usando: $PHPCS_CMD"
    PHPCS_RULES="$CONFIG_DIR/phpcs_rules.xml"
    PHPCS_STANDARD="$PHPCS_RULES"
    if [ ! -f "$PHPCS_RULES" ]; then
        PHPCS_STANDARD="Generic"
        log_warn "phpcs_rules.xml não encontrado, usando standard Generic"
    fi

    $PHPCS_CMD "$REPO_DIR/src" \
        --standard="$PHPCS_STANDARD" \
        --report=json \
        --ignore="*/vendor/*,*/tests/*,*/test/*,*/node_modules/*" \
        -q \
        > "$OUTPUT_DIR/phpcs_output.json" 2>/dev/null || true

    if [ -f "$OUTPUT_DIR/phpcs_output.json" ] && [ -s "$OUTPUT_DIR/phpcs_output.json" ]; then
        PHPCS_COUNT=$(python3 -c "
import json
with open('$OUTPUT_DIR/phpcs_output.json') as f:
    data = json.load(f)
total = sum(len(fe.get('messages',[])) for fe in data.get('files',{}).values())
print(total)
" 2>/dev/null || echo "?")
        log_ok "PHPCS: $PHPCS_COUNT messages encontradas"
    else
        log_warn "PHPCS não produziu saída válida"
        echo '{"totals":{"errors":0,"warnings":0},"files":{}}' > "$OUTPUT_DIR/phpcs_output.json"
    fi
else
    log_fail "PHPCS não encontrado. Execute setup.sh para instalar."
    echo '{"totals":{"errors":0,"warnings":0},"files":{}}' > "$OUTPUT_DIR/phpcs_output.json"
fi

# ──────────────────────────────────────────────────────────
# 5. SonarQube Scanner
# ──────────────────────────────────────────────────────────
section "5/5  SonarQube Scanner (Qualidade de C\u00f3digo)"

SONAR_SCANNER="$TOOLS_DIR/sonar-scanner/bin/sonar-scanner"
# SonarQube local (servi\u00e7o no docker-compose, perfil fase3)
SONAR_HOST="${SONAR_HOST:-http://sonarqube:9000}"

# Aguardar SonarQube estar pronto (j\u00e1 validado pelo healthcheck do compose)
if [ ! -f "$SONAR_SCANNER" ]; then
    log_warn "SonarQube Scanner n\u00e3o encontrado em $SONAR_SCANNER"
else
    log_info "Conectando ao SonarQube em $SONAR_HOST..."

    # 1. Aguardar API do SonarQube estar realmente pronta (além do healthcheck)
    log_info "Aguardando API do SonarQube..."
    for i in $(seq 1 30); do
        if curl -sf -o /dev/null -u admin:admin "$SONAR_HOST/api/system/status" 2>/dev/null; then
            log_ok "API respondendo"
            break
        fi
        sleep 2
    done

    # 2. Criar projeto e rodar scanner
    REPO_NAME=$(basename "$REPO_DIR")
    log_info "Analisando projeto: $REPO_NAME"

    cat > /tmp/sonar-project.properties << EOF
sonar.host.url=${SONAR_HOST}
sonar.projectKey=${REPO_NAME}
sonar.projectName=${REPO_NAME}
sonar.sources=${REPO_DIR}/src
sonar.exclusions=vendor/**,tests/**,test/**,node_modules/**
sonar.php.file.suffixes=php
sonar.sourceEncoding=UTF-8
sonar.login=admin
sonar.password=admin
sonar.scm.disabled=true
sonar.scanner.skipJreProvisioning=true
EOF

    $SONAR_SCANNER \
        -Dsonar.scanner.skipJreProvisioning=true \
        -Dproject.settings=/tmp/sonar-project.properties \
        2>&1 | tail -5 || true

    # 3. Buscar issues via API REST (aguardar processamento background)
    log_info "Aguardando processamento do SonarQube..."
    for i in $(seq 1 20); do
        STATUS=$(curl -sf -u admin:admin "$SONAR_HOST/api/ce/component?component=${REPO_NAME}" 2>/dev/null \
            | python3 -c "import sys,json; print(json.load(sys.stdin).get('current',{}).get('status','PENDING'))" 2>/dev/null || echo "PENDING")
        if [ "$STATUS" = "SUCCESS" ]; then
            break
        fi
        sleep 3
    done

    log_info "Baixando issues do SonarQube..."
    for i in $(seq 1 10); do
        ISSUES_JSON=$(curl -sf -u admin:admin \
            "$SONAR_HOST/api/issues/search?componentKeys=${REPO_NAME}&types=CODE_SMELL,BUG,VULNERABILITY&ps=500" 2>/dev/null)
        ISSUE_COUNT=$(echo "$ISSUES_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null || echo "0")
        if [ "$ISSUE_COUNT" -gt 0 ] 2>/dev/null; then
            echo "$ISSUES_JSON" > "$OUTPUT_DIR/sonar_output.json"
            log_ok "SonarQube: $ISSUE_COUNT issues encontradas"
            break
        fi
        sleep 5
    done

    if [ ! -f "$OUTPUT_DIR/sonar_output.json" ]; then
        log_warn "SonarQube: 0 issues ou timeout. Salvando vazio."
        echo '{"total":0,"issues":[]}' > "$OUTPUT_DIR/sonar_output.json"
    fi
fi

# ──────────────────────────────────────────────────────────
# 6. Consolidação — mapear findings para snippets
# ──────────────────────────────────────────────────────────
section "Consolidação dos Resultados"

log_info "Mapeando findings das 5 ferramentas para snippets da Fase 2..."

python3 "$SCRIPT_DIR/fase3_consolidar.py" \
    --snippets "$SNIPPETS_JSON" \
    --phpmd "$OUTPUT_DIR/phpmd_output.json" \
    --phpstan "$OUTPUT_DIR/phpstan_output.json" \
    --psalm "$OUTPUT_DIR/psalm_output.json" \
    --phpcs "$OUTPUT_DIR/phpcs_output.json" \
    --sonar "$OUTPUT_DIR/sonar_output.json" \
    --repo-root "$REPO_DIR" \
    --output-json "$OUTPUT_DIR/pre_rotulacao.json" \
    --output-csv "$OUTPUT_DIR/pre_rotulacao.csv"

echo ""
log_ok "Fase 3 concluída com sucesso!"
echo ""
echo "Artefatos gerados em: $OUTPUT_DIR/"
echo "  ├── phpmd_output.json"
echo "  ├── phpstan_output.json"
echo "  ├── psalm_output.json"
echo "  ├── phpcs_output.json"
echo "  ├── sonar_output.json"
echo "  ├── pre_rotulacao.json     ← Dados consolidados"
echo "  └── pre_rotulacao.csv"
