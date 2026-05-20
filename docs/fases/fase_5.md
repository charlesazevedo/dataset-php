# Fase 5 — Validação, Deduplicação e Dataset Final

## Objetivo

A Fase 5 é o **ponto de fechamento** do pipeline. Sua responsabilidade é juntar tudo
que as fases anteriores produziram (metadados do repo, snippets com métricas,
pré-rótulos automáticos e — se disponível — anotações humanas), aplicar uma camada
final de controle de qualidade (deduplicação, filtros de exclusão, validação
estatística) e materializar o **dataset final** num único CSV pronto para análise,
publicação ou consumo por modelos de ML.

Em uma frase: a Fase 5 transforma "vários JSONs intermediários espalhados pelas
fases" em "um CSV auditável que é o produto científico do projeto".

Script: `scripts/fase5_validar_dataset.py` (Python 3, stdlib pura — sem pandas,
sem numpy, sem scipy; correlação ponto-bisserial implementada à mão).

---

## Etapas do processamento

```
1. Carregar Fase 1 (metadados do repo)
   Carregar Fase 2 (snippets + métricas)
   Carregar Fase 3 (pré-rotulação)
   Opcional: carregar JSON de anotações da Fase 4

2. Detecção de duplicatas (Jaccard ≥ 0.80)
   Mantém o snippet com mais smells; descarta o outro.

3. Filtros de exclusão pós-anotação
   - duplicatas (do passo 2)
   - código gerado (marcadores @generated etc.)
   - código muito curto (< 20 caracteres)
   - chaves {/} desbalanceadas (> 2 de diferença)

4. Dataset filtrado (kept_ids = snippets que sobreviveram)

5. Validação estatística
   - Distribuição de labels
   - Top 15 categorias de smell
   - Correlação ponto-bisserial entre métricas e has_smell

6. Geração do CSV final (47 colunas)

7. Relatório JSON consolidado (validation_report.json)
```

A fase é **single-pass**: carrega tudo na memória, processa em sequência, escreve
no disco. Mesmo para repos grandes (~500 snippets), termina em segundos.

---

## Resolução do rótulo final

A regra mais importante da Fase 5 é como ela decide o `label` de cada snippet no
CSV. Para cada `snippet_id` em `kept_ids`:

```python
if sid in manual_annotations:   # --annotations passado e snippet tem entrada
    label = manual_annotations[sid]["label"]
    label_source = "manual"
    smells_cats = manual_annotations[sid].get("smells", fallback_da_fase3)
else:
    label = fase3.snippets[sid]["pre_label"]
    label_source = "automatic"
    smells_cats = fase3.snippets[sid]["unique_smell_categories"]
```

Duas colunas no CSV deixam essa decisão auditável:

- `label` — o rótulo final.
- `label_source` — `manual` (humano decidiu na Fase 4) ou `automatic`
  (caiu no fallback da Fase 3).

Sem `--annotations`, **100%** dos snippets terão `label_source = automatic`. Com
anotações parciais, alguns serão `manual` e outros `automatic` — coerente com a
realidade do projeto.

> Nota metodológica: a Fase 4 só permite `smelly` ou `clean` na anotação humana.
> O `potentially_smelly` ainda aparece no CSV quando vem do fallback automático
> da Fase 3 (snippets que ficaram em zona cinzenta sem anotador humano).

---

## Detecção de duplicatas (Jaccard)

Implementação artesanal em ~30 linhas (`tokenize_code` + loop O(N²) com pré-filtro
de comprimento). Threshold metodológico: **0.80**, fixo (`AGENTS.md`).

### Tokenização

```python
def tokenize_code(code: str) -> set:
    return set(re.findall(r'[a-zA-Z_]\w*|\d+|[^\s\w]', code))
```

Captura três tipos de token:

- Identificadores: `[a-zA-Z_]\w*` (variáveis, nomes de função, palavras-chave).
- Números inteiros literais.
- Pontuação isolada: `[^\s\w]` (parênteses, operadores, ponto-e-vírgula).

Conjuntos (sem ordem nem repetição), o que é coerente com Jaccard.

### Cálculo e pré-filtro

```python
for a, b in pares(snippet_ids):
    a_tokens, b_tokens = token_sets[a], token_sets[b]
    # Pré-filtro: pula se diferença de tamanho já garante J < 0.80
    if min(|a|, |b|) / max(|a|, |b|) < 0.80:
        continue
    j = |a ∩ b| / |a ∪ b|
    if j >= 0.80:
        duplicate_pairs.append((a, b, j))
        # Mantém o que tem mais smells; remove o outro
        remove_id = b if smells(a) >= smells(b) else a
        duplicates_to_remove.add(remove_id)
```

O pré-filtro de comprimento é crítico: sem ele, o loop é O(N²) com cálculo de
intersecção de conjuntos em cada par; com ele, ~99% dos pares são descartados
em O(1).

### Política de remoção

Em cada par detectado, **um** dos dois snippets é removido. A heurística:

- Mantém o snippet com **mais** smells detectados (`total_smells_count` da Fase 3).
- Em empate, mantém o `a` (o de `snippet_id` lexicograficamente menor, pelo ordering).

Justificativa: snippets duplicados que diferem só em formatação raramente são
detectados pelos mesmos smells pelas 5 ferramentas (variações de linha mudam o
mapeamento). Manter o de maior cobertura preserva mais informação para a Fase 5
e para análises subsequentes.

---

## Filtros de exclusão pós-anotação

Quatro motivos podem excluir um snippet do dataset final. Um mesmo snippet pode
acumular múltiplos motivos (registrados em `exclusion_reasons[sid]`).

| Motivo               | Critério                                                          |
|----------------------|-------------------------------------------------------------------|
| `near_duplicate`     | Marcado como duplicata no passo anterior                          |
| `auto_generated`     | Regex `(?i)auto[-\s]?generated|do not (edit|modify)|generated by \w+|@generated` |
| `too_short`          | `len(code.strip()) < 20`                                          |
| `unbalanced_braces`  | `abs(code.count("{") - code.count("}")) > 2`                      |

A redundância com filtros da Fase 2 (que já exclui `auto_generated` e snippets
triviais via LOC/CC) é **intencional**: a Fase 5 olha o snippet **pós-anotação**,
e o anotador pode ter editado/cancelado anotações de coisas que escaparam dos
filtros estruturais. Também serve como segunda linha de defesa contra ruído.

---

## Validação estatística

Três análises descritivas no `stdout` (e replicadas no `validation_report.json`):

### 1. Distribuição de labels

```
clean: 363 (88.8%)
potentially_smelly: 22 (5.4%)
smelly: 24 (5.9%)
```

Útil para checar **balanceamento** do dataset. Se >95% for `clean`, o dataset
tem pouco sinal para modelos supervisionados — pode ser preciso revisar
critérios da Fase 3 ou amostrar repositórios mais "smelly".

### 2. Top 15 categorias de smell

Conta quantos snippets têm cada categoria em `unique_smell_categories` (manual ou
automático). Ajuda a identificar categorias muito raras (frequência < 3%) que
podem precisar ser agrupadas em `Other` antes de análises supervisionadas.

> O threshold de **3% de frequência mínima** por categoria é metodológico
> (registrado em `AGENTS.md`). A Fase 5 não filtra por isso, só reporta — a
> decisão de agrupar fica para o pesquisador na etapa de análise.

### 3. Correlação ponto-bisserial

Para cada métrica contínua, calcula `r_pb` e `p-value` contra a variável binária
`has_smell` (`1` se `label ∈ {smelly, potentially_smelly}`, `0` caso contrário):

| Métrica                  | Esperado    | Interpretação                              |
|--------------------------|-------------|--------------------------------------------|
| `loc_executable`         | r > 0       | métodos longos tendem a ter mais smells    |
| `cyclomatic_complexity`  | r > 0       | complexidade alta correlaciona com smell   |
| `nesting_depth`          | r > 0       | aninhamento profundo é smell por si só     |
| `halstead_volume`        | r > 0       | volume cognitivo correlaciona              |
| `halstead_difficulty`    | r > 0       | dificuldade idem                           |
| `halstead_effort`        | r > 0       | esforço idem                               |

Cálculo (stdlib):

```python
r_pb = (m_1 - m_0) / σ_total * sqrt(n_1 * n_0 / n²)
t_stat = r_pb * sqrt((n - 2) / (1 - r_pb²))
p_val = 2 * (1 - 0.5 * (1 + erf(|t_stat| / sqrt(2))))
```

Onde `m_1`/`m_0` são as médias da métrica para os grupos com/sem smell, e `σ_total`
é o desvio-padrão da métrica em todo o dataset. `p_val` usa aproximação normal
via `math.erf` (válida para `n` grande, suficiente para o uso descritivo).

**O que esperar:** correlações positivas e estatisticamente significativas
(`p < 0.05`) validam a hipótese de que as métricas escolhidas têm poder
discriminativo. Correlações próximas de zero indicam métricas redundantes ou
ruído na anotação.

---

## Saída em disco

```
output/fase5/
├── dataset_final.csv         # ★ produto final do projeto
└── validation_report.json    # auditoria completa da fase
```

### `dataset_final.csv` (40 colunas)

| Bloco                | Colunas                                                                                  |
|----------------------|------------------------------------------------------------------------------------------|
| Identidade           | `snippet_id`, `repo`, `file_path`, `snippet_type`, `snippet_name`, `start_line`, `end_line` |
| LOC                  | `loc_total`, `loc_blank`, `loc_comment`, `loc_executable`                                |
| Complexidade         | `cyclomatic_complexity`, `nesting_depth`                                                 |
| Halstead             | `halstead_vocabulary`, `halstead_length`, `halstead_volume`, `halstead_difficulty`, `halstead_effort`, `halstead_time`, `halstead_bugs` |
| Estrutura            | `num_methods`, `num_properties`, `parent_class`, `implements`, `is_abstract`, `num_parameters`, `return_type` |
| Rótulo               | `label`, `label_confidence`, `label_source`                                              |
| Smells               | `smells_detected` (JSON), `total_smells_count`, `unique_smell_categories` (JSON), `tools_that_detected` (JSON), `tool_agreement_count` |
| Contexto do repo     | `repo_stars`, `repo_forks`, `repo_license`, `repo_category`                              |
| Código               | `code` (texto completo do snippet)                                                       |

Notas sobre o CSV:

- Encoding UTF-8 sem BOM.
- `smells_detected`, `unique_smell_categories`, `tools_that_detected` ficam
  serializados como JSON dentro da célula. Para abrir em Pandas:
  `df["unique_smell_categories"] = df["unique_smell_categories"].apply(json.loads)`.
- `code` preserva quebras de linha (CSV "real", não achatado). Importadores
  precisam usar parser que respeite aspas com newlines internos (Python `csv`
  faz por default).
- `label_source` distingue anotação manual vs fallback automático (auditoria).

### `validation_report.json`

```json
{
  "timestamp": "2026-05-14T...",
  "phase": "Fase 5 — Validação e Controle de Qualidade",
  "input": { "total_snippets": 509 },
  "duplicate_detection": {
    "method": "Jaccard similarity on code tokens",
    "threshold": 0.80,
    "pairs_found": 12,
    "snippets_removed": 12
  },
  "exclusion_filters": {
    "total_excluded": 100,
    "reasons": {
      "near_duplicate": 12,
      "auto_generated": 4,
      "too_short": 89,
      "unbalanced_braces": 0
    }
  },
  "statistical_validation": {
    "dataset_size_after_filters": 409,
    "label_distribution": { "clean": 363, "smelly": 24, "potentially_smelly": 22 },
    "smell_category_distribution": { "Other": 88, "Complex Method": 56, "Dead Code": 23, "...": "..." },
    "point_biserial_correlations": {
      "loc_executable": { "rpb": 0.42, "p_value": 0.0001 },
      "cyclomatic_complexity": { "rpb": 0.58, "p_value": 0.0 },
      "nesting_depth": { "rpb": 0.31, "p_value": 0.0012 },
      "...": "..."
    }
  },
  "output": {
    "csv_path": "output/fase5/dataset_final.csv",
    "rows": 409,
    "columns": 40,
    "file_size_kb": 4287.3
  }
}
```

Esse JSON é o **comprovante metodológico** do dataset: todo número que aparece em
um paper deve ser reprodutível a partir deste relatório + os JSONs de entrada.

---

## Execução prática

```bash
# Pipeline completo (Fases 1–5)
make run REPO=FakerPHP/Faker

# Só a Fase 5 (assume Fases 1, 2 e 3 prontas; sem anotações humanas)
docker compose --profile fase5 up fase5

# Com anotações humanas exportadas da Fase 4 (1 anotador)
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
    --annotations output/fase4/fase4_anotacoes_FakerPHP_Faker_2026-05-14.json \
    --output output/fase5

# Com anotações consolidadas de N anotadores (fluxo completo)
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
    --annotations output/fase4/anotacoes_final.json \
    --output output/fase5

# Caminhos customizados de entrada
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
    --fase1 output/fase1/repositorio_metadata.json \
    --fase2 output/fase2/snippets_com_metricas.json \
    --fase3 output/fase3/pre_rotulacao.json \
    --annotations output/fase4/anotacoes_final.json \
    --output output/fase5
```

O wrapper Compose (`docker-compose.yml`, linhas 155–169) roda sem
`--annotations` por default — ou seja, **modo automático**. Para incluir
anotações humanas, use o `docker compose run --rm shell ...` manualmente.

---

## Execução validada (FakerPHP/Faker, 2026-05-13)

Números esperados em uma run sem anotações humanas (registrados em `AGENTS.md`):

| Métrica                            | Valor    |
|------------------------------------|----------|
| Snippets de entrada (Fase 3)       | 509      |
| Duplicatas removidas               | 12       |
| Excluídos no total                 | 100      |
|  → near_duplicate                  | 12       |
|  → too_short                       | 89       |
|  → auto_generated                  | 4        |
|  → unbalanced_braces               | 0        |
| Dataset final                      | 409 reg. |
| Colunas no CSV                     | 40       |
| Categorias de smell distintas      | 7        |

Notas:

- `total_excluded` soma motivos distintos por snippet; o N real removido pode ser
  menor (mesmo snippet com 2 motivos conta 2 vezes no `reasons`).
- Snippets com `too_short` que sobreviveram à Fase 2 indicam que o
  `loc_executable > 3` da Fase 2 não captura "código com poucas linhas mas
  muito branco" — a Fase 5 pega esses casos via `len(code.strip()) < 20`.

---

## Contrato com as fases anteriores

- **Fase 1 (`repositorio_metadata.json`):** fornece `repo_name`, `stars`,
  `forks`, `license`, `category` que vão para as colunas `repo_*` do CSV.
- **Fase 2 (`snippets_com_metricas.json`):** fornece toda a parte estrutural
  e métrica do CSV. **Sem isso, a Fase 5 falha.**
- **Fase 3 (`pre_rotulacao.json`):** fornece `pre_label`, `pre_label_confidence`,
  `code_smells_detected`, `unique_smell_categories`, `tools_that_detected`,
  `tool_agreement_count`. **Sem isso, a Fase 5 falha.** Em modo automático, é a
  fonte do `label` final.
- **Fase 4 (opcional, via `--annotations`):** se passado, sobrescreve `label` e
  `unique_smell_categories` com decisão humana e marca `label_source = manual`.

A Fase 5 é a única que **não tem fase seguinte**. Seu output é consumido por
ferramentas externas (Pandas, Excel, ML frameworks) ou citado direto no paper.

---

## Pontos de atenção e armadilhas conhecidas

1. **Threshold Jaccard fixo em 0.80.** Decisão metodológica registrada em
   `AGENTS.md`. Mudar exige justificativa documental — não é parâmetro
   ajustável "para ver o que dá".
2. **Frequência mínima de 3% por categoria.** Não é aplicada como filtro no
   script, apenas reportada. Quando for usar o dataset, considere agrupar
   categorias raras em `Other` ou usar técnicas robustas a classes
   desbalanceadas.
3. **Complexidade O(N²) da deduplicação.** Com pré-filtro de comprimento é
   tratável até ~5 mil snippets. Em datasets maiores (combinando vários repos)
   pode demorar minutos. Solução: pré-agrupar por hash do código antes do
   Jaccard.
4. **`label_source = manual` parcial.** Quando o anotador anotou apenas alguns
   snippets, o CSV mistura `manual` e `automatic`. Filtrar o dataset por
   `label_source = manual` antes de análises produz um subconjunto auditado
   por humanos.
5. **CSV com `code` completo.** O arquivo final fica grande (3–10 MB para ~400
   snippets). Para inspeção rápida, o `repo_*`/`metrics`/`label` já são
   suficientes; o `code` só importa para ML / análise textual.
6. **`has_smell` na correlação inclui `potentially_smelly`.** O cálculo
   considera `smelly` **e** `potentially_smelly` como positivos. Para análise
   com 2 classes estritas, refaça a correlação pós-filtragem.
7. **Sem anotações humanas, o "dataset" é heurística pura.** A Fase 5 funciona,
   mas o `label` é o pré-rótulo da Fase 3 — útil para validação preliminar e
   bootstrap, não para publicação como "gold standard". Para isso, a Fase 4
   é obrigatória.
8. **`metadata_repo` é de um único repositório.** O script assume um repo por
   execução. Para datasets multi-repo, rode a Fase 5 N vezes (uma por repo) e
   concatene os CSVs com `cat` ou `pandas.concat()` — as colunas são as mesmas.
9. **`smells_detected` no CSV é o da Fase 3.** Mesmo quando o anotador
   discordou de smells específicos na Fase 4, a coluna `smells_detected`
   guarda os findings originais das ferramentas (auditoria). Apenas
   `unique_smell_categories` reflete a decisão humana.
10. **`erf` para p-value.** A aproximação normal é precisa o suficiente para
    `n > 30`. Em subamostras pequenas (filtrando por categoria específica),
    use `scipy.stats.pointbiserialr` para resultado exato — a Fase 5 mantém
    stdlib pura por restrição metodológica.
