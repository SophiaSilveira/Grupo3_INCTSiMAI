# Grupo3_INCTSiMAI
Um repositório para o projeto extensionista da matéria de Coleta e Análise de dados.

Objetivo propor um dashboard de duas telas que contenham visões com opções de melhorias a ferramenta: http://vhlab.com.br/INCT/floods/ 

## Proposta:
Visto a magnitude dos prejuízos causados pelas enchentes de 2025 na cidade de Porto Alegre, decidimos elaborar uma análise capaz de impactar positivamente na vida das pessoas em caso da recorrência de um evento similar.

Nas diversas faces afetadas por este evento traumático, identificamos a dificuldade de locomoção como um dos assuntos mais pertinentes para estudo. Todos lembramos o quão tramático foi o desafio do transporte, de pessoas e de bens, na entrada e saída de Porto Alegre, principalmente na região central. Tamanha foi a urgência que justificou a construção de um corredor improvisado no acesso da cidade junto à rodoviária, demolindo passarelas ali existentes.

Neste âmbito, decidimos desenvolver uma análise de dados capaz de responder ao usuário quais rodovias da cidade se encontram afetadas pelo nível d'água e quais estão operantes. Por meio de um slider, o usuário pode navegar através das diferentes cotas do nível do Guaíba, visualizando no mapa as curvas de nível de inundação na cidade e quais rodovias deixam de ser trafegáveis. A ideia é que, no caso de nova tragédia, o mapa pudesse ser utilizado como referência para identificar rotas ainda válidas, seja para fuga ou transporte de mantimentos.


## Bancos:
### INCT
  #### Extração
  - Formato json
  - Fornecido pela empresa
    
  #### Features
  - cotação
  - bairro
  - affected_buildings
  - total_buildings
  - percentage
  - population
  - affected_population
    
  #### Análises
  - Um controle deslizante do nível do Guaíba, de 3,0 m a 10,0 m em passos de 0,1 m, que atualiza todos os elementos da tela.
  - Indicadores no topo: pessoas afetadas, prédios afetados e bairros atingidos no nível escolhido.
  - Um gráfico com a porcentagem de prédios afetados em cada bairro atingido. Um mapa dos bairros colorido por essa porcentagem é opcional e conta como diferencial na avaliação do dashboard.
  - Uma curva da população afetada em toda a cidade por nível do rio, com o nível recorde de maio de 2024 (5,35 m) marcado.
  - Um ranking dos bairros mais afetados no nível escolhido.
  - Um aviso visível das limitações dos dados (ver a seção "Os dados do INCT")


### Cotas de Inundação Prefeitura de Porto Alegre
  #### Extração
  - link: https://gis-smamus.portoalegre.rs.gov.br/server/rest/services/01_PUBLICACOES/cotas_inundacao_300_535/FeatureServer/0
  - Consumo: API -> padrão ArcGIS REST -> dados geográficos por requisições HTTP
    
#### Features
  | Campo | Descrição | Tipo |
  |---|---|---|
  | `objectid` | Identificador do registro | Inteiro |
  | `contourmax` | Cota de inundação (cm) | Decimal |
  | `area_ha` | Área em hectares | Decimal |
  | `Shape__Area` | Área calculada da geometria | Decimal |
  | `Shape__Length` | Comprimento do contorno | Decimal |
  | `geometry` | Polígono geográfico | Geometria |

  #### Análises
  - Rotas de evacuação direta das regiões afetadas para qualquer outro bairro (por nível)
  - Rotas de A até B evitando regiões afetadas (por nível)
