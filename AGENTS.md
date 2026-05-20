# AGENTS.md

Pesquisa de doutorado: pipeline para construir um dataset anotado de *code smells* em PHP. Projeto Dockerizado — todos os comandos rodam via container. Não há suíte de testes, lint ou CI.

Toda a documentação interna está em **português (pt-BR)**.

## Fases do pipeline (ordem obrigatória)

`Fase 1 (metadados via GitHub API) → Fase 2 (extração de snippets + métricas, PHP AST) → Fase 3 (análise estática: PHPMD, PHPStan, Psalm, PHPCS, SonarQube Scanner) → Fase 4 (interface HTML de anotação humana) → Fase 5 (deduplicação Jaccard ≥0.80, filtros, validação estatística, CSV final)`

- Fase 2 depende de `nikic/php-parser` (Composer em `config/`).
- Fase 3 (`scripts/fase3_analise_estatica.sh`) baixa as PHARs em runtime. No Docker já vêm pré-baixadas em `/tools`. Inclui servidor SonarQube Community local (sobe via docker-compose, acessível em `http://localhost:9000`).
- Fase 4 gera um HTML autocontido com os snippets da Fase 2 + pré-rótulos da Fase 3 — abrir no navegador, exportar JSON/CSV de anotações.
- Fase 5 consome o JSON da Fase 4 via `--annotations`; sem ele, usa pré-rótulos da Fase 3 como fallback.

## Comandos principais (tudo via Docker)

```bash
# Build da imagem (obrigatório antes de rodar qualquer fase)
make build

# Pipeline completo (1 repo)
make run REPO=FakerPHP/Faker

# Fases individuais
REPO=FakerPHP/Faker docker compose --profile fase1 up fase1
docker compose --profile fase2 up fase2
docker compose --profile fase3 up fase3
docker compose --profile fase4 up fase4
docker compose --profile fase5 up fase5

# Batch: selecionar N repos automaticamente
docker compose run --rm shell python3 scripts/fase1_selecionar_repositorio.py --auto-select 5

# Shell interativo (scripts bind-mounted, sem rebuild)
docker compose run --rm shell bash

# Interface Fase 4
make interface INTERFACE_PORT=9090

# Fase 5 com anotações manuais
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
  --annotations output/fase4/anotacoes_final.json --output output/fase5
```

`GITHUB_TOKEN` em `.env` (evita rate-limit da API). `scripts/` é bind-mount — editar no host reflete no container sem rebuild.

## Fluxo com múltiplos anotadores (N devs)

A interface Fase 4 não é colaborativa — cada anotador trabalha sozinho no próprio navegador (anotações ficam em `localStorage` chaveado pelo nome do repo). Para consolidar:

1. Cada dev clica em **📥 Exportar JSON** na interface.
2. Reúna todos os arquivos em `output/fase4/` (ex.: `anotacoes_dev1.json`, `anotacoes_dev2.json`, ...).
3. Rode `scripts/consolidar_anotacoes.py` por votação de maioria:
   ```bash
   docker compose run --rm shell python3 scripts/consolidar_anotacoes.py \
     output/fase4/anotacoes_dev{1,2,3}.json \
     --output output/fase4/anotacoes_consolidadas.json \
     --snippets-data output/fase4/dados_integrados.json \
     --review-html output/fase4/revisao_desempate.html
   ```
4. Se houver casos `requires_review`, abra `revisao_desempate.html` no navegador (4º revisor), clique em **📥 Exportar JSON Final** e aplique:
   ```bash
   docker compose run --rm shell python3 scripts/aplicar_desempate.py \
     --consolidado output/fase4/anotacoes_consolidadas.json \
     --desempate desempate_2026-05-13.json \
     --output output/fase4/anotacoes_final.json
   ```
5. Passe o arquivo final para a Fase 5: `--annotations output/fase4/anotacoes_final.json`.

**Regras de consolidação:**
- Label: maioria simples. Empate → prioridade `smelly > potentially_smelly > clean` e marca `requires_review: true`.
- Smells: mantidos se ≥2 anotadores apontaram (≥3 anotadores) ou ≥1 (1 anotador).
- Notas: concatenadas com ` | ` (deduplicadas).
- Campos: `agreement_rate`, `resolution`, `all_votes`, `votes_per_annotator`, `requires_review`.

**HTML de desempate:** standalone (CDN highlight.js), persiste em `localStorage`, mostra código + voto individual de cada dev. Saída JSON aplicado via `aplicar_desempate.py` (marca `resolution: human_tiebreak`, preserva `label_before_tiebreak`).

## Diretórios

- `scripts/` — scripts Python/PHP/Bash das 5 fases + consolidação + desempate (bind-mount no container)
- `config/` — `composer.json` (nikic/php-parser) + regras PHPMD/PHPCS
- `docker/` — scripts auxiliares (`docker-setup.sh`, `docker-run-all.sh`, etc.)
- `output/` — dados gerados (fase1 a fase5)
- `repos/` — repositórios clonados
- `.env` — `GITHUB_TOKEN` (não commitável)

## Convenções e armadilhas

- **Sem testes automatizados.** "Validação" refere-se à validação estatística do dataset (Fase 5).
- **Sem git** (`Is directory a git repo: false`). Não use `git status`/`git log`.
- Scripts Python usam **stdlib pura** (sem numpy/pandas) — preservar essa restrição. Exceção: `fase1_selecionar_repositorio.py` usa `requests`.
- Métricas Halstead, CC e Jaccard implementadas à mão — não introduzir libs externas.
- Threshold Jaccard = 0.80 e frequência mínima de smell = 3% são fixos por metodologia. Não mexer sem justificativa.
- `scripts/` é bind-mount: edições no host valem no container sem rebuild. Editar `Dockerfile` ou `config/composer.json` ainda exige `make build`.
- Interface Fase 4: `localStorage` chaveado por nome do repo. Auto-save, import JSON, export CSV. Linhas numeradas com highlight de smells clicáveis.

## Bugs corrigidos (2026-05-13, validação end-to-end)

1. **`docker-compose.yml`** — `python -c` multilinha sob YAML `>` → `IndentationError`. Corrigido com `jq`.
2. **`scripts/fase2_extrair_snippets.php:448`** — `fprintf` com `%` literal no PHP 8 → `fwrite`.
3. **`Dockerfile`** — `tokenizer` em `docker-php-ext-install` (built-in no PHP 8.2) removido.

**Diagnóstico de outputs vazios:**
```bash
docker logs codesmell-fase2 2>&1 | head -20
jq '.metadata.total_snippets' output/fase2/snippets_com_metricas.json
ls repos/
```

## Execução validada (FakerPHP/Faker, 2026-05-13)

| Fase | Esperado |
|---|---|
| 2 | 509 snippets (157 class + 351 method + 1 function), 666 arquivos, 0 erros |
| 3 | 7358 findings, 1869 mapeados; 363 clean / 78 potentially / 68 smelly |
| 5 | 409 registros, 40 colunas, 7 categorias |

## Referências

- `docs/guia_docker.md` — guia completo de execução com Docker
- `docs/fases/` — documentação técnica detalhada de cada fase do pipeline
- `Makefile` — `make help` lista todos os comandos disponíveis

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
