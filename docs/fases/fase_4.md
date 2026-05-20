# Fase 4 — Interface de Anotação Humana

## Objetivo

A Fase 4 é o **ponto humano-no-loop** do pipeline. Sua responsabilidade é integrar
os dados estruturais da Fase 2 (snippets + métricas) com os pré-rótulos automáticos
da Fase 3 (smells detectados pelas 5 ferramentas) e renderizar tudo numa **interface
HTML autocontida** que permite a um especialista validar, corrigir ou refinar a
classificação de cada snippet — produzindo o conjunto de rótulos "gold standard"
que a Fase 5 vai consumir para montar o dataset final.

Em uma frase: a Fase 4 é onde a opinião informada do humano supervisiona a heurística
de concordância entre ferramentas — e onde decisões metodológicas (Smelly × Clean +
categoria obrigatória) materializam-se em rótulos confiáveis.

Scripts envolvidos:

- `scripts/fase4_preparar_interface.py` — gera o HTML autocontido + o JSON
  intermediário (`dados_integrados.json`) que une Fase 2 e Fase 3.
- `scripts/consolidar_anotacoes.py` — opcional, agrupa anotações de múltiplos
  anotadores por votação de maioria.
- `scripts/aplicar_desempate.py` — opcional, aplica decisões do 4º revisor sobre
  os casos com empate.

Artefatos no diretório de saída:

- `output/fase4/interface_anotacao.html` — interface principal (abrir no navegador).
- `output/fase4/index.html` — landing page com cartões para a interface e para o
  HTML de desempate (gerada apenas se ainda não existir).
- `output/fase4/dados_integrados.json` — snippets + métricas + pré-rótulos consolidados.
- `output/fase4/revisao_desempate.html` — só existe após `consolidar_anotacoes.py`
  detectar casos divergentes (≥ 2 anotadores).

---

## Arquitetura da interface

O `interface_anotacao.html` é um arquivo único, ~3 MB, totalmente autocontido:

- **JavaScript embarcado:** lógica de navegação, validação, persistência local,
  export/import. Sem build, sem bundler.
- **Dados embarcados:** o array `DATA` (todos os snippets já integrados) é
  injetado direto no `<script>` como JSON literal — evita CORS ao abrir via
  `file://`.
- **Dependências externas (via CDN):** apenas `highlight.js` para syntax
  highlighting de PHP (tema `github-dark`).
- **Persistência:** `localStorage` chaveado pelo nome do repositório
  (`codesmell_annotations_<owner>_<repo>`). Auto-save a cada interação.

A geração do HTML é feita inteira em Python (`generate_annotation_html()`), usando
um template de string com placeholders `__DATA_JSON__` e `{{repo_name}}` substituídos
em tempo de build.

---

## Pipeline de preparação (script Python)

```
1. Carregar Fase 2 (snippets_com_metricas.json)
2. Carregar Fase 3 (pre_rotulacao.json)
3. Localizar repo clonado em repos/<owner>_<repo>/
4. Para cada snippet:
     4.1. Re-extrair code do arquivo real
          via [start_line..end_line] (1-indexed inclusive)
          → garante alinhamento perfeito com smell.line da Fase 3
          fallback: code do pretty-printer (Fase 2) se arquivo não acessível
     4.2. Agregar métricas + pre_label + smells_detected
                + unique_smell_categories + tools_that_detected
     4.3. Empurrar para integrated_data[]
5. Computar estatísticas (smelly / potentially_smelly / clean)
6. Render HTML
7. Persistir dados_integrados.json (backup programático)
8. Gerar index.html se não existir
```

A re-extração da etapa 4.1 é crucial: o `code` armazenado pela Fase 2 é o
**reserializado** pelo pretty-printer do nikic, então as linhas não casam com as
posições reportadas pelas ferramentas (que enxergam o arquivo original). Lendo
do disco, o highlight de smells por linha funciona corretamente.

---

## Layout da interface

```
┌──────────────────────────────────────────────────────────────────┐
│ Header: badge repo | total | smelly | potencial | clean | anotados │
├──────────────────────────────────────┬───────────────────────────┤
│ NAV BAR                              │                           │
│ ← Anterior  [pág/total]  Próximo →   │      🏷 Anotação          │
│ [filtro ▼]   [⚙ Ações ▾]              │                           │
├──────────────────────────────────────┤  Label Final:             │
│ [type] [pre_label]  Generator::fmt   │    — selecione —          │
│ src/Generator.php : 42-78            │    🔴 Smelly              │
│                                      │    🟢 Clean               │
│ [metrics grid]                       │                           │
│   LOC Exec  | CC  | Nesting          │  [aviso de validação]     │
│   H.Volume  | Diff | Bugs            │                           │
│                                      │  Categorias de Smell:     │
│ ┌────────────────────────────────┐   │    ☐ Complex Method       │
│ │  42  public function format(...│   │    ☐ Long Method          │
│ │  43      ...                   │   │    ☐ Large Class          │
│ │  44      [HL] if (deep_nested) │   │    ... (20 opções)        │
│ │  ...                           │   │                           │
│ └────────────────────────────────┘   │  Observações:             │
│                                      │    [textarea]             │
│ 🔍 Smells Detectados                  │                           │
│  [PHPMD: CyclomaticComplexity]       │  [Salvar & Próximo →]     │
│  [PHPStan: phpstan.error] ...        │                           │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━     │                           │
│ [progress bar de anotações]           │                           │
└──────────────────────────────────────┴───────────────────────────┘
```

**Painel esquerdo (código + smells):**

- Cabeçalho com tipo, pré-rótulo (badge), nome qualificado, caminho do arquivo.
- Grade de métricas com tooltip explicativo em cada uma (LOC, CC, Nesting,
  Halstead Volume/Diff/Bugs, num_methods, num_parameters).
- Bloco de código com numeração de linha 1:1 ao arquivo original, sintaxe
  destacada por highlight.js. Linhas com smell ganham fundo colorido (vermelho
  para `high/critical`, amarelo para `warning`, azul para `info`).
- Lista de smells abaixo do código, cada um clicável: rolagem suave até a linha
  do finding.

**Painel direito (formulário de anotação):**

- Select `Label Final`: 2 opções **Smelly** ou **Clean** + placeholder
  `— selecione —`. Removido o `Potencialmente Smelly` por decisão metodológica
  (o especialista deve afirmar uma das duas).
- Pré-seleção:
  - Pré-rótulo `smelly` → Smelly já vem selecionado.
  - Pré-rótulo `clean` → Clean já vem selecionado.
  - Pré-rótulo `potentially_smelly` → placeholder (força decisão humana).
- Bloco de Categorias de Smell: 20 checkboxes (lista canônica) + marcador
  inline mostrando estado de validação (`(obrigatório se Smelly)` →
  `✓ N categoria(s)` → `(obrigatório — selecione ao menos uma)`).
- Textarea de Observações (notas do anotador, persistido junto com o label).
- Botão **Salvar & Próximo →** (atalho: `Enter`).

---

## Regras de validação

Implementadas em `saveAnnotation()`. Cada anotação só persiste se passar nas duas:

| Regra                                 | Mensagem ao falhar                                                    |
|---------------------------------------|-----------------------------------------------------------------------|
| Label deve ser `smelly` ou `clean`    | ⚠ Selecione um label final (Smelly ou Clean) para anotar este snippet |
| `smelly` exige ≥ 1 categoria marcada  | ⚠ Snippets marcados como Smelly precisam de pelo menos uma categoria  |

Quando falha:

- Feedback visual: caixa de categorias ganha borda vermelha (`.invalid`),
  marcador inline em vermelho.
- A anotação **não persiste** no `localStorage`.
- Se havia anotação anterior válida para o snippet, ela é **removida** —
  consistência total entre estado UI e estado persistido.
- O botão "Salvar & Próximo" **não avança** o índice; o usuário fica no
  snippet até corrigir.

Quando `clean` é escolhido, smells marcados (vindos do pré-rótulo da Fase 3) são
**descartados automaticamente** ao persistir — coerência semântica.

### Categorias canônicas

Lista fixa em `SMELL_CATEGORIES` (no template JS):

`Complex Method`, `Long Method`, `Large Class`, `Long Parameter List`,
`God Class`, `Feature Envy`, `Dead Code`, `Deep Nesting`,
`Poor Naming`, `Commented Out Code`, `Duplicated Code`, `Boolean Parameter`,
`Static Coupling`, `Unnecessary Else`, `Deep Hierarchy`, `Type Inconsistency`,
`Null Safety`, `Empty Block`, `Useless Override`, `Other`.

São as mesmas que a Fase 3 atribui via `SMELL_CATEGORY_MAP`. Mantenha alinhado:
adicionar/remover aqui exige adicionar/remover no consolidador também.

---

## Navegação e atalhos

| Ação                                | Como                                       |
|-------------------------------------|--------------------------------------------|
| Próximo snippet                     | `→`, `n`, botão "Próximo →", `Enter`       |
| Snippet anterior                    | `←`, `p`, botão "← Anterior"               |
| Ir para página N                    | input numérico ao lado dos botões          |
| Marcar como Smelly                  | tecla `1`                                  |
| Marcar como Clean                   | tecla `2`                                  |
| Fechar menu de Ações                | `Escape` ou clique fora                    |
| Filtrar (Todos / Smelly / Pot. / Clean / Não anotados) | dropdown na nav bar  |
| Rolar até linha de um smell         | clicar no smell-tag ou no link `📍 Linha N` |

Atalhos `1`/`2` aplicam o label imediatamente (chamam `saveAnnotation()`). Se a
validação falhar, a UI mostra o aviso mas não persiste.

---

## Menu de Ações (export/import)

Único botão **⚙ Ações ▾** abre um dropdown com 3 grupos descritivos:

### Anotações

- **📥 Exportar anotações (JSON):** baixa apenas as anotações do anotador atual em
  formato `fase4_anotacoes_<repo>_<data>.json`. Use para enviar a outro
  anotador ou consolidar via `consolidar_anotacoes.py`.
- **📊 Exportar anotações (CSV):** mesmo conteúdo em planilha (8 colunas:
  `snippet_id`, `snippet_name`, `file_path`, `type`, `label`, `smells`,
  `notes`, `annotated_at`). BOM UTF-8 no início para abrir bonito no Excel.
- **📤 Importar anotações:** carrega um JSON e **mescla** com as atuais
  (preserva snippets em memória, sobrescreve anotações com mesmo `snippet_id`).

### Pacote completo

- **📦 Exportar pacote completo:** baixa `fase4_pacote_completo_<repo>_<data>.json`
  contendo **snippets + métricas + pré-rótulos + anotações** num único arquivo.
  Use para compartilhar entre máquinas sem ter que rodar o pipeline inteiro.
- **📦 Importar pacote completo:** carrega um pacote e **substitui** os snippets
  e anotações desta sessão. Confirma com tela exibindo nome do repo, contagem
  de snippets, contagem de anotações. Atualiza o badge do repo no header e o
  título da aba do navegador.

### Manutenção

- **🗑️ Limpar anotações deste navegador:** remove as anotações do repositório
  atual do `localStorage`. Não afeta arquivos já exportados.

---

## Estado persistido (localStorage)

```
Chave: codesmell_annotations_<owner>_<repo>
Valor: JSON serializado:
{
  "SNIPPET_0001": {
    "label": "smelly",
    "smells": ["Complex Method", "Deep Nesting"],
    "notes": "CC alta, vale refatorar o switch principal",
    "annotated_at": "2026-05-14T..."
  },
  "SNIPPET_0042": { ... },
  ...
}
```

Caminhos importantes:

- **Auto-save:** cada `onchange` do select, checkboxes e textarea dispara
  `saveAnnotation()`. Não há botão de "salvar manualmente".
- **Carregamento:** ao abrir a página, lê `localStorage[STORAGE_KEY]` e
  popula `annotations`.
- **Migração:** anotações antigas com `label: "potentially_smelly"` são tratadas
  como **não anotadas** ao renderizar o form (força o anotador a redecidir).
- **Reset:** o item "Limpar anotações deste navegador" apaga só esta chave;
  outros repositórios em outras sessões ficam intactos.

---

## Fluxo de múltiplos anotadores

A interface **não é colaborativa em tempo real** — cada anotador trabalha sozinho
no próprio navegador. O fluxo recomendado (registrado em `AGENTS.md`) é:

```
                ┌─────────────────────────────┐
                │  fase4_preparar_interface.py │
                └─────────────────────────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
   Dev 1 abre              Dev 2 abre             Dev N abre
   no navegador            no navegador            no navegador
   anota tudo              anota tudo             anota tudo
   Exporta JSON            Exporta JSON           Exporta JSON
       │                      │                      │
       └──────────────────────┼──────────────────────┘
                              ▼
              ┌────────────────────────────────┐
              │  consolidar_anotacoes.py        │
              │  votação de maioria + desempate │
              └────────────────────────────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
        consolidado.json                 revisao_desempate.html
        (todos consensuais)              (só os com empate)
              │                                │
              │                                ▼
              │                       4º revisor decide
              │                       Exporta JSON Final
              │                                │
              │           ┌────────────────────┘
              ▼           ▼
        ┌────────────────────────────┐
        │  aplicar_desempate.py       │
        └────────────────────────────┘
                       │
                       ▼
                anotacoes_final.json
                       │
                       ▼
              ┌────────────────┐
              │   Fase 5        │
              │   --annotations │
              └────────────────┘
```

### Regras de consolidação (`consolidar_anotacoes.py`)

- **Label final:** maioria simples dos votos.
  - Unanimidade → `resolution: consensus`.
  - Empate exato → desempate por prioridade `smelly > potentially_smelly > clean`
    e marca `requires_review: true`.
  - Maioria não-unânime → `resolution: majority`; se for maioria mínima
    (≤ 50% + 1 voto), também marca `requires_review: true`.
- **Smells:** mantidos se ≥ 2 anotadores apontaram (com 3+ anotadores) ou
  ≥ 1 (com 1 anotador).
- **Notas:** concatenadas com ` | `, deduplicadas.
- **Campos extras gerados:** `agreement_rate`, `resolution`, `all_votes`,
  `votes_per_annotator`, `requires_review`.

### HTML de desempate

Quando há `requires_review > 0` e o usuário passou `--snippets-data`, o
consolidador gera `revisao_desempate.html` (também autocontido, com CDN
highlight.js). Mostra, para cada caso conflitante:

- Código completo com syntax highlighting.
- Voto de cada anotador lado a lado (label + smells + notas).
- Form para o 4º revisor decidir: label final + smells + nota de desempate.
- Botão **📥 Exportar JSON Final** baixa `desempate_<data>.json`.

A página persiste estado em `localStorage` (chave separada da interface
principal).

### Aplicar desempate (`aplicar_desempate.py`)

Lê o consolidado + o JSON do desempate e produz `anotacoes_final.json`,
marcando cada caso resolvido com:

- `label`: decisão do revisor.
- `label_before_tiebreak`: valor anterior (auditoria).
- `smells` / `smells_before_tiebreak`: idem para categorias, se o revisor mudou.
- `resolution`: `human_tiebreak`.
- `requires_review`: `false`.
- `tiebreak_decided_at`: ISO timestamp.
- `notes`: original + ` | [desempate] <nota do revisor>`.

Esse arquivo é o input final da Fase 5 via `--annotations`.

---

## Saída em disco

```
output/fase4/
├── interface_anotacao.html              # ★ abrir no navegador
├── index.html                           # landing page (gerada se não existir)
├── dados_integrados.json                # snippets + métricas + pré-rótulos integrados
└── revisao_desempate.html               # só se houver requires_review > 0
```

`dados_integrados.json` tem a mesma estrutura usada pelo template do HTML, mas
em formato programático: `metadata` (repo, distribuição, data) + `snippets[]`
(cada um com identidade, code re-extraído, métricas, pré-rótulo, smells,
ferramentas que detectaram). Útil para scripts de pós-processamento que querem
ler os dados sem precisar varrer o HTML.

---

## Execução prática

```bash
# Gerar a interface (após Fases 1, 2 e 3 rodarem)
docker compose --profile fase4 up fase4

# Servir via HTTP (recomendado para múltiplos anotadores na rede local)
make interface INTERFACE_PORT=9090
# acessar em http://localhost:9090

# Abrir local diretamente (file://)
xdg-open output/fase4/interface_anotacao.html

# Regenerar mantendo o index.html customizado
docker compose run --rm shell python3 scripts/fase4_preparar_interface.py
# (se index.html já existir, é preservado; só interface_anotacao.html é refeito)
```

Servir via HTTP é mais robusto que abrir como `file://` — alguns navegadores
limitam `localStorage` em URLs locais e bloqueiam fetches mesmo de arquivos
adjacentes (importação de pacote completo, por exemplo).

---

## Contrato com as fases anteriores e seguintes

- **Entrada exigida:**
  - `output/fase2/snippets_com_metricas.json` (sem isso, nada a mostrar).
  - `output/fase3/pre_rotulacao.json` (sem isso, falha imediatamente — pré-rótulos
    são parte essencial do form).
  - `repos/<owner>_<repo>/` clonado (para re-extrair `code` por linha; é
    fallback-friendly: se faltar, usa o `code` reserializado da Fase 2).
- **Saída exigida pela Fase 5:**
  - Um JSON de anotações no formato `{ "metadata": {...}, "annotations": { "<sid>": {...} } }`,
    consumido pela flag `--annotations`. Pode ser:
    - Exportação direta de 1 anotador (botão **📥 Exportar anotações (JSON)**), ou
    - Consolidado de N anotadores (via `consolidar_anotacoes.py`), ou
    - Final pós-desempate (via `aplicar_desempate.py`).

Sem `--annotations`, a Fase 5 cai no fallback: usa pré-rótulos da Fase 3 como
rótulo final do dataset. Funcional, mas perde a contribuição humana.

---

## Pontos de atenção e armadilhas conhecidas

1. **Re-extração de código vs pretty-printer.** O `code` exibido na interface
   é o do arquivo original (linhas alinhadas com findings da Fase 3). Se você
   limpou `repos/` mas mantém `output/fase2`, o script faz fallback para o
   código reserializado — funciona, mas linhas dos smells deslocam levemente.
2. **`localStorage` por origem.** Abrir `file:///abs/output/fase4/interface_anotacao.html`
   e `http://localhost:8080/interface_anotacao.html` usam **chaves diferentes**
   no `localStorage` (origem distinta). Anotações feitas em um modo não aparecem
   no outro. Padronize o modo de acesso entre anotadores.
3. **Tamanho do HTML.** A interface fica ~3 MB para repos grandes (~500 snippets,
   ~509 KB de JSON embutido após re-extração). Funciona, mas Firefox em máquinas
   modestas pode levar 2–3s para parsear no primeiro load.
4. **Conflito ao importar pacote completo.** Importar um pacote sobrescreve
   `DATA`, `annotations`, `REPO_NAME` e `STORAGE_KEY` em memória. Se o anotador
   estava com mudanças não exportadas, elas são perdidas. O confirm() avisa,
   mas vale lembrar.
5. **Categorias divergentes.** A lista `SMELL_CATEGORIES` no JS tem que casar
   com `SMELL_CATEGORY_MAP` em `fase3_consolidar.py`. Adicionar uma categoria
   nova exige editar ambos.
6. **Anotações legadas com `potentially_smelly`.** Anotações geradas em versões
   antigas da interface ainda podem ter esse label. São tratadas como
   não anotadas (force re-anotação). Se vir queda no contador "Anotados"
   depois de regenerar a interface, é isso.
7. **Pré-seleção de label não persiste sozinha.** Quando o select vem
   pré-marcado com `smelly`/`clean` por causa do pré-rótulo, **nada** é salvo
   no `localStorage` até o anotador interagir. O contador "Anotados" só sobe
   após uma ação afirmativa.
8. **Highlight.js da CDN.** Se o anotador estiver offline, o `<script src="cdn...">`
   falha e o código aparece sem cor (mas ainda legível). Solução: hospedar
   `highlight.min.js` localmente ou rodar `make interface` antes de perder
   internet.
9. **Atalhos `1`/`2`.** Funcionam fora de inputs/textareas (o listener filtra
   `target.tagName === 'TEXTAREA' || 'INPUT'`). Para alternar rápido entre
   muitos snippets, prefira teclar `1`/`2` + `Enter` em vez de clicar.
