# Colunas do `dataset_final.csv`

47 colunas no total.

---

## Identificação

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 1 | A | `snippet_id` | string | Identificador único do snippet (`SNIPPET_0001`, …) |
| 2 | B | `repo` | string | Nome do repositório GitHub (`fakerphp/faker`) |
| 3 | C | `file_path` | string | Caminho relativo do arquivo dentro do repositório |
| 4 | D | `snippet_type` | string | Tipo: `class`, `method` ou `function` |
| 5 | E | `snippet_name` | string | Nome da classe, método ou função extraída |
| 6 | F | `start_line` | int | Linha inicial do snippet no arquivo original |
| 7 | G | `end_line` | int | Linha final do snippet no arquivo original |

---

## Métricas de LOC

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 8 | H | `loc_total` | int | Linhas totais (inclui comentários e linhas em branco) |
| 9 | I | `loc_blank` | int | Linhas em branco |
| 10 | J | `loc_comment` | int | Linhas de comentário |
| 11 | K | `loc_executable` | int | Linhas com lógica executável (exclui comentários/branco) |

---

## Complexidade

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 12 | L | `cyclomatic_complexity` | float | Complexidade ciclomática (McCabe): número de caminhos independentes |
| 13 | M | `nesting_depth` | int | Profundidade máxima de aninhamento de estruturas (`if`, `for`, etc.) |

---

## Métricas Halstead

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 14 | N | `halstead_vocabulary` | int | Vocabulário: operadores únicos + operandos únicos |
| 15 | O | `halstead_length` | int | Comprimento: total de operadores + operandos |
| 16 | P | `halstead_volume` | float | Volume: tamanho cognitivo do snippet |
| 17 | Q | `halstead_difficulty` | float | Dificuldade: esforço para escrever/compreender |
| 18 | R | `halstead_effort` | float | Esforço: volume × dificuldade |
| 19 | S | `halstead_time` | float | Tempo estimado de implementação (segundos) |
| 20 | T | `halstead_bugs` | float | Número estimado de defeitos (Halstead) |

---

## Estrutura PHP

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 21 | U | `num_methods` | int | Número de métodos (para snippets tipo `class`) |
| 22 | V | `num_properties` | int | Número de atributos/propriedades (para `class`) |
| 23 | W | `parent_class` | string | Nome da classe pai (herança), se houver |
| 24 | X | `implements` | string | Interfaces implementadas, separadas por vírgula |
| 25 | Y | `is_abstract` | bool | Se a classe ou método é abstrato |
| 26 | Z | `num_parameters` | int | Número de parâmetros na assinatura (para métodos/funções) |
| 27 | AA | `return_type` | string | Tipo de retorno declarado (para métodos/funções) |

---

## Anotação — Rótulo final

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 28 | AB | `label` | string | Rótulo final: `smelly` ou `clean` |
| 29 | AC | `label_confidence` | string | Confiança do pré-rótulo automático: `high`, `medium` ou `low` |
| 30 | AD | `label_source` | string | Origem do rótulo: `manual` (especialistas) ou `automatic` (ferramentas) |

---

## Anotação — Consolidação humana

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 31 | AE | `annotators_count` | int | Quantos revisores humanos anotaram este snippet |
| 32 | AF | `agreement_rate` | float | Taxa de concordância no label entre revisores (0.0–1.0) |
| 33 | AG | `resolution` | string | Como o label foi resolvido: `consensus` (unanimidade), `majority` (maioria), `tie_broken` (desempate automático) ou `human_tiebreak` (4º revisor) |
| 34 | AH | `notes` | string | Comentários dos revisores concatenados com ` \| `, incluindo justificativa do desempate |

---

## Smells — Ferramentas automáticas (Fase 3)

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 35 | AI | `smells_detected` | JSON | Lista de smells brutos detectados por PHPMD, PHPStan, Psalm, PHPCS, SonarQube |
| 36 | AJ | `total_smells_count` | int | Total de ocorrências de smell detectadas pelas ferramentas |
| 37 | AK | `tools_that_detected` | JSON | Lista das ferramentas que detectaram ao menos 1 smell |
| 38 | AL | `tool_agreement_count` | int | Quantas ferramentas concordaram em pelo menos 1 smell |

---

## Smells — Decisão final

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 39 | AM | `unique_smell_categories` | JSON | Lista final de categorias de smell. Origem: especialistas (se `label_source=manual`) ou ferramentas (se `automatic`) |

---

## Smells — Metadados da consolidação humana

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 40 | AN | `smell_counts` | JSON | Dicionário `{categoria: n_votos}` — quantos revisores apontaram cada smell |
| 41 | AO | `smell_agreement` | JSON | Dicionário `{categoria: taxa}` — concordância por smell (0.0–1.0) |
| 42 | AP | `disputed_smells` | JSON | Lista de smells com divergência (selecionados por ≥1 revisor, abaixo do threshold de ≥2) |

---

## Metadados do repositório

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 43 | AQ | `repo_stars` | int | Estrelas do repositório no GitHub |
| 44 | AR | `repo_forks` | int | Forks do repositório |
| 45 | AS | `repo_license` | string | Licença (ex.: `MIT`) |
| 46 | AT | `repo_category` | string | Categoria inferida: `framework`, `library/utility`, `cms/ecommerce` |

---

## Código-fonte

| # | Col | Coluna | Tipo | Descrição |
|---|-----|--------|------|-----------|
| 47 | AU | `code` | string | Código-fonte completo do snippet (PHP) |
