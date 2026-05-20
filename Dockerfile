# =============================================================================
# Dockerfile — Pipeline de Construção de Dataset de Code Smells PHP
# =============================================================================
# Multi-stage build para otimizar tamanho da imagem
# Imagem final: PHP 8.2 + Python 3 + ferramentas de análise estática
# =============================================================================

# ─────────────────────────────────────────────────────────────
# Stage 1: Download de ferramentas PHAR
# ─────────────────────────────────────────────────────────────
FROM php:8.2-cli AS tools-downloader

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tools

# Baixar ferramentas de análise estática como .phar
RUN curl -fSL https://github.com/phpmd/phpmd/releases/latest/download/phpmd.phar -o phpmd.phar \
    && curl -fSL https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar -o phpstan.phar \
    && curl -fSL https://github.com/vimeo/psalm/releases/latest/download/psalm.phar -o psalm.phar \
    && curl -fSL https://github.com/PHPCSStandards/PHP_CodeSniffer/releases/latest/download/phpcs.phar -o phpcs.phar \
    && chmod +x *.phar \
    && curl -fSL https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-6.2.1.4610-linux-x64.zip -o /tmp/sonar-scanner.zip \
    && unzip -q /tmp/sonar-scanner.zip -d /tmp/ \
    && mv /tmp/sonar-scanner-*-linux-x64 /tools/sonar-scanner \
    && rm /tmp/sonar-scanner.zip

# ─────────────────────────────────────────────────────────────
# Stage 2: Instalação de dependências Composer
# ─────────────────────────────────────────────────────────────
FROM composer:2 AS composer-deps

WORKDIR /app/config
COPY config/composer.json config/composer.lock* ./
RUN composer install --no-dev --no-interaction --optimize-autoloader --ignore-platform-reqs 2>/dev/null \
    || composer install --no-dev --no-interaction --ignore-platform-reqs

# ─────────────────────────────────────────────────────────────
# Stage 3: Imagem final
# ─────────────────────────────────────────────────────────────
FROM php:8.2-cli

LABEL maintainer="CodeSmell Dataset Pipeline"
LABEL description="Ambiente completo para construção de dataset de code smells PHP"
LABEL version="1.0"

# Instalar dependências do sistema + Python 3
RUN apt-get update && apt-get install -y --no-install-recommends \
        # PHP extensions dependencies
        libxml2-dev \
        libzip-dev \
        libonig-dev \
        # Python e pip
        python3 \
        python3-pip \
        python3-venv \
        python3-setuptools \
        python3-wheel \
        # Ferramentas de sistema
        git \
        curl \
        wget \
        unzip \
        jq \
        ca-certificates \
        # Java JRE (requerido pelo SonarQube Scanner)
        default-jre-headless \
    && docker-php-ext-install -j$(nproc) \
        xml \
        mbstring \
        zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Instalar Composer
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# Criar usuário não-root
RUN groupadd -g 1000 codesmell \
    && useradd -u 1000 -g codesmell -m -s /bin/bash codesmell \
    && mkdir -p /app /app/output /app/repos /app/tools \
    && chown -R codesmell:codesmell /app

WORKDIR /app

# Copiar ferramentas PHAR do stage 1
COPY --from=tools-downloader --chown=codesmell:codesmell /tools/*.phar /app/tools/
COPY --from=tools-downloader --chown=codesmell:codesmell /tools/sonar-scanner /app/tools/sonar-scanner

# Criar symlinks para as ferramentas
RUN ln -s /app/tools/phpmd.phar /usr/local/bin/phpmd \
    && ln -s /app/tools/phpstan.phar /usr/local/bin/phpstan \
    && ln -s /app/tools/psalm.phar /usr/local/bin/psalm \
    && ln -s /app/tools/phpcs.phar /usr/local/bin/phpcs

# Copiar dependências Composer do stage 2
COPY --from=composer-deps --chown=codesmell:codesmell /app/config/vendor /app/config/vendor

# Copiar arquivos do projeto
COPY --chown=codesmell:codesmell config/ /app/config/
COPY --chown=codesmell:codesmell scripts/ /app/scripts/
# Instalar dependências Python (sem venv, estamos em container)
RUN pip3 install --no-cache-dir --break-system-packages -r /app/config/requirements.txt 2>/dev/null \
    || pip3 install --no-cache-dir -r /app/config/requirements.txt

# Permissões de execução
RUN chmod +x /app/scripts/*.sh /app/scripts/*.py 2>/dev/null || true \
    && chmod +x /app/docker/*.sh

# Criar estrutura de output
RUN mkdir -p /app/output/fase{1,2,3,4,5} \
    && chown -R codesmell:codesmell /app

# Mudar para usuário não-root
USER codesmell

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PHP_MEMORY_LIMIT=512M \
    COMPOSER_ALLOW_SUPERUSER=0 \
    PROJECT_DIR=/app \
    PATH="/app/tools:${PATH}"

# Porta para interface web
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD php -v > /dev/null 2>&1 && python3 --version > /dev/null 2>&1

# Comando padrão: shell interativo
CMD ["bash"]
