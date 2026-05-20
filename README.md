# Pipeline Automatizado para Construção de Dataset Anotado de *Code Smells* em PHP

> Uma abordagem multi-ferramenta com validação humana — pesquisa de doutorado.

Este repositório contém o pipeline reproduzível, em 5 fases, para construir um
**dataset anotado de code smells em código PHP**. A coleta é automatizada
(metadados via GitHub API, métricas de AST, análise estática com cinco
ferramentas) e a rotulagem final passa por **revisão humana com consolidação
por votação de maioria**.

Toda a execução roda em **Docker**: não é preciso instalar PHP, Python ou
ferramentas estáticas no host.

---

## Sumário

- [Visão geral do pipeline](#visão-geral-do-pipeline)
- [Pré-requisitos](#pré-requisitos)
- [Instalação rápida](#instalação-rápida)
- [Execução do pipeline (passo a passo)](#execução-do-pipeline-passo-a-passo)
  - [Fase 1 — Seleção do repositório](#fase-1--seleção-do-repositório)
  - [Fase 2 — Extração de snippets](#fase-2--extração-de-snippets-requer-fase-1)
  - [Fase 3 — Análise estática](#fase-3--análise-estática-requer-fases-1-e-2)
  - [Fase 4.1 — Geração da interface de anotação](#fase-41--geração-da-interface-de-anotação-requer-fases-2-e-3)
  - [Fase 4.2 — Anotação humana](#fase-42--anotação-humana)
  - [Fase 4.3 — Consolidação de anotações](#fase-43--consolidação-de-anotações-de-três-revisores)
  - [Fase 4.3.1 — Página de desempate](#fase-431--criar-página-de-desempate-opcional)
  - [Fase 4.4 — Revisão de desempate](#fase-44--revisão-de-desempate)
  - [Fase 4.5 — Aplicar desempate](#fase-45--aplicar-desempate-e-gerar-anotações-finais)
  - [Fase 5 — Validação e dataset final](#fase-5--validação-e-dataset-final)
- [Estrutura de diretórios](#estrutura-de-diretórios)
- [Comandos auxiliares (Makefile)](#comandos-auxiliares-makefile)
- [Documentação adicional](#documentação-adicional)
- [Licença](#licença)

---

## Visão geral do pipeline

```
Fase 1 ──▶ Fase 2 ──▶ Fase 3 ──▶ Fase 4 ──▶ Fase 5
metadados   snippets   análise    anotação   dataset
GitHub API  + métricas estática   humana     final (CSV)
            (AST PHP)  (5 tools)  (HTML)
```

| Fase | Entrada | Saída principal |
|------|---------|-----------------|
| 1 | `REPO=owner/name` | `output/fase1/repositorio_metadata.json` |
| 2 | Fase 1 + clone do repo | `output/fase2/snippets_com_metricas.json` |
| 3 | Fase 2 | `output/fase3/pre_rotulacao.json` |
| 4 | Fases 2 + 3 | `output/fase4/anotacoes_final.json` |
| 5 | Fases 1–4 | `output/fase5/*.csv` |

Detalhes técnicos de cada fase: `docs/fases/fase_1.md` … `docs/fases/fase_5.md`.

---

## Pré-requisitos

- **Docker** e **Docker Compose** instalados e funcionando.
- Acesso de leitura ao repositório alvo no GitHub.
- Arquivo `.env` na raiz contendo `GITHUB_TOKEN=...` (evita rate-limit da API
  do GitHub). Use `.env.exemple` como modelo.

> Configuração completa do ambiente: `docs/guia_docker.md`.

---

## Instalação rápida

```bash
# 1. Clonar o repositório
git clone <url-do-repo> dataset-php
cd dataset-php

# 2. Configurar o token do GitHub
cp .env.exemple .env
# edite .env e preencha GITHUB_TOKEN=seu_token_aqui

# 3. Construir a imagem Docker
make build
```

---

## Execução do pipeline (passo a passo)

Os comandos abaixo usam **FakerPHP/Faker** como repositório de exemplo (mesma
referência usada em `docs/validacao/fakerphp.md`). Para outro repositório,
substitua o valor de `REPO`.

### Fase 1 — Seleção do repositório

Coleta os metadados iniciais do repositório alvo via GitHub API.

```bash
REPO=FakerPHP/Faker docker compose --profile fase1 up fase1
```

---

### Fase 2 — Extração de snippets (requer Fase 1)

Extrai os snippets de código do repositório clonado e os enriquece com métricas
estáticas (Halstead, complexidade ciclomática, LOC) calculadas a partir da AST
PHP (`nikic/php-parser`).

```bash
docker compose --profile fase2 up fase2
```

---

### Fase 3 — Análise estática (requer Fases 1 e 2)

Roda as ferramentas de análise estática (PHPMD, PHPStan, Psalm, PHPCS,
SonarQube Scanner) sobre os snippets da Fase 2 e gera as **pré-rotulagens**
que orientarão a revisão humana.

```bash
docker compose --profile fase3 up fase3
```

---

### Fase 4.1 — Geração da interface de anotação (requer Fases 2 e 3)

Constrói o HTML autocontido com os snippets + pré-rótulos para revisão humana.

```bash
docker compose --profile fase4 up fase4
```

---

### Fase 4.2 — Anotação humana

Sobe o servidor web local com a interface de anotação. Por padrão, acessível
em `http://localhost:9090` (ajuste com `INTERFACE_PORT`).

```bash
INTERFACE_PORT=9090 docker compose --profile interface up interface
```

Cada revisor abre a interface no próprio navegador, anota os snippets e
clica em **📥 Exportar JSON** ao final. As anotações ficam em `localStorage`
e devem ser salvas em `output/fase4/` com nomes distintos por revisor
(ex.: `fase4_anotacoes_fakerphp_faker_dev_1.json`).

---

### Fase 4.3 — Consolidação de anotações de três revisores

Após cada revisor exportar seu JSON, consolide os três arquivos em um único
documento com votação por maioria simples. Garanta que os arquivos estejam
em `output/fase4/`.

```bash
docker compose run --rm shell python3 scripts/consolidar_anotacoes.py \
    output/fase4/fase4_anotacoes_fakerphp_faker_dev_1.json \
    output/fase4/fase4_anotacoes_fakerphp_faker_dev_2.json \
    output/fase4/fase4_anotacoes_fakerphp_faker_dev_3.json \
    --output output/fase4/anotacoes_consolidadas.json
```

A saída indica quantos casos foram resolvidos por maioria e quantos
permanecem como **empate** (`tie_broken > 0`). Se não houver empates, pule
direto para a [Fase 5](#fase-5--validação-e-dataset-final).

---

### Fase 4.3.1 — Criar página de desempate (opcional)

> **Necessário apenas se a consolidação indicar `tie_broken > 0`.**

Gera um HTML de revisão para um **4º revisor** decidir os casos divergentes.
Os arquivos de anotação dos revisores e `dados_integrados.json` devem estar
em `output/fase4/`.

```bash
docker compose run --rm shell python3 scripts/consolidar_anotacoes.py \
  output/fase4/fase4_anotacoes_fakerphp_faker_dev_{1,2,3}.json \
  --output output/fase4/anotacoes_consolidadas.json \
  --snippets-data output/fase4/dados_integrados.json \
  --review-html output/fase4/revisao_desempate.html
```

---

### Fase 4.4 — Revisão de desempate

Com o servidor da Fase 4.2 ainda rodando:

1. Acesse `http://localhost:9090/revisao_desempate.html`.
2. Para cada caso de empate, escolha a anotação correta com base no código
   e nos votos individuais exibidos.
3. Clique em **📥 Exportar JSON Final** para baixar o arquivo de decisões.
4. Mova o `desempate_*.json` para `output/fase4/`.

---

### Fase 4.5 — Aplicar desempate e gerar anotações finais

Aplica as decisões do desempate sobre o JSON consolidado, produzindo o
`anotacoes_final.json` consumido pela Fase 5.

```bash
docker compose run --rm shell python3 scripts/aplicar_desempate.py \
  --consolidado output/fase4/anotacoes_consolidadas.json \
  --desempate output/fase4/desempate_*.json \
  --output output/fase4/anotacoes_final.json
```

---

### Fase 5 — Validação e dataset final

Fase final do pipeline. Integra todos os artefatos (metadados, snippets +
métricas, pré-rotulagens, anotações humanas finais), aplica deduplicação por
similaridade de Jaccard (limiar **≥ 0.80**), filtros estatísticos (frequência
mínima de smell **3%**) e gera o **CSV anotado final**.

```bash
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
  --fase1 output/fase1/repositorio_metadata.json \
  --fase2 output/fase2/snippets_com_metricas.json \
  --fase3 output/fase3/pre_rotulacao.json \
  --annotations output/fase4/anotacoes_final.json \
  --output output/fase5 2>&1 | tail -40
```

Saída em `output/fase5/` (dataset CSV + relatório estatístico).

> Referência de colunas do CSV final: `docs/referencia/colunas_csv.md`.

---

## Estrutura de diretórios

```
.
├── scripts/        # Scripts Python/PHP/Bash das 5 fases (bind-mount no container)
├── config/         # composer.json + regras PHPMD/PHPCS
├── docker/         # Scripts auxiliares de Docker
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── interface/      # Templates/assets da interface de anotação
├── output/         # Saídas geradas (fase1 a fase5) — bind-mount
├── repos/          # Repositórios clonados
├── docs/
│   ├── guia_docker.md            # Guia completo de execução com Docker
│   ├── fases/                    # Documentação técnica de cada fase
│   ├── referencia/               # Schemas (ex.: colunas_csv.md)
│   └── validacao/                # Casos de validação end-to-end
├── .env             # GITHUB_TOKEN (não commitar)
└── .specify/        # Spec-Kit (constituição + templates)
```

---

## Comandos auxiliares (Makefile)

```bash
make help            # Lista todos os comandos disponíveis
make build           # Constrói a imagem Docker
make run REPO=owner/name  # Executa o pipeline completo para um repo
make interface INTERFACE_PORT=9090  # Sobe apenas a interface de anotação
make shell           # Terminal interativo no container
make status          # Mostra containers, imagem e tamanho de output/
make clean           # Remove containers parados
make clean-all       # Remove tudo (containers, imagem, outputs/)
```

---

## Documentação adicional

- **`docs/guia_docker.md`** — pré-requisitos, configuração do `.env`, troubleshooting.
- **`docs/fases/fase_{1..5}.md`** — descrição técnica detalhada de cada fase.
- **`docs/referencia/colunas_csv.md`** — schema do dataset final.
- **`docs/validacao/fakerphp.md`** — caso de validação end-to-end com FakerPHP/Faker.
- **`AGENTS.md`** — guia operacional rápido para contribuidores e agentes.
- **`.specify/memory/constitution.md`** — princípios e governança do projeto.

---

## Licença

Distribuído sob a licença **MIT**. Veja `LICENSE` para detalhes.

© 2026 Charles de Azevedo Júnior — Pesquisa de Doutorado.
