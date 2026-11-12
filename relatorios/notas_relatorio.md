# Notas para os relatórios

Sugestões acumuladas durante o trabalho. Ao final, marcar o que entrou em `limpeza_dados.pdf` ou `dashboard.pdf`.

## Base externa: Cotas de inundação

### Descrição dos dados
- [ ] **Texto sugerido:** A base "Cotas de inundação – 3 m a 5,35 m", publicada pela Prefeitura de Porto Alegre (SMAMUS) em um serviço ArcGIS REST, contém dados geoespaciais vetoriais das áreas de inundação associadas a cada nível do Guaíba. São 25 registros, um por cota, de 3,00 m a 5,30 m em passos de 0,10 m, além da cota de 5,35 m, que corresponde ao recorde de maio de 2024. Cada registro é um polígono múltiplo (MultiPolygon) e traz a cota em centímetros (`contourmax`), a área em hectares (`area_ha`) e a geometria. As áreas vão de cerca de 33,3 mil ha (3,00 m) a 37,8 mil ha (5,35 m).
- [ ] Usar "áreas alcançadas em cada nível", e não "áreas atingidas": a camada traz uma área por cota, não um evento observado. O serviço não publica a metodologia.
- [ ] Ligação com o INCT pelo nível do Guaíba: 3,0 a 5,3 m existem nas duas bases, 5,35 m só nas cotas, 5,4 a 10 m só no INCT.
- [ ] Licença: o serviço não informa licença nem direitos autorais.

### Coleta
- [ ] **Texto sugerido:** Os dados são obtidos por requisições HTTP à API ArcGIS REST da Prefeitura de Porto Alegre, em formato GeoJSON. A coleta foi feita em Python com `requests` em 09/11/2026.
- [ ] GeoJSON foi o formato solicitado. A API também oferece JSON e PBF.
- [ ] Coleta responsável: `robots.txt` do servidor retorna 404 (sem regras publicadas), há pausa de 1 s entre as requisições e os dados brutos ficam guardados localmente, sem repetir downloads.
- [ ] Fonte e data de coleta de cada arquivo ficam em `dados/originais/cotas_coleta.json` (a Tela 2 precisa mostrar as duas).

### Limpeza e preparo
- [ ] **Texto sugerido:** Os polígonos da fonte contêm anéis que passam mais de uma vez pelo mesmo vértice, o que os torna inválidos segundo o padrão OGC adotado pelas bibliotecas Shapely e GeoPandas. Testes nos níveis de 3,00 m e 5,35 m mostraram que a característica já existe nos dados servidos pela API, inclusive no formato nativo do ArcGIS, e não decorre da leitura. Como isso pode comprometer operações espaciais, as geometrias foram reparadas com `make_valid()`. Após o reparo, todos os 25 níveis ficaram válidos, e a área calculada manteve-se igual à informada pela fonte.
- [ ] Evidência: 116 de 6.095 anéis com problema em 3,00 m e 37 de 2.665 em 5,35 m, com as mesmas quantidades no GeoJSON e no formato nativo.
- [ ] Tratar como incompatibilidade com o padrão OGC, não como erro da Prefeitura: o ArcGIS tem regras próprias de geometria.
- [ ] O reparo é preventivo: o cruzamento com o dado bruto não chegou a ser testado.
- [ ] Demais passos: união dos níveis, conversão para SIRGAS 2000 / UTM 22S (EPSG:31982) para medir em metros, criação de `level_m` e remoção de `Shape__Area` e `Shape__Length`, que estão em graus.
- [ ] Sistema de coordenadas: original em SIRGAS 2000 (EPSG:4674), baixado em WGS 84 (EPSG:4326).

### Stack
- [ ] **Texto sugerido:** A coleta foi feita em Python com `requests`, e os dados brutos foram mantidos em GeoJSON. O preparo usou GeoPandas, Shapely e pyproj para unir os níveis, reparar geometrias inválidas e converter as coordenadas para SIRGAS 2000 / UTM 22S (EPSG:31982). O resultado foi armazenado em GeoParquet, por meio do pyarrow.

### Limitações e observações
- [ ] O rio entra na área: um ponto no meio do Guaíba aparece nos 25 níveis, então os hectares não são só terra alagada.
- [ ] Sistema de proteção aparentemente ignorado: Mercado Público e aeroporto aparecem na mancha desde 3 m. É inferência do grupo, com coordenadas aproximadas. Confirmar com a Prefeitura ou comparar com a mancha observada em 2024.
- [ ] Controle: um ponto no Morro Santa Tereza não aparece em nenhum nível.
- [ ] Sem dados abaixo de 3,00 m nem acima de 5,35 m: a Tela 2 fica limitada a essa faixa.
- [ ] Os níveis são quase aninhados, mas não perfeitamente: cerca de 2,4 ha de 3,00 m ficam fora de 3,10 m, e o mesmo ocorre de 3,10 m para 3,20 m. Usar o menor nível que alcança cada rua.
- [ ] Partes desconectadas: em 3,00 m, 108 de 121 partes têm menos de 1 ha; em 5,35 m, 40 de 43.

## Base externa: Eixos de Logradouros

### Descrição e coleta
- [ ] **Texto sugerido:** A base "Eixos de Logradouros", publicada pela Prefeitura de Porto Alegre (SMAMUS) na página Mapas Digitais, representa o sistema viário da cidade como linhas que passam pelo centro geométrico de cada via. Foi produzida pela USIG por restituição fotogramétrica do aerolevantamento de 2010, na escala 1:1000. São 31.416 segmentos de 10.410 logradouros, em shapefile, no sistema SIRGAS 2000 / TM-POA. Os dados foram obtidos por download direto do arquivo ZIP, sem API, em 11/11/2026.
- [ ] Data dos dados: no servidor, os arquivos são de 31/05/2022, e os do ZIP são de 12/05/2022. A ficha técnica diz que a atualização é semanal, mas o arquivo publicado não é atualizado desde 2022. Ruas abertas depois disso podem faltar.
- [ ] Uso: a ficha técnica (Metadados_Logradouros.zip) informa que não há limitações de acesso e uso. A página não publica licença.
- [ ] Coleta responsável: o `robots.txt` permite `/sites/default/files/` (checado em 10/11/2026), e o ZIP é baixado uma vez e guardado localmente. A URL, a data, o tamanho e o SHA-256 ficam em `*.metadata.json`.
- [ ] Os metadados documentam os campos, mas não os códigos de `CDTIPO` (situação) e `CDIDECAT` (categoria). As classes usadas na limpeza são hipóteses do grupo.

### Limitações
- [ ] Eixo não é a pista: a linha é o centro da via, então não diz a largura nem quantas faixas ficam livres.
- [ ] Inclui itens que não são ruas (margem do Guaíba, ilhas, arroios, contornos de praças, escadarias). Eles foram classificados em `feature_class`, e não apagados.
- [ ] Resultado da limpeza: 31.416 → 31.393 segmentos (30.494 ruas, 786 contornos de área, 98 que não são ruas e 15 de pedestres).

## Base do INCT: sugestões para a parte da Sophia

Pontos encontrados ao revisar a limpeza. A decisão de usar cada um é de quem está cuidando dessa parte.

- [ ] Espírito Santo, 3,0 a 3,4 m: 633 a 637 prédios, mas nunca passa de 133 até 10 m, fora o erro de 4,7 m. O erro provável está nos níveis baixos.
- [ ] Boa Vista do Sul, 7,2 e 7,3 m: 686 de 2450 dá exatamente 28%, mas o arquivo traz 29, por erro de ponto flutuante seguido de arredondamento para cima.
- [ ] O nível `5_3m` tem os bairros em ordem diferente (38 posições mudam).
- [ ] Arredondamento para cima: a 5,3 m, o arquivo soma 138.414 pessoas e o cálculo exato dá 136.389 (+1,5%); 128 linhas mostram 100% sem todos os prédios atingidos.
- [ ] Os zeros do Centro Histórico (9,7 e 9,8 m) fazem a curva de população da cidade cair a 9,7 m.
- [ ] Correções propostas:
  - Interpolar Espírito Santo 4,7 m (46), Centro Histórico 9,7 e 9,8 m (2077 e 2103), Lageado 8,1 m (109) e Rubem Berta 8,8 m (268).
  - Corrigir Espírito Santo 3,0 a 3,4 m para 25, com sinalização e aviso ao INCT.
  - Aplicar máximo acumulado no Arquipélago só depois dos demais ajustes. Aplicado antes, espalharia o 637 do Espírito Santo por todos os níveis.
  - Recalcular `percentage` e `affected_population` sem arredondar para cima, mantendo os originais em colunas separadas.
  - Manter e avisar: `high_at_low_level`, `big_jump` e `repeated_value`.

## Geral
- [ ] Registrar todos os usos de IA, como o enunciado exige.
- [ ] A enchente foi em 2024: o README diz "enchentes de 2025".
- [ ] O dashboard deve deixar claro que os números são estimativas de uma simulação.
