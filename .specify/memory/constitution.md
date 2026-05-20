<!--
SYNC IMPACT REPORT
==================
Version change: 0.0.0 (template) → 1.0.0 (initial ratification)
Bump rationale: First concrete ratification; all placeholders replaced with
domain-specific content derived from AGENTS.md and the established research
methodology. MAJOR bump establishes the initial governance baseline.

Modified principles:
  - [PRINCIPLE_1_NAME]            → I. Reprodutibilidade via Docker (NÃO-NEGOCIÁVEL)
  - [PRINCIPLE_2_NAME]            → II. Integridade Metodológica (NÃO-NEGOCIÁVEL)
  - [PRINCIPLE_3_NAME]            → III. Pipeline Sequencial das Cinco Fases
  - [PRINCIPLE_4_NAME]            → IV. Stdlib Python e Métricas Auditáveis
  - [PRINCIPLE_5_NAME]            → V. Documentação em pt-BR e Rastreabilidade

Added sections:
  - Restrições Técnicas e Padrões de Qualidade
  - Fluxo de Desenvolvimento e Anotação Humana
  - Governança

Removed sections:
  - None (template placeholders replaced in place)

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md       (Constitution Check gates align;
                                                  no edits required)
  - ✅ .specify/templates/spec-template.md       (Generic Spec-Kit scaffold; no
                                                  conflicts with principles)
  - ✅ .specify/templates/tasks-template.md      (Test tasks remain OPTIONAL —
                                                  consistent with "sem suíte de
                                                  testes" principle)
  - ✅ .specify/templates/checklist-template.md  (Generic; no conflicts)
  - ⚠ AGENTS.md                                  (Authoritative operational doc;
                                                  keep in sync if principles
                                                  evolve)
  - ⚠ docs/guia_docker.md, docs/fases/*          (Reference these principles
                                                  when amended)

Follow-up TODOs:
  - None. RATIFICATION_DATE set to 2026-05-13 (data da validação end-to-end
    registrada em AGENTS.md).
-->

# Dataset PHP Code Smells Constitution

## Core Principles

### I. Reprodutibilidade via Docker (NÃO-NEGOCIÁVEL)

Toda execução do pipeline (Fases 1 a 5, consolidação de anotações, desempate)
DEVE rodar dentro do container Docker definido pelo `Dockerfile` e orquestrado
pelo `docker-compose.yml` / `Makefile`. Nenhum comando do pipeline DEVE assumir
ferramentas instaladas no host além de `docker`, `docker compose` e `make`.

- Antes de qualquer execução: `make build` (ou rebuild explícito quando
  `Dockerfile` ou `config/composer.json` mudarem).
- `scripts/` é bind-mount: edições no host refletem no container sem rebuild —
  preservar essa propriedade ao alterar `docker-compose.yml`.
- Ferramentas externas (PHPMD, PHPStan, Psalm, PHPCS, SonarQube Scanner) DEVEM
  estar pré-baixadas em `/tools` na imagem; o script `fase3` pode baixar em
  runtime apenas como fallback.

**Racional**: pesquisa de doutorado exige resultados reproduzíveis por
terceiros e por revisores ao longo de anos. Ambiente fixo elimina deriva.

### II. Integridade Metodológica (NÃO-NEGOCIÁVEL)

Parâmetros metodológicos fixados pela pesquisa NÃO PODEM ser alterados sem
justificativa formal escrita e bump MAJOR da constituição.

Parâmetros protegidos:
- Threshold de deduplicação Jaccard ≥ **0.80**.
- Frequência mínima de smell para inclusão no dataset = **3%**.
- Ordem obrigatória das fases: `1 → 2 → 3 → 4 → 5` (dependências unidirecionais).
- Critérios de votação por maioria na consolidação (Smelly > Potentially > Clean
  em caso de empate, com `requires_review: true`).

Qualquer PR que toque esses números DEVE incluir: (a) justificativa metodológica,
(b) referência bibliográfica ou validação empírica, (c) atualização do AGENTS.md.

**Racional**: thresholds arbitrários comprometem validade estatística e
comparabilidade do dataset com a literatura.

### III. Pipeline Sequencial das Cinco Fases

Cada fase DEVE consumir exclusivamente artefatos produzidos pela fase anterior
e gravar suas saídas em `output/faseN/`. Nenhuma fase pode pular ou reordenar
etapas; nenhuma pode escrever fora de seu diretório de saída.

- Fase 1: seleção de repositórios via GitHub API → `output/fase1/`.
- Fase 2: extração de snippets + métricas (PHP AST via `nikic/php-parser`) →
  `output/fase2/snippets_com_metricas.json`.
- Fase 3: análise estática (5 ferramentas + SonarQube Community local) →
  `output/fase3/`.
- Fase 4: interface HTML autocontida de anotação humana → `output/fase4/`.
- Fase 5: deduplicação, filtros, validação estatística, CSV final →
  `output/fase5/`.

Toda nova funcionalidade DEVE ser mapeada a uma fase existente OU justificar
explicitamente a criação de uma sub-fase auxiliar (ex.: `consolidar_anotacoes`,
`aplicar_desempate`) sem quebrar a ordem principal.

**Racional**: separação clara permite re-execução parcial, auditoria por fase
e paralelismo seguro.

### IV. Stdlib Python e Métricas Auditáveis

Scripts Python DEVEM usar apenas a stdlib. Exceções permitidas, explicitamente
documentadas:
- `requests` em `scripts/fase1_selecionar_repositorio.py` (chamadas à GitHub API).

NÃO É PERMITIDO introduzir `numpy`, `pandas`, `scipy`, `scikit-learn` ou
bibliotecas equivalentes. Métricas de Halstead, Complexidade Ciclomática e
Similaridade de Jaccard DEVEM permanecer implementadas à mão, em código legível
e revisável linha-a-linha.

Critérios de aceitação para novas métricas:
- Implementação direta em Python puro ou PHP (conforme a fase).
- Comentários explicando a fórmula e referência da literatura.
- Saída determinística (sem dependência de seeds aleatórias não controladas).

**Racional**: auditabilidade científica. Revisores devem conseguir reproduzir
e validar cada cálculo sem instalar um stack de ML opaco.

### V. Documentação em pt-BR e Rastreabilidade

Toda documentação interna, comentários de código relevantes para a metodologia,
mensagens de log voltadas ao pesquisador e specs (`specs/`, `.specify/`) DEVEM
ser escritos em **português brasileiro (pt-BR)**. Identificadores de código
(funções, variáveis) permanecem em inglês quando essa for a convenção da
linguagem ou da biblioteca.

Rastreabilidade obrigatória:
- Cada execução de fase grava metadados (timestamp, repo, contagens) em seu
  JSON de saída.
- Cada bug corrigido pós-validação DEVE ser registrado na seção "Bugs
  corrigidos" do `AGENTS.md` com data e arquivo afetado.
- Anotações de múltiplos avaliadores DEVEM preservar `votes_per_annotator`,
  `agreement_rate` e `resolution` no JSON consolidado.

**Racional**: a tese, defesa e revisões por pares ocorrem em pt-BR; rastros
explícitos sustentam reivindicações empíricas.

## Restrições Técnicas e Padrões de Qualidade

- **Sem suíte de testes automatizados, sem lint, sem CI.** "Validação" no
  contexto deste projeto refere-se à validação estatística do dataset
  produzido pela Fase 5, não a testes unitários de software.
- **Sem dependências de Composer além das declaradas em `config/composer.json`**.
  Atualmente: `nikic/php-parser`.
- **PHP 8.2** é a versão alvo do container. Código PHP NÃO DEVE usar
  funcionalidades de versões mais recentes nem depender de extensões fora das
  habilitadas no `Dockerfile`.
- **Tokens e segredos** (`GITHUB_TOKEN`) vivem apenas em `.env` (não commitado).
  Nenhum script pode logar tokens em stdout/stderr.
- **Outputs determinísticos** quando possível: ordenação estável de listas,
  serialização JSON com `sort_keys=True` para diffs limpos entre execuções.
- **Bind-mount preservado**: `scripts/` e `output/` montados do host. Não mover
  para dentro da imagem.

## Fluxo de Desenvolvimento e Anotação Humana

**Desenvolvimento**:
1. Alterações em scripts (`scripts/*.py`, `scripts/*.php`, `scripts/*.sh`)
   refletem no container sem rebuild.
2. Alterações em `Dockerfile`, `config/composer.json`, `docker-compose.yml`
   exigem `make build`.
3. Toda mudança que afete uma fase DEVE ser exercitada com pelo menos um
   repositório de referência (ex.: `FakerPHP/Faker`) e os números esperados
   da tabela em AGENTS.md DEVEM ser confirmados ou atualizados.

**Anotação humana (Fase 4)**:
1. Anotadores trabalham em paralelo, cada um em seu navegador
   (`localStorage` chaveado por nome de repo).
2. Exportar JSON individual ao concluir.
3. Consolidar com `scripts/consolidar_anotacoes.py` por **maioria simples**;
   smells mantidos com ≥2 votos quando há ≥3 anotadores, ou ≥1 quando há 1.
4. Casos `requires_review` resolvidos via HTML de desempate por um 4º revisor
   (`revisao_desempate.html`) e aplicados com `aplicar_desempate.py`
   (`resolution: human_tiebreak`, preservando `label_before_tiebreak`).
5. JSON final alimenta a Fase 5 via `--annotations`.

**Critérios de qualidade da anotação**:
- Notas dos anotadores são preservadas concatenadas com ` | ` (deduplicadas).
- Conflitos não podem ser resolvidos por inferência automática que vá além
  das regras acima — sempre intervenção humana documentada.

## Governança

Esta constituição supera convenções tácitas e quaisquer práticas individuais
de contribuidores. Em caso de conflito entre esta constituição e outros
documentos (`AGENTS.md`, `README.md`, `docs/`), **prevalece esta constituição**;
os demais documentos devem ser atualizados para alinhar.

**Política de versionamento (SemVer aplicado à constituição)**:
- **MAJOR**: remoção ou redefinição incompatível de princípio; alteração de
  threshold metodológico protegido (Princípio II); mudança na ordem das fases.
- **MINOR**: adição de princípio ou seção; expansão material de orientação
  existente; novas restrições não-negociáveis.
- **PATCH**: esclarecimentos de redação, correções tipográficas, refinamentos
  não-semânticos.

**Procedimento de emenda**:
1. Abrir alteração em PR (ou commit direto em ramo de trabalho) explicitando:
   versão antiga → nova, princípios afetados, racional metodológico.
2. Atualizar o Sync Impact Report no topo deste arquivo.
3. Propagar para templates de spec/plan/tasks/checklist e para `AGENTS.md`
   conforme necessário.
4. Confirmar em pelo menos uma execução end-to-end (ex.: FakerPHP/Faker) que
   o pipeline ainda produz os números esperados — ou atualizar a tabela de
   referência justificadamente.

**Revisão de conformidade**: toda alteração de código em `scripts/`, `config/`
ou `Dockerfile` DEVE ser revisada quanto à conformidade com os Princípios I-V
antes do merge. Justificativas para desvios pontuais ficam registradas no
próprio commit/PR.

**Guia operacional em tempo de execução**: consultar `AGENTS.md` para comandos,
diretórios e armadilhas conhecidas. Esta constituição define o "por quê" e o
"o que é inegociável"; o AGENTS.md descreve o "como" no dia-a-dia.

**Version**: 1.0.0 | **Ratified**: 2026-05-13 | **Last Amended**: 2026-05-20
