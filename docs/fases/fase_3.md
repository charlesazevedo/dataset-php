# Fase 3 — Análise Estática Multi-Ferramenta e Pré-Rotulação

## Objetivo

A Fase 3 é o **motor de pré-rotulação automática** do pipeline. Sua responsabilidade
é rodar cinco ferramentas independentes de análise estática sobre o código-fonte do
repositório clonado, mapear cada finding ao snippet correspondente (produzido pela
Fase 2) e, com base na concordância entre ferramentas, atribuir um **pré-rótulo**
(`smelly`, `potentially_smelly` ou `clean`) que será apresentado ao anotador humano
na Fase 4 e usado como fallback pela Fase 5 quando não houver anotação manual.

Em uma frase: a Fase 3 traduz "milhares de findings desestruturados de 5 ferramentas
diferentes" em "um rótulo provisório por snippet, com nível de confiança".

Scripts envolvidos:

- `scripts/fase3_analise_estatica.sh` — orquestrador Bash. Localiza ferramentas,
  executa cada uma, lida com falhas, fala com o SonarQube e dispara a consolidação.
- `scripts/fase3_consolidar.py` — coletor Python. Faz o parsing dos JSONs brutos,
  mapeia findings para snippets, classifica smells em categorias, aplica as regras
  de pré-rotulação e exporta `pre_rotulacao.json` + `pre_rotulacao.csv`.

---

## As cinco ferramentas

Cada ferramenta cobre um ângulo complementar da qualidade de código PHP. Usar várias
e exigir concordância reduz falso-positivo e melhora a confiança do pré-rótulo.

| Ferramenta            | Foco principal                                          | Como é invocada                          | Output bruto                  |
|-----------------------|---------------------------------------------------------|------------------------------------------|-------------------------------|
| **PHPMD**             | Mess Detector: complexidade, código morto, naming       | PHAR ou binário do PATH                  | `phpmd_output.json`           |
| **PHPStan** (level 5) | Análise de tipos, erros lógicos, contratos              | PHAR/binário                             | `phpstan_output.json`         |
| **Psalm**             | Análise estática rigorosa, null-safety, tipos genéricos | PHAR/binário (com config `errorLevel=2`) | `psalm_output.json`           |
| **PHPCS**             | Estilo, métricas leves (line length, nesting)           | PHAR/binário com ruleset XML             | `phpcs_output.json`           |
| **SonarQube Scanner** | Engine completa (issues + métricas) via servidor local  | Scanner local + API REST                 | `sonar_output.json`           |

PHPMD/PHPStan/Psalm/PHPCS são localizados pela função `find_tool()` em três níveis:

1. Binário no `PATH` (`command -v`).
2. PHAR pré-baixada em `tools/<nome>.phar` (já vem no container Docker).
3. Vendor do Composer (`config/vendor/bin/<nome>`).

Se nenhum for encontrado, o script registra `log_fail` e grava um JSON vazio
("estrutura mínima válida") para que o consolidador não quebre.

---

## Configuração específica de cada ferramenta

### PHPMD
- **Regras:** `config/phpmd_rules.xml` se existir; senão `cleancode,codesize,design,naming,unusedcode,controversial`.
- **Diretório analisado:** `<repo_dir>/src`.
- **Exclusões:** `vendor`, `tests`, `test`, `node_modules`.

### PHPStan
- **Nível:** `--level=5` (equilíbrio rigor × ruído).
- **Limite de memória:** `--memory-limit=1G`.
- **Diretório analisado:** `<repo_dir>/src`.

### Psalm
- **Configuração:** prefere `psalm.xml` do próprio repo; depois `psalm.xml.dist`;
  como fallback, gera um `_psalm_temp.xml` com `errorLevel="2"` mirando `<repo_dir>/src`
  e o remove ao final.
- **Cache:** `--no-cache` (evita cache contaminado entre runs).

### PHPCS
- **Standard:** `config/phpcs_rules.xml` se existir; senão `Generic`.
- **Exclusões:** `*/vendor/*`, `*/tests/*`, `*/test/*`, `*/node_modules/*`.
- **Quiet mode:** `-q`.

### SonarQube Scanner
- **Servidor:** sobe junto via `docker-compose.yml` (`sonarqube:community`, perfil
  `fase3`, healthcheck em `/api/system/status`).
- **Host alcançado pelo container fase3:** `SONAR_HOST=http://sonarqube:9000` (rede
  interna do Compose).
- **Credenciais default:** `admin/admin`.
- **Configuração do projeto:** gerada em `/tmp/sonar-project.properties` com chave
  `${REPO_NAME}` (basename do `repo_dir`).
- **Issues coletadas:** tipos `CODE_SMELL`, `BUG`, `VULNERABILITY`, página de 500.

O script Bash do SonarQube tem dois loops de espera explícita:

1. Esperar `/api/system/status` responder (até 30 tentativas × 2s).
2. Após disparar o scanner, fazer polling em `/api/ce/component?component=<repo>`
   até `status=SUCCESS` (até 20 × 3s) — necessário porque o Sonar processa de forma
   assíncrona (background tasks).
3. Loop final para baixar `/api/issues/search` (até 10 × 5s) — alguns repositórios
   demoram a aparecer no índice.

Se tudo expirar, grava `{"total":0,"issues":[]}` e o pipeline segue.

---

## Pipeline interno (passo a passo)

```
        ┌──────────────────────────────────────────┐
        │  fase3_analise_estatica.sh               │
        │  args: <repo_dir> [snippets_json]        │
        └──────────────────────────────────────────┘
                          │
   ┌──────────────────────┼───────────────────────────────────────────┐
   ▼                      ▼                  ▼              ▼          ▼
1) PHPMD             2) PHPStan         3) Psalm        4) PHPCS    5) SonarQube
   ↓                     ↓                  ↓              ↓          ↓
phpmd_output.json    phpstan_output    psalm_output    phpcs_output  sonar_output
        │                     │              │              │          │
        └─────────────────────┴──────┬───────┴──────────────┴──────────┘
                                     ▼
                       6) fase3_consolidar.py
                                     ▼
                ┌──────────────────────────────────────────┐
                │  output/fase3/pre_rotulacao.json + csv   │
                └──────────────────────────────────────────┘
```

Cada bloco 1–5 é "tolerante a falha por design": se a ferramenta não estiver
disponível ou produzir saída inválida, o script grava um JSON vazio canônico
(formato esperado pelo parser daquela ferramenta) e segue para a próxima. **A Fase 3
não aborta porque uma das ferramentas falhou** — apenas reduz o sinal disponível.

---

## Pré-rotulação: como o rótulo é decidido

A lógica está em `fase3_consolidar.py` (linhas 260–271). Depois de coletar todos os
findings que caem dentro do intervalo `[start_line, end_line]` de cada snippet, o
script conta:

- `total_findings`: total de findings no snippet (todas as ferramentas).
- `tool_agreement`: quantas ferramentas distintas detectaram **algum** smell ali.

Regras (avaliadas em ordem, primeira que casar vence):

| Condição                                | `pre_label`           | `confidence` |
|-----------------------------------------|-----------------------|--------------|
| `total_findings == 0`                   | `clean`               | `high`       |
| `tool_agreement >= 3`                   | `smelly`              | `high`       |
| `tool_agreement >= 2`                   | `smelly`              | `medium`     |
| `total_findings >= 3` (1 só ferramenta) | `smelly`              | `medium`     |
| `total_findings >= 1` (1 ferramenta)    | `potentially_smelly`  | `low`        |

A lógica privilegia **concordância entre ferramentas** (rigor metodológico) e cai
para **volume na mesma ferramenta** como segunda evidência. Um único finding isolado
nunca vira `smelly` automaticamente — fica como `potentially_smelly` para o anotador
humano decidir na Fase 4.

> Nota metodológica: na Fase 4, a opção `potentially_smelly` foi removida do select
> de anotação humana. O anotador é forçado a decidir `smelly` ou `clean` para esses
> casos limítrofes — exatamente onde o julgamento humano agrega mais valor sobre a
> análise automatizada.

---

## Mapeamento de findings → snippets

A Fase 2 produz snippets com `file_path`, `start_line`, `end_line`. Cada finding traz
arquivo + linha. A função `find_matching_snippets()` faz, em essência:

```python
for snippet in file_snippets[normalized_path]:
    if snippet["start_line"] <= finding.line <= snippet["end_line"]:
        match
```

Como um arquivo pode conter tanto um snippet `class` (cobrindo, digamos, linhas
10–200) quanto vários snippets `method` aninhados (linhas 30–45, 60–80, …), um único
finding **pode mapear para múltiplos snippets** — e tudo bem: o smell será atribuído
a todos os snippets que o contêm. Isso é coerente com a metodologia (um método ruim
torna a classe inteira ruim também).

Findings sem `line` ou em arquivos fora dos snippets da Fase 2 são contados em
`findings_unmapped` (métrica de saúde do pipeline).

### `normalize_path()`

Diferentes ferramentas reportam paths em formatos distintos. A normalização garante
que `phpmd:/abs/path/repo/src/Foo.php`, `/abs/path/repo/src/Foo.php` e
`src/Foo.php` virem todos `src/Foo.php`:

1. Remove prefixo `<tool>:` (SonarQube usa `<projectKey>:src/Foo.php`).
2. Remove o `REPO_ROOT` absoluto (caminho real do clone).
3. Tira `/` inicial residual.

---

## Classificação de smells em categorias

Cada finding tem uma `rule` específica da ferramenta
(`CyclomaticComplexity`, `Generic.Files.LineLength`, etc.). O consolidador mapeia
isso para uma **taxonomia comum** via `SMELL_CATEGORY_MAP` (linhas 199–219), com
~25 mapeamentos diretos e fallback heurístico:

- `complex` no nome → `Complex Method`
- `unused` / `dead` → `Dead Code`
- `naming` / `name` → `Poor Naming`
- `null` → `Null Safety`
- `type` → `Type Inconsistency`
- `long` / `length` → `Long Method`
- caso nenhuma regra case → `Other`

As categorias finais (que aparecem na interface de anotação e no dataset) são as
mesmas listadas em `SMELL_CATEGORIES` no `fase4_preparar_interface.py`:
`Complex Method`, `Long Method`, `Large Class`, `Long Parameter List`, `God Class`,
`Feature Envy`, `Dead Code`, `Deep Nesting`, `Poor Naming`, `Commented Out Code`,
`Duplicated Code`, `Boolean Parameter`, `Static Coupling`, `Unnecessary Else`,
`Deep Hierarchy`, `Type Inconsistency`, `Null Safety`, `Empty Block`,
`Useless Override`, `Other`.

---

## Saída em disco

```
output/fase3/
├── phpmd_output.json        # bruto, formato PHPMD
├── phpstan_output.json      # bruto, formato PHPStan
├── psalm_output.json        # bruto, formato Psalm (lista)
├── phpcs_output.json        # bruto, formato PHPCS
├── sonar_output.json        # bruto, /api/issues/search do SonarQube
├── pre_rotulacao.json       # ★ consolidado (consumido por Fase 4 e Fase 5)
└── pre_rotulacao.csv        # mesma info em CSV achatado (planilha)
```

### Estrutura de `pre_rotulacao.json`

```json
{
  "metadata": {
    "phase": "Fase 3",
    "description": "Pre-labeling based on static analysis tools",
    "repo": "FakerPHP/Faker",
    "analysis_date": "2026-05-13T...",
    "tools_used": ["PHPMD", "PHPStan", "Psalm", "PHPCS"],
    "statistics": {
      "total_snippets": 509,
      "total_findings_all_tools": 7358,
      "findings_mapped_to_snippets": 1869,
      "findings_unmapped": 5489,
      "tool_finding_counts": { "PHPMD": ..., "PHPStan": ..., "Psalm": ..., "PHPCS": ..., "SonarQube": ... },
      "tool_snippet_coverage": { "PHPMD": ..., ... },
      "pre_label_distribution": { "clean": 363, "potentially_smelly": 78, "smelly": 68 },
      "smell_category_distribution": { "Long Line": 1234, "Complex Method": 56, ... },
      "snippets_with_smells": 146,
      "snippets_clean": 363
    }
  },
  "snippets": [
    {
      "snippet_id": "snippet_0001",
      "file_path": "src/Generator.php",
      "snippet_type": "method",
      "snippet_name": "format",
      "start_line": 42, "end_line": 78,
      "loc_executable": 25,
      "cyclomatic_complexity": 8,
      "code_smells_detected": [
        { "tool_name": "PHPMD",   "smell_type": "CyclomaticComplexity",
          "smell_category": "Complex Method", "severity": "3",
          "message": "...", "line": 50 },
        { "tool_name": "PHPStan", "smell_type": "phpstan.error",
          "smell_category": "Other", "severity": "error",
          "message": "...", "line": 67 }
      ],
      "total_smells_count": 2,
      "unique_smell_categories": ["Complex Method", "Other"],
      "tools_that_detected": ["PHPMD", "PHPStan"],
      "tool_agreement_count": 2,
      "pre_label": "smelly",
      "pre_label_confidence": "medium"
    }
  ]
}
```

Campos consumidos pelas próximas fases:

- **Fase 4** lê `snippets[].pre_label`, `code_smells_detected`, `unique_smell_categories`,
  `tools_that_detected` para popular o painel direito e pré-marcar checkboxes.
- **Fase 5** lê o mesmo arquivo como **fallback** quando não há anotação humana (via
  `--annotations`), promovendo o pré-rótulo a rótulo final do dataset.

### CSV achatado

Um registro por snippet, com `unique_smell_categories` e `tools_that_detected`
serializados como string separada por `; `. Pensado para abrir direto em planilha
ou inspecionar com `awk`/`grep`.

---

## Execução prática

A Fase 3 **não** roda nativa de forma confiável (precisa do SonarQube em rede). Use
sempre Docker:

```bash
# Pipeline completo (clona, snippeta, analisa)
make run REPO=FakerPHP/Faker

# Só Fase 3 (assume que Fase 2 já gerou snippets_com_metricas.json)
docker compose --profile fase3 up fase3

# Iniciar manualmente o SonarQube primeiro (caso queira inspecionar via UI)
docker compose --profile fase3 up -d sonarqube
# UI disponível em http://localhost:9000 (admin/admin)
```

O `docker-compose.yml` declara `fase3.depends_on.sonarqube.condition: service_healthy`,
ou seja, o container `fase3` só sobe depois que o healthcheck do SonarQube
(`curl -sf /api/system/status`) passar.

### Sem rede / sem Sonar disponível

Se você não quiser/puder subir o Sonar, edite `fase3_analise_estatica.sh` e pule
o bloco "5/5 SonarQube" — o consolidador aceita um `sonar_output.json` vazio sem
reclamar (`parse_sonar` retorna lista vazia).

---

## Execução validada (FakerPHP/Faker, 2026-05-13)

Números esperados de uma run limpa:

| Métrica                                    | Valor   |
|--------------------------------------------|---------|
| Findings totais (5 ferramentas somadas)    | 7.358   |
| Findings mapeados a snippets               | 1.869   |
| Findings descartados (sem linha ou fora)   | 5.489   |
| Snippets `clean`                           | 363     |
| Snippets `potentially_smelly`              | 78      |
| Snippets `smelly`                          | 68      |

Diferenças grandes (>20%) entre runs do mesmo repositório indicam:

1. Mudança no `commit_hash` (Fase 1 rodou de novo e pegou HEAD diferente).
2. Versão diferente das PHARs em `tools/`.
3. SonarQube fresh vs. cached (primeira run sempre produz menos issues que a segunda
   no mesmo container — comportamento conhecido).

---

## Contrato com as fases anteriores e seguintes

- **Entrada exigida:**
  - `output/fase1/repositorio_metadata.json` (usado pelo Compose para descobrir
    `REPO_NAME` e localizar o diretório `repos/<owner>_<repo>/`).
  - `output/fase2/snippets_com_metricas.json` (consumido pelo consolidador).
  - O próprio repositório clonado em `repos/<owner>_<repo>/` (Fase 2 garante isso).
- **Saída exigida pelas fases seguintes:**
  - `output/fase3/pre_rotulacao.json` é leitura obrigatória da Fase 4 (interface) e
    fallback da Fase 5 (dataset final).
  - Os 5 JSONs brutos (`phpmd_output.json`, etc.) ficam como **auditoria** —
    permitem refazer a consolidação com regras diferentes sem rodar tudo de novo.

---

## Pontos de atenção e armadilhas conhecidas

1. **PHARs versus binários.** Em ambiente Docker, as PHARs em `tools/` têm
   prioridade sobre qualquer binário de sistema. Atualizar uma PHAR exige `make build`
   (o `Dockerfile` baixa as versões fixas).
2. **PHPStan level.** O nível está fixado em 5. Subir para 7+ aumenta drasticamente
   o ruído e desequilibra a regra "1 só ferramenta com ≥3 findings = smelly medium".
   Mudar isso é uma decisão metodológica, não cosmética.
3. **PHPCS standard genérico.** Se `config/phpcs_rules.xml` desaparecer, o standard
   cai para `Generic`, que produz pouquíssimas mensagens — vai gerar mais `clean`
   artificialmente. Mantenha o XML em `config/`.
4. **SonarQube primeiro start.** A primeira inicialização do `sonarqube:community`
   leva 30–60s antes do healthcheck passar. Em máquinas lentas, ajuste o `retries: 60`
   do compose para mais.
5. **`findings_unmapped` alto.** Esperado: ferramentas reportam findings em arquivos
   que a Fase 2 ignorou (testes, configs). Não é defeito do mapper. Se o número
   passar de 90% do total, vale investigar se a Fase 2 não está filtrando demais.
6. **Sonar não retorna issues.** Algumas regras só rodam após "scan profundo". A
   estratégia atual (polling até `SUCCESS`) cobre 95% dos casos, mas repositórios
   muito grandes podem precisar aumentar os limites de espera no script.
7. **Regras heurísticas de classificação.** Quando uma rule não está no
   `SMELL_CATEGORY_MAP`, o fallback por substring pode classificar mal (ex.: regra
   contendo "type" em outro contexto vira `Type Inconsistency`). Para refinar,
   adicione mapeamentos explícitos ao dicionário.
