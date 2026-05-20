## Pipeline Automatizada para Construção de Dataset Anotado de Code Smells em PHP
#### Uma Abordagem Multi-Ferramenta com Validação Humana

Este documento guia a execução do pipeline para construção de um dataset anotado de code smells em PHP, usando o repositório FakerPHP/Faker como exemplo. O processo é dividido em 5 fases, cada uma com comandos específicos para serem executados via Docker Compose.

### Pré-requisitos para rodar o pipeline:
- Docker e Docker Compose instalados e configurados.
- Acesso ao repositório alvo (FakerPHP/Faker) e permissão para clonar e analisar o código.
- Configuração adequada dos arquivos de ambiente.

**_Informações sobre Pré-requisitos e configuração do ambiente estão disponíveis no arquivo `docs/guia_docker.md` do projeto._**


### Fase 1: Seleção do repositório
Para iniciar o processo, selecione o repositório alvo (neste caso, FakerPHP/Faker) e execute a fase 1 para coletar os metadados iniciais:

```bash
REPO=FakerPHP/Faker docker compose --profile fase1 up fase1
```
_____________________________________________________________________________

### Fase 2: Extração de snippets (requer Fase 1)
Agora, extraia os snippets de código do repositório selecionado, enriquecendo-os com métricas estáticas:

```bash
docker compose --profile fase2 up fase2
```
_____________________________________________________________________________

### Fase 3: Análise estática (requer Fases 1 e 2)
Com os snippets extraídos, rode as ferramentas de análise estática para identificar potenciais code smells e gerar pré-rotulagens:

```bash
docker compose --profile fase3 up fase3
```
_____________________________________________________________________________

### Fase 4.1: Interface de anotação (requer Fases 2 e 3)
Inicie a interface de anotação, que permitirá aos revisores humanos validar e corrigir as pré-rotulagens geradas na fase anterior:

```bash
docker compose --profile fase4 up fase4
```
_____________________________________________________________________________

### Fase 4.2: Anotação Humana

Rode a interface para anotações, acessível em `http://localhost:9090` (ou porta definida em `INTERFACE_PORT`):

```bash
INTERFACE_PORT=9090 docker compose --profile interface up interface 
```
_____________________________________________________________________________

### Fase 4.3: Consolidar (Juntar) anotações dos três revisores
Após os revisores completarem suas anotações, consolide os resultados em um único arquivo JSON.
Para rodar a consolidação, use o comando abaixo, substituindo os nomes dos arquivos das anotação dos revisores, lembrando que os arquivos das anotações devem estar no diretório `output/fase4`:

```bash
docker compose run --rm shell python3 scripts/consolidar_anotacoes.py \
     output/fase4/fase4_anotacoes_fakerphp_faker_dev_1.json \
     output/fase4/fase4_anotacoes_fakerphp_faker_dev_2.json \
     output/fase4/fase4_anotacoes_fakerphp_faker_dev_3.json \
     --output output/fase4/anotacoes_consolidadas.json
```
_____________________________________________________________________________

### Fase 4.3.1: Criar página de desempate
**Observação importante:** Essa etapa só é **_necessária_** se a consolidação indicar que há casos de empate (tie_broken > 0). Caso não haja empates, essa etapa pode ser pulada e o processo segue diretamente para a fase 5.

Quando as anotações dos revisores apresentarem divergências, é necessário criar uma página de desempate para revisão final. O comando abaixo gera um arquivo HTML que pode ser acessado para resolver os casos de empate. Certifique-se de que os arquivos de anotação dos revisores e os dados integrados estejam no diretório `output/fase4`:

```bash
docker compose run --rm shell python3 scripts/consolidar_anotacoes.py \
  output/fase4/fase4_anotacoes_fakerphp_faker_dev_{1,2,3}.json \
  --output output/fase4/anotacoes_consolidadas.json \
  --snippets-data output/fase4/dados_integrados.json \
  --review-html output/fase4/revisao_desempate.html
```
_____________________________________________________________________________

### Fase 4.4: Revisão de Desempate
Quando a consolidação indicar que há casos de empate (tie_broken > 0), é necessário acessar a página de revisão de desempate para tomar a decisão final sobre cada caso. Siga os passos abaixo:


1. Acessar: http://localhost:9090/revisao_desempate.html

2. Tome as decisões para cada caso de empate, escolhendo a anotação correta com base nas informações apresentadas.
3. Clique em "Exportar JSON Final" para gerar um arquivo JSON com as decisões de desempate.
4. Coloque o desempate_*.json no diretório "output/fase4"

_____________________________________________________________________________

### Fase 4.5: Aplicar desempate gerando anotações final
Antes da fase 5, é necessário aplicar as decisões de desempate para gerar o arquivo final de anotações. O comando abaixo realiza essa aplicação, gerando o arquivo `anotacoes_final.json` que será usado na fase 5:

```bash
docker compose run --rm shell python3 scripts/aplicar_desempate.py \
  --consolidado output/fase4/anotacoes_consolidadas.json \
  --desempate output/fase4/desempate_*.json \
  --output output/fase4/anotacoes_final.json
```
_____________________________________________________________________________

### Fase 5: com anotações finais in php-codesmell-dataset
Está é a fase final do pipeline, onde as anotações finais são integradas para gerar o dataset anotado de code smells em PHP. Certifique-se de que os arquivos de metadados, snippets com métricas, pré-rotulagens e anotações finais estejam nos diretórios corretos antes de rodar o comando abaixo:

```bash
docker compose run --rm shell python3 scripts/fase5_validar_dataset.py \
  --fase1 output/fase1/repositorio_metadata.json \
  --fase2 output/fase2/snippets_com_metricas.json \
  --fase3 output/fase3/pre_rotulacao.json \
  --annotations output/fase4/anotacoes_final.json \
  --output output/fase5 2>&1 | tail -40
```
______________________________________________________________________________
