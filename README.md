# Grupo3_INCTSiMAI
Um repositório para o projeto extensionista da matéria de Coleta e Análise de dados.

Objetivo propor um dashboard de duas telas que contenham visões com opções de melhorias a ferramenta: http://vhlab.com.br/INCT/floods/ 

## Proposta:
Visto a magnitude dos prejuízos causados pelas enchentes de 2025 na cidade de Porto Alegre, decidimos elaborar uma análise capaz de impactar positivamente na vida das pessoas em caso da recorrência de um evento similar.

Nas diversas faces afetadas por este evento traumático, identificamos a dificuldade de locomoção como um dos assuntos mais pertinentes para estudo. Todos lembramos o quão traumático foi o desafio do transporte, de pessoas e de bens, na entrada e saída de Porto Alegre, principalmente na região central. Tamanha foi a urgência que justificou a construção de um corredor improvisado no acesso da cidade junto à rodoviária, demolindo passarelas ali existentes.

Neste âmbito, decidimos desenvolver uma análise de dados capaz de responder ao usuário quais rodovias da cidade se encontram afetadas pelo nível d'água e quais estão operantes. Por meio de um slider, o usuário pode navegar através das diferentes cotas do nível do Guaíba, visualizando no mapa as curvas de nível de inundação na cidade e quais rodovias deixam de ser trafegáveis. A ideia é que, no caso de nova tragédia, o mapa pudesse ser utilizado como referência para identificar rotas ainda válidas, seja para fuga ou transporte de mantimentos.


<details>
<summary><b>Fase 1: Levantamento da base externa</b></summary>

---

### Bancos:
#### INCT
##### Extração
- Formato json
- Fornecido pela empresa

##### Features
- cotação
- bairro
- affected_buildings
- total_buildings
- percentage
- population
- affected_population

##### Análises
- Um controle deslizante do nível do Guaíba, de 3,0 m a 10,0 m em passos de 0,1 m, que atualiza todos os elementos da tela.
- Indicadores no topo: pessoas afetadas, prédios afetados e bairros atingidos no nível escolhido.
- Um gráfico com a porcentagem de prédios afetados em cada bairro atingido. Um mapa dos bairros colorido por essa porcentagem é opcional e conta como diferencial na avaliação do dashboard.
- Uma curva da população afetada em toda a cidade por nível do rio, com o nível recorde de maio de 2024 (5,35 m) marcado.
- Um ranking dos bairros mais afetados no nível escolhido.
- Um aviso visível das limitações dos dados (ver a seção "Os dados do INCT")

---

#### Cotas de Inundação Prefeitura de Porto Alegre
##### Extração
- link: https://gis-smamus.portoalegre.rs.gov.br/server/rest/services/01_PUBLICACOES/cotas_inundacao_300_535/FeatureServer/0
- Consumo: API pelo padrão ArcGIS REST onde recebemos dados geográficos por requisições HTTP

##### Features
| Campo | Descrição | Tipo |
|---|---|---|
| `contourmax` | Cota de inundação (cm) | Decimal |
| `area_ha` | Área em hectares | Decimal |
| `geometry` | Polígono geográfico | Geometria |

##### Análises
- Área alagada (ha) em cada nível do Guaíba, de 3,00 m a 5,35 m
- Área que passa a ser alagada a cada 10 cm a mais de nível

---

#### Eixos de Logradouros Prefeitura de Porto Alegre
##### Extração
- link: https://prefeitura.poa.br/smamus/planejamento-urbano/mapas-digitais
- Consumo: download direto do shapefile (ZIP), sem API
- Formato: linhas no centro de cada via, 31.416 trechos de 10.410 ruas
- Coordenadas: SIRGAS 2000 / TM-POA, em metros

##### Features
| Campo | Descrição | Tipo |
|---|---|---|
| `CDLOG` | Código do logradouro | Inteiro |
| `CDSEG` | Código do trecho | Inteiro |
| `NMIDELOG` | Nome do logradouro | Texto |
| `CDIDECAT` | Categoria (rua, avenida, praça...) | Texto |
| `CDTIPO` | Situação do logradouro | Inteiro |
| `geometry` | Linha do eixo da via | Geometria |

##### Análises
- Ruas alagadas em cada nível do Guaíba
- Nível a partir do qual cada rua fica intransitável
- Extensão (km) de vias alagadas por nível

---

### Objetivo
- Rotas de evacuação direta das regiões afetadas para qualquer outro bairro (por nível)
- Rotas de A até B evitando regiões afetadas (por nível)

</details>

<details>
<summary><b>Fase 2: Limpeza de dados e EDA</b></summary>

---

### Limpeza da base fornecida
_Registro de tudo o que foi feito na base do INCT e o porquê de cada decisão._

<!-- Preencher conforme a limpeza avançar: etapa, o que foi feito, motivo da decisão. -->

### EDA
_A documentar._

</details>
