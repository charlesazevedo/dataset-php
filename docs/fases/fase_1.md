# Fase 1 — Seleção e Validação de Repositório PHP

## Objetivo

A Fase 1 é a porta de entrada do pipeline de construção do dataset. Sua responsabilidade
é **identificar repositórios PHP no GitHub que satisfaçam os critérios metodológicos da
pesquisa** e gravar, em disco, um arquivo de metadados completo que será consumido por
todas as fases subsequentes (clonagem na Fase 2, análise estática na Fase 3, etc.).

Em uma frase: a fase consulta a GitHub API, valida cada repositório candidato contra um
conjunto fixo de critérios e persiste um JSON de metadados — opcionalmente em modo
batch, selecionando os top N repositórios automaticamente.

Script: `scripts/fase1_selecionar_repositorio.py` (Python 3, somente stdlib + `requests`).

---

## Critérios de seleção (metodologia)

Os critérios são fixos no código (`CRITERIA`, linhas 39–46 do script) e refletem a
necessidade de trabalhar com projetos PHP **maduros, ativos e de adoção comprovada**:

| Critério              | Valor exigido                                           | Justificativa                                                     |
|-----------------------|---------------------------------------------------------|-------------------------------------------------------------------|
| `language`            | `PHP` (linguagem primária reportada pela API)           | Restringe o universo ao alvo da pesquisa.                         |
| `min_stars`           | `>= 1000`                                               | Indicador de adoção pela comunidade.                              |
| `min_forks`           | `>= 100`                                                | Indica reutilização e contribuição externa.                       |
| `last_push_after`     | `>= 2024-01-01`                                         | Manutenção ativa — descarta projetos abandonados.                 |
| `created_before`      | `< 2023-01-01`                                          | Projeto maduro com histórico suficiente para análise.             |
| `allowed_licenses`    | `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`     | Licenças permissivas — viabiliza redistribuição do dataset.       |

Alterar esses valores muda a composição estatística do dataset; por isso, qualquer
modificação deve ser justificada metodologicamente.

---

## Modos de execução

O script aceita quatro modos mutuamente exclusivos, controlados pelos argumentos da CLI
(ou pelas variáveis de ambiente `REPO` / `AUTO_SELECT` quando executado via Docker
Compose).

### 1. `--repo OWNER/REPO` — repositório específico

Caso de uso típico: o pesquisador já sabe qual projeto quer analisar.

Fluxo:

1. **Cache.** Antes de qualquer chamada à API, o script procura um arquivo
   `repositorio_metadata_<owner>_<repo>.json` (com ou sem prefixo de índice
   `01_`, `02_`, …) em `output/fase1/`. Se encontrar, **reaproveita** sem consultar
   a GitHub API — economiza requisições e permite re-execução offline.
2. **Consulta à API.** Se não houver cache, chama `GET /repos/{owner}/{repo}` e monta
   os metadados (ver seção "Conteúdo do JSON gerado" abaixo).
3. **Validação dos critérios.** Exibe tabela visual com cada critério, valor obtido
   e status (✓/✗).
4. **Decisão sobre prosseguir.** Se algum critério falhar, o script pergunta
   interativamente (`[s/N]`) se o usuário quer continuar mesmo assim. Em ambiente
   não-interativo (Docker, CI), o `EOFError` é capturado e o pipeline prossegue.
5. **Atualização do symlink.** Cria/atualiza `output/fase1/repositorio_metadata.json`
   apontando para o arquivo do repositório escolhido. Esse symlink é o "ponteiro
   ativo" que as Fases 2–5 leem.

### 2. `--auto-select N` — modo batch (não-interativo)

Caso de uso: gerar uma lista candidata de N repositórios PHP para análise comparativa.

Fluxo (`_batch_select`, linhas 336–428):

1. Chama `GET /search/repositories?q=language:php stars:>=1000 forks:>=100`,
   ordenado por estrelas (decrescente), 30 resultados por página.
2. Para cada candidato:
   - Faz `GET /repos/{owner}/{repo}` (dados completos).
   - Roda `build_metadata` (que dispara `detect_license`, `detect_php_version`,
     `get_latest_commit`).
   - Aplica `validate_criteria`.
   - **Aceita somente repos que passam em TODOS os critérios.** Os reprovados são
     listados com motivo da rejeição e descartados (entram em `skipped`).
3. Salva cada metadata aprovada com prefixo de ordem
   (`repositorio_metadata_01_xxx.json`, `02_…`, …) e cria também um
   `batch_selection.json` resumindo o que foi selecionado.
4. O symlink `repositorio_metadata.json` aponta para o **primeiro** aprovado (o
   melhor rankeado).
5. Continua paginando até completar N aprovados ou esgotar resultados.

Comando típico:

```bash
docker compose run --rm shell python3 scripts/fase1_selecionar_repositorio.py --auto-select 5
```

### 3. `--search "keyword"` — busca por palavra-chave

Variante interativa: o usuário digita uma keyword, o script lista os top resultados
PHP que contêm o termo e pede para escolher um pelo índice (`1-N`). Depois segue o
mesmo fluxo do modo `--repo`. Em ambiente não-interativo, escolhe o primeiro
resultado.

### 4. Sem argumentos — listagem padrão

Lista os top repositórios PHP sem filtro de keyword. Idêntico ao `--search` em
comportamento (pergunta o índice), mas sem termo de busca.

---

## Como cada peça de metadados é obtida

O script não confia cegamente nos campos retornados pela API — usa fallbacks robustos
para os dois pontos mais sensíveis: licença e versão do PHP.

### Licença (`detect_license`)

1. **Primário:** campo `license.spdx_id` do payload `/repos/...`.
2. **Fallback 1:** se o primário vier como `NOASSERTION` ou vazio, chama o endpoint
   dedicado `/repos/{owner}/{repo}/license`.
3. **Fallback 2:** se ainda não houver, baixa `composer.json` via
   `/repos/{owner}/{repo}/contents/composer.json` (decodificando o base64) e lê o
   campo `license` (que pode ser string ou lista; trata ambos).
4. Se nada der resultado, devolve `"unknown"`.

### Versão do PHP requerida (`detect_php_version`)

Lê `composer.json` (`require.php`), via API de `contents`. Não há fallback adicional —
se o repo não tiver `composer.json` ou se a chave não existir, retorna `"unknown"`.

### Hash do último commit (`get_latest_commit`)

Faz `GET /repos/{owner}/{repo}/commits/{branch}`, onde `branch` é a `default_branch`
do repo. Esse hash é o "ponto de congelamento" do dataset — todas as fases seguintes
analisam o código nesse snapshot lógico (ainda que o `git clone --depth 1` da Fase 2
clone HEAD por simplicidade).

### Categorização (`categorize_repo`)

Heurística simples baseada em keywords presentes na `description` e nos `topics` do
repositório. Retorna uma de:

- `framework` (palavras-chave: framework, mvc)
- `cms` (cms, content management)
- `ecommerce` (ecommerce, e-commerce, shop)
- `library/utility` (library, lib, sdk, utility, helper)
- `api` (api, rest, graphql)
- `other` (default)

Útil para análises descritivas posteriores, sem peso nos critérios de seleção.

---

## Conteúdo do JSON gerado

Cada repositório selecionado gera um arquivo em `output/fase1/` com a seguinte
estrutura (exemplo real: `FakerPHP/Faker`):

```json
{
  "repo_name": "FakerPHP/Faker",
  "github_url": "https://github.com/FakerPHP/Faker",
  "commit_hash": "82f77b19dbbddda50317ffc36f8ea152cb0f50a0",
  "snapshot_date": "2026-05-14T19:59:54.185374+00:00",
  "stars": 3963,
  "forks": 423,
  "license": "MIT",
  "php_version_required": "^7.4 || ^8.0",
  "category": "library/utility",
  "created_at": "2020-10-27T10:10:59Z",
  "last_push": "2026-05-02T00:19:11Z",
  "description": "Faker is a PHP library that generates fake data for you",
  "default_branch": "2.0",
  "language": "PHP",
  "topics": [],
  "criteria_validation": {
    "language_php":       { "required": "PHP",                    "actual": "PHP",                    "passed": true },
    "stars_min":          { "required": ">= 1000",                "actual": 3963,                     "passed": true },
    "forks_min":          { "required": ">= 100",                 "actual": 423,                      "passed": true },
    "last_push_recent":   { "required": "after 2024-01-01",       "actual": "2026-05-02T00:19:11Z",   "passed": true },
    "created_mature":     { "required": "before 2023-01-01",      "actual": "2020-10-27T10:10:59Z",   "passed": true },
    "license_permissive": { "required": "one of ['MIT', ...]",    "actual": "MIT",                    "passed": true }
  },
  "all_criteria_met": true,
  "notes": ["Todos os critérios atendidos ✓"]
}
```

Campos-chave para as próximas fases:

- `repo_name` — usado pela Fase 2 para nomear o diretório de clone (`repos/<owner>_<repo>/`).
- `github_url` — URL que a Fase 2 clona (`git clone --depth 1`).
- `default_branch` — branch a clonar.
- `commit_hash` — snapshot lógico do dataset (rastreabilidade).
- `criteria_validation` / `all_criteria_met` — auditoria reprodutível.

---

## Saída em disco

Estrutura final em `output/fase1/`:

```
output/fase1/
├── repositorio_metadata.json                          # symlink → arquivo do repo "ativo"
├── repositorio_metadata_FakerPHP_Faker.json           # gerado pelo modo --repo
├── repositorio_metadata_01_<owner>_<repo>.json        # gerado pelo modo --auto-select
├── repositorio_metadata_02_<owner>_<repo>.json
├── ...
└── batch_selection.json                               # resumo do batch (modo --auto-select)
```

O **symlink** `repositorio_metadata.json` é o único arquivo lido pelas Fases 2–5.
Trocar o repositório ativo no batch significa apenas redirecionar esse symlink — o
que o script faz via `_update_symlink` quando invocado com `--repo OWNER/REPO`
posteriormente.

Em sistemas onde o symlink falha (Windows sem privilégio, alguns mounts), há fallback
para `shutil.copy2` — o arquivo é copiado em vez de linkado.

`batch_selection.json` (gerado apenas no modo `--auto-select`) tem este formato:

```json
{
  "generated_at": "2026-05-13T...",
  "selection_mode": "auto",
  "criteria": { "min_stars": 1000, "min_forks": 100, "...": "..." },
  "total_selected": 5,
  "total_skipped": 12,
  "repositories": [
    { "index": 1, "repo_name": "danielmiessler/SecLists", "stars": ..., "license": "MIT",
      "all_criteria_met": true, "file": "repositorio_metadata_01_..." },
    ...
  ]
}
```

---

## Autenticação e rate-limit

O script usa o cabeçalho `Authorization: token <GITHUB_TOKEN>` quando a variável
de ambiente `GITHUB_TOKEN` está definida (lida do `.env` do projeto pelo
`docker-compose`).

| Estado            | Limite GitHub API                |
|-------------------|----------------------------------|
| Sem token         | **60 requisições/hora** por IP   |
| Com token pessoal | **5.000 requisições/hora**       |

Como cada repositório consome ~3–4 chamadas (`/repos`, `/license`, `/contents/composer.json`,
`/commits/<branch>`) e o modo batch também consome `/search/repositories`, executar
`--auto-select N` sem token estoura o limite muito rapidamente. **Sempre defina
`GITHUB_TOKEN` no `.env`.**

---

## Execução prática

Todos os comandos rodam via Docker (não há execução nativa suportada):

```bash
# Construir a imagem (uma única vez por sessão / após mudança no Dockerfile)
make build

# Modo --repo: validar um repositório específico
REPO=FakerPHP/Faker docker compose --profile fase1 up fase1

# Modo --auto-select: selecionar 5 repos automaticamente
docker compose run --rm shell python3 scripts/fase1_selecionar_repositorio.py --auto-select 5

# Trocar o repo ativo de um batch já gerado (apenas atualiza o symlink)
docker compose run --rm shell python3 scripts/fase1_selecionar_repositorio.py --repo laravel/framework

# Pipeline completo (Fases 1–5) num único comando
make run REPO=FakerPHP/Faker
```

O wrapper Compose (`docker-compose.yml`, linhas 90–106) escolhe o modo conforme as
variáveis de ambiente: `AUTO_SELECT` tem prioridade sobre `REPO`; se nenhuma estiver
definida, cai no modo padrão (listagem interativa).

---

## Contrato com as fases seguintes

A Fase 2 começa lendo `output/fase1/repositorio_metadata.json` para obter
`repo_name` e `github_url`. Se esse arquivo não existir, a Fase 2 falha imediatamente.

Por isso, a Fase 1 é a **única fase que não pode ser pulada**. Tudo o que vem depois
depende do JSON que ela produz.

---

## Pontos de atenção e armadilhas conhecidas

1. **Repos cujo `default_branch` não é `main`/`master`.** O script lê a branch correta
   do payload da API (`data["default_branch"]`), então funciona para casos como
   `FakerPHP/Faker` (branch `2.0`). Não fixe `main` no código.
2. **Repos sem `composer.json`.** Aceitos, mas `php_version_required` ficará como
   `"unknown"`. Isso não bloqueia o pipeline — apenas remove uma informação descritiva.
3. **Repos com licença em formato não-SPDX.** Tratados via fallback no `composer.json`,
   mas se mesmo assim a licença não estiver na lista permissiva, o critério
   `license_permissive` falha (✗) e o repositório é rejeitado em modo `--auto-select`.
4. **Cache "preso".** Se você quiser reanalisar um repo cujos metadados já estão em
   cache (campos novos, regras atualizadas), apague manualmente o arquivo
   `output/fase1/repositorio_metadata_<owner>_<repo>.json` antes de rodar `--repo`.
5. **Reprodutibilidade.** Como `snapshot_date` é gerado com `datetime.now()` a cada
   execução, dois runs do mesmo repo produzirão JSONs ligeiramente diferentes (mesmo
   conteúdo metodológico, timestamps distintos). Para auditoria, o que importa é
   `commit_hash` + critérios.
