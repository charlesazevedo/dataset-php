# 🐳 Guia Docker — Pipeline de Code Smells PHP

Guia completo para executar o pipeline de construção de dataset de Code Smells PHP
usando Docker, sem necessidade de instalar PHP, Python ou ferramentas localmente.

---

## Índice

- [Pré-requisitos](#pré-requisitos)
- [Início Rápido](#início-rápido)
- [Comandos Disponíveis](#comandos-disponíveis)
- [Execução por Fases](#execução-por-fases)
- [Interface Web](#interface-web)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Modo Interativo](#modo-interativo)
- [Makefile (Atalhos)](#makefile-atalhos)
- [Estrutura de Arquivos Docker](#estrutura-de-arquivos-docker)
- [Troubleshooting](#troubleshooting)
- [Plataformas](#plataformas)

---

## Pré-requisitos

| Requisito | Versão Mínima | Verificar |
|-----------|---------------|-----------|
| Docker | 20.10+ | `docker --version` |
| Docker Compose | v2.0+ | `docker compose version` |
| Espaço em disco | ~2 GB | Para imagem + dados |

### Instalação do Docker

- **Linux (Ubuntu/Debian)**:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  # Logout e login novamente
  ```

- **macOS**: [Docker Desktop para Mac](https://www.docker.com/products/docker-desktop/)

- **Windows**: [Docker Desktop para Windows](https://www.docker.com/products/docker-desktop/) (requer WSL2)

---

## Início Rápido

```bash
# 1. Clone o projeto (se ainda não fez)
git clone <url-do-repositorio> php-codesmell-dataset
cd php-codesmell-dataset

# 2. Construa a imagem
docker compose build app

# 3. Verifique o ambiente
docker compose --profile setup up setup

# 4. Execute o pipeline completo
REPO=FakerPHP/Faker docker compose --profile run up run-all

# 5. Veja os resultados
ls -la output/fase5/
```

Ou usando o **Makefile** (mais simples):

```bash
make build                        # Constrói imagem
make setup                        # Verifica ambiente
make run REPO=FakerPHP/Faker      # Executa tudo
make interface                    # Abre interface web
```

---

## Comandos Disponíveis

### Via Docker Compose

| Comando | Descrição |
|---------|-----------|
| `docker compose build app` | Constrói a imagem Docker |
| `docker compose --profile setup up setup` | Verifica o ambiente |
| `docker compose --profile run up run-all` | Executa todas as 5 fases |
| `docker compose --profile interface up interface` | Interface web (porta 8080) |
| `docker compose --profile shell run --rm shell` | Terminal interativo |

### Via Makefile

| Comando | Descrição |
|---------|-----------|
| `make help` | Lista todos os comandos |
| `make build` | Constrói a imagem |
| `make setup` | Verifica o ambiente |
| `make run` | Executa todas as fases |
| `make run REPO=owner/name` | Executa com repositório específico |
| `make interface` | Interface web |
| `make shell` | Terminal interativo |
| `make exec CMD='...'` | Executa comando no container |
| `make clean` | Remove containers |
| `make clean-all` | Remove tudo |
| `make status` | Status dos containers |

### Via Scripts de Conveniência

```bash
bash docker/docker-enter.sh                  # Shell interativo
bash docker/docker-enter.sh php -v           # Executar comando
bash docker/docker-exec.sh phpmd --version   # Executar ferramenta
bash docker/docker-clean.sh                  # Limpar containers
bash docker/docker-clean.sh --all            # Limpar tudo
```

---

## Execução por Fases

Execute fases individuais quando precisar reprocessar uma etapa específica:

```bash
# Fase 1: Seleção do repositório
REPO=laravel/framework docker compose --profile fase1 up fase1

# Fase 2: Extração de snippets (requer Fase 1)
docker compose --profile fase2 up fase2

# Fase 3: Análise estática (requer Fases 1 e 2)
# 5 ferramentas: PHPMD, PHPStan, Psalm, PHPCS, SonarQube Scanner
# SonarQube requer SONAR_TOKEN (pula automaticamente se não definido)
docker compose --profile fase3 up fase3

# Fase 4: Interface de anotação (requer Fases 2 e 3)
docker compose --profile fase4 up fase4

# Fase 5: Validação e dataset final (requer Fases 1, 2 e 3)
docker compose --profile fase5 up fase5
```

Ou via Makefile:

```bash
make fase1 REPO=laravel/framework
make fase2
make fase3
make fase4
make fase5
```

### Dependências entre fases

```
Fase 1 (Repositório) → Fase 2 (Snippets) → Fase 3 (Análise) → Fase 4 (Interface)
         ↓                     ↓                    ↓
         └─────────────────────┴────────────────────→ Fase 5 (Dataset Final)
```

### Fluxo completo com anotação humana (Fase 4.1–4.5)

Após rodar as Fases 1–3, a Fase 4 se desdobra em etapas manuais (anotação) + scripts de consolidação:

```bash
# ── 4.1: Gerar interface ──
docker compose --profile fase4 up fase4

# ── 4.2: Servir interface para os anotadores ──
INTERFACE_PORT=9090 docker compose --profile interface up interface
# Cada dev acessa http://localhost:9090, anota e clica em 📥 Exportar JSON

# ── 4.3: Consolidar anotações dos 3 revisores (votação por maioria) ──
docker compose run --rm shell python3 scripts/consolidar_anotacoes.py \
  output/fase4/fase4_anotacoes_<repo>_dev_{1,2,3}.json \
  --output output/fase4/anotacoes_consolidadas.json \
  --snippets-data output/fase4/dados_integrados.json \
  --review-html output/fase4/revisao_desempate.html

# ── 4.4: Se aparecer tie_broken > 0, revisão de desempate ──
# 1. Acessar http://localhost:9090/revisao_desempate.html
# 2. Escolher o rótulo final para cada caso em conflito
# 3. Clicar em 📥 Exportar JSON Final
# 4. Mover o desempate_*.json para output/fase4/

# ── 4.5: Aplicar desempate gerando anotações finais ──
docker compose run --rm shell python3 scripts/aplicar_desempate.py \
  --consolidado output/fase4/anotacoes_consolidadas.json \
  --desempate output/fase4/desempate_*.json \
  --output output/fase4/anotacoes_final.json
```

### Fase 5 com anotações finais

```bash
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
  --fase1 output/fase1/repositorio_metadata.json \
  --fase2 output/fase2/snippets_com_metricas.json \
  --fase3 output/fase3/pre_rotulacao.json \
  --annotations output/fase4/anotacoes_final.json \
  --output output/fase5
```

Se não houver anotações manuais, omita `--annotations` — a Fase 5 usa os pré-rótulos da Fase 3 como fallback.

---

## Fluxo com Múltiplos Repositórios (Batch)

O pipeline processa um repositório por vez (symlink `output/fase1/repositorio_metadata.json`).
Para processar vários, alterne o symlink e arquive os outputs entre execuções.

### 1. Selecionar N repositórios automaticamente

```bash
docker compose run --rm shell python3 scripts/fase1_selecionar_repositorio.py --auto-select 5
```

> Só aceita repos com licença MIT/Apache-2.0/BSD, ≥1000 stars, ≥100 forks, PHP, push recente.
> Metadados salvos em `output/fase1/batch_selection.json` e `output/fase1/repositorio_metadata_NN_repo.json`.

### 2. Processar o repo ativo

```bash
make fase2 && make fase3 && make fase4 && make fase5
# ou manualmente:
docker compose --profile fase2 up fase2
docker compose --profile fase3 up fase3
docker compose --profile fase4 up fase4
# ... anotação + consolidação + desempate (ver seção acima) ...
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py ...
```

### 3. Arquivar e trocar de repo

```bash
# Arquivar dados do repo atual
mv output output_01_SecLists
mkdir -p output/fase{1,2,3,4,5}

# Trocar symlink para o próximo repo do batch (cache hit, sem API)
docker compose run --rm shell python3 scripts/fase1_selecionar_repositorio.py --repo coollabsio/coolify
# ou:
REPO=coollabsio/coolify docker compose --profile fase1 up fase1

# Repetir passo 2
```

---

## Interface Web

A interface de anotação pode ser acessada via navegador:

```bash
# Subir interface na porta 8080 (padrão)
docker compose --profile interface up interface

# Porta customizada
INTERFACE_PORT=9090 docker compose --profile interface up interface

# Via Makefile
make interface
make interface INTERFACE_PORT=9090
```

Acesse: **http://localhost:8080** (ou a porta configurada)

> **Nota**: A interface requer que pelo menos as Fases 1-4 tenham sido executadas.

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `REPO` | (vazio) | Repositório GitHub (ex: `laravel/framework`) |
| `GITHUB_TOKEN` | (vazio) | Token GitHub para evitar rate limiting |
| `INTERFACE_PORT` | `8080` | Porta da interface web |
| `SONAR_PORT` | `9000` | Porta do dashboard SonarQube |
| `PHP_MEMORY_LIMIT` | `512M` | Limite de memória PHP |

### Uso com GitHub Token (recomendado)

```bash
# Exportar token
export GITHUB_TOKEN=ghp_seu_token_aqui

# Executar
make run REPO=laravel/framework

# Ou via docker compose
GITHUB_TOKEN=ghp_xxx REPO=laravel/framework docker compose --profile run up run-all
```

### Uso com SonarQube Scanner (Fase 3)

O SonarQube Scanner agora roda **localmente** via serviço `sonarqube` no docker-compose. Nenhuma configuração adicional é necessária — o container sobe automaticamente quando a Fase 3 é executada e a análise é salva em `output/fase3/sonar_output.json`.

- **Dashboard web:** http://localhost:9000 (credenciais: `admin` / `admin`)
- **Primeira execução:** o Docker baixa a imagem `sonarqube:community` (~500 MB) e o SonarQube leva ~60s para iniciar
- A Fase 3 aguarda automaticamente o SonarQube estar pronto

Para desligar o SonarQube após o uso:
```bash
docker compose --profile sonar down
```

> Os resultados também ficam disponíveis no dashboard web enquanto o container estiver rodando.

### Criar arquivo .env (alternativa)

```bash
# Criar .env na raiz do projeto
cat > .env << 'EOF'
GITHUB_TOKEN=ghp_seu_token_aqui
INTERFACE_PORT=8080
PHP_MEMORY_LIMIT=512M
EOF
```

---

## Modo Interativo

Para explorar o container ou executar comandos avulsos:

```bash
# Entrar no container
make shell
# ou
bash docker/docker-enter.sh

# Dentro do container, você tem acesso a:
php -v                           # PHP 8.2
python3 --version                # Python 3
phpmd --version                  # PHPMD
phpstan --version                # PHPStan
psalm --version                  # Psalm
phpcs --version                  # PHPCS
composer --version               # Composer

# Executar scripts diretamente
python3 scripts/fase1_selecionar_repositorio.py --help
php scripts/fase2_extrair_snippets.php --help
```

---

## Estrutura de Arquivos Docker

```
php-codesmell-dataset/
├── Dockerfile                    ← Imagem multi-stage (PHP + Python + tools)
├── docker-compose.yml            ← Orquestração de serviços e profiles
├── .dockerignore                 ← Otimização do build context
├── Makefile                      ← Atalhos de comandos
├── docs/guia_docker.md            ← Este guia
│
├── docker/                       ← Scripts Docker
│   ├── docker-setup.sh           ← Verificação do ambiente
│   ├── docker-run-all.sh         ← Executa todas as fases
│   ├── docker-enter.sh           ← Shell interativo
│   ├── docker-exec.sh            ← Executa comandos específicos
│   └── docker-clean.sh           ← Limpeza do ambiente
│
├── output/                       ← 📁 Persistido via volume
│   ├── fase1/                    ← Metadados do repositório
│   ├── fase2/                    ← Snippets extraídos
│   ├── fase3/                    ← Análise estática
│   ├── fase4/                    ← Interface de anotação
│   └── fase5/                    ← Dataset final
│
└── repos/                        ← 📁 Persistido via volume
```

---

## Troubleshooting

### Erro: "permission denied"

```bash
# Se os outputs foram criados como root:
sudo chown -R $USER:$USER output/ repos/
```

### Erro: "port already in use"

```bash
# Mudar a porta da interface
make interface INTERFACE_PORT=9090
```

### Build lento / cache não funciona

```bash
# Reconstruir sem cache
make build-no-cache
```

### Container não inicia

```bash
# Verificar logs
docker compose logs

# Verificar status
make status

# Limpar e tentar novamente
make clean
make build
```

### Erro de memória no PHP

```bash
# Aumentar limite de memória
PHP_MEMORY_LIMIT=1G docker compose --profile run up run-all
```

### GitHub rate limit

```bash
# Usar token de acesso pessoal
export GITHUB_TOKEN=ghp_seu_token
make run REPO=laravel/framework
```

---

## Plataformas

### Linux

Funciona nativamente. Instale Docker via `curl -fsSL https://get.docker.com | sh`.

### macOS

Use Docker Desktop. O Docker Compose v2 já vem incluso.

### Windows

1. Instale [Docker Desktop](https://www.docker.com/products/docker-desktop/) com backend WSL2
2. Abra terminal WSL2 ou PowerShell
3. No PowerShell, use `$env:REPO="laravel/framework"` em vez de `REPO=...`

```powershell
# PowerShell
$env:REPO = "laravel/framework"
docker compose --profile run up run-all

# Ou use o Makefile via WSL2
wsl make run REPO=laravel/framework
```

---

## Arquitetura da Imagem Docker

```
┌─────────────────────────────────────────────┐
│            Stage 1: tools-downloader        │
│  Baixa PHPMD, PHPStan, Psalm, PHPCS (.phar) │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┼──────────────────────────┐
│            Stage 2: composer-deps           │
│  Instala nikic/php-parser                   │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Stage 3: Imagem Final            │
│  PHP 8.2 + Python 3 + Git + Composer        │
│  + Ferramentas PHAR + Deps Composer         │
│  + Deps Python + Scripts do projeto         │
│  Usuário: codesmell (não-root)              │
└─────────────────────────────────────────────┘
```

**Tamanho estimado da imagem**: ~500 MB (otimizado com multi-stage build)
