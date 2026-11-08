# Log da limpeza da base do INCT

Registro de cada passo da limpeza: o que foi feito, por que, o que apareceu ao rodar e o que foi decidido.
Este conteúdo alimenta a seção "Limpeza da base fornecida" do README e o relatório `limpeza_dados.pdf`.

## Estrutura do código
- `app.py`: fornece os caminhos (`dados/originais/data.json` e `dados/processados/anomalies.csv`) e chama **uma única função**, `generate_anomaly_report`.
- `scripts/inct_cleaning.py`: biblioteca com uma função por etapa (carga, normalização, detecção, relatório e os esqueletos das etapas 5 a 7).
- `scripts/inct_checks.py`: as verificações de anomalias e as funções compartilhadas que montam a tabela de anomalias.
- O arquivo original nunca é alterado.
- `scripts/*_old.py`: versão anterior, mantida só como referência. O código atual foi reescrito etapa por etapa a partir dela.

**Caminho do dado:** `data.json` → carga → normalização → detecção → `anomalies.csv`.

---

## Etapa 1: Carga (`load_raw_data`)
**O que faz:** lê o `data.json` e devolve uma tabela com uma linha por nível e bairro.

**Como:**
- O JSON é lido como pares ordenados (`object_pairs_hook=list`), para que um bairro repetido dentro do mesmo nível vire uma linha repetida, e não sobrescreva a anterior em silêncio.
- O nível vem da **chave** (`"3_1m"` vira `3.1`), e não da posição no arquivo, porque o enunciado avisa para não assumir a ordem. A conversão (`parse_level_key`) usa um padrão de texto e devolve `NaN` para chaves fora do padrão, em vez de parar o programa.
- Guarda a chave original (`level_key`) e o nome original do bairro (`neighborhood_raw`), para a anomalia poder mostrar o que veio no arquivo.
- Garante as 5 colunas de dados, mesmo que alguma falte no arquivo.

**Resultado ao rodar:** `(6674, 8)`. São 6.674 linhas (71 níveis × 94 bairros, como no enunciado) e 8 colunas: `level_key`, `level_m`, `neighborhood_raw` e os 5 campos.

---

## Etapa 2: Normalização (`normalize_data`)
**O que faz:** padroniza a forma dos dados, sem corrigir valores e sem remover linhas.

**Como:**
- **Nomes dos bairros:** padroniza espaços, unicode e apóstrofos. Nomes que diferem só por acento, maiúscula ou apóstrofo são tratados como o mesmo bairro e ficam com a grafia mais comum. Gera a coluna `neighborhood`, e o nome original continua em `neighborhood_raw`.
- **Números:** as 5 colunas passam por `pd.to_numeric`. Texto que não converte vira vazio (`NaN`).
- **Registro:** cada nome renomeado e cada texto convertido vira uma linha no formato das anomalias, que entra no CSV final.

**Resultado ao rodar:**
- Formato `(6674, 9)`, com a coluna `neighborhood` a mais.
- **94 bairros** distintos.
- **0 mudanças registradas:** nenhum nome precisou ser renomeado e nenhum campo numérico tinha texto. Nesta parte a base já veio limpa.

---

## Etapa 3: Detecção de anomalias (`detect_anomalies`)
**O que faz:** roda todas as verificações sobre a tabela normalizada. **Só lê os dados, nunca corrige.** Cada verificação devolve linhas no mesmo formato.

| Grupo | Verificação | Origem |
|---|---|---|
| Estrutura | níveis faltando, fora da grade 3,0–10,0 ou ilegíveis | enunciado |
| | contagem diferente de 94 bairros e bairro ausente em algum nível | enunciado |
| | registros duplicados (mesmo nível e bairro) | enunciado |
| | valores vazios nos 5 campos | enunciado |
| | campos que não são os 5 documentados | adição da equipe |
| | nomes de bairro parecidos (possível mesma grafia) | adição da equipe |
| Constantes | `total_buildings` e `population` variando entre níveis | enunciado |
| Coerência | negativos, prédios afetados acima do total, `total_buildings` igual a 0 | enunciado |
| | `percentage` diferente de afetados ÷ total × 100 | enunciado |
| | `affected_population` diferente de população × percentual ÷ 100 | enunciado |
| Comportamento | prédios afetados **diminuindo** quando o nível sobe | enunciado |
| | prédios afetados caindo para **zero** depois de já terem sido afetados (dado ausente preenchido com 0?) | adição da equipe |
| | valor isolado muito acima do nível anterior e do seguinte (provável erro de digitação) | adição da equipe |
| | saltos grandes, valores repetidos por muitos níveis seguidos, percentual alto em nível baixo | adição da equipe |
| Escala | bairro muito fora do padrão, soma da população longe do total da cidade | adição da equipe |

**Tolerância do percentual:** o arquivo guarda o `percentage` como número inteiro. Por exemplo, 28 de 589 prédios dá 4,75%, e o arquivo traz 5. Como a diferença para o cálculo exato não passou de 1 ponto, o grupo considerou que é arredondamento e não erro. Por isso o código aceita diferenças de até **1 ponto** e só marca como anomalia o que passar disso. Com uma tolerância menor (0,01), 2.620 linhas seriam marcadas à toa.

**Limite dessa escolha:** erros menores que 1 ponto não aparecem como anomalia.

---

## Etapa 4: Relatório (`generate_anomaly_report`)
**O que faz:** junta as mudanças da normalização com as anomalias da detecção e grava `dados/processados/anomalies.csv`.

**Como:**
- Colunas: `type`, `category`, `severity`, `neighborhood`, `level_m`, `field`, `value`, `expected`, `description`.
- Ordenado por gravidade (erro, aviso, info).
- Cria a pasta de saída se ela não existir. O arquivo é sempre sobrescrito, então rodar de novo gera um relatório novo.

**Resultado ao rodar o código atual:** 76 anomalias. Nenhuma é de estrutura nem de coerência entre campos (6.674 linhas, 94 bairros em todos os 71 níveis, sem duplicados nem vazios).

| Tipo | Qtde | Severidade |
|---|---|---|
| `value_decreased` | 12 | erro |
| `zero_after_affected` | 4 | erro |
| `isolated_high_value` | 1 | erro |
| `high_at_low_level` | 52 | aviso |
| `big_jump` | 6 | info |
| `repeated_value` | 1 | info |

---

## Achados da análise do JSON
Os erros de verdade, vistos nas séries por nível:
- **Valor isolado alto:** Espírito Santo, 4,7 m: `46 → 2101 → 47`. O 2101 é o erro.
- **Zeros no meio da série:** Centro Histórico 9,7 e 9,8 m (`2050 → 0 → 0 → 2130`), Lageado 8,1 m (`108 → 0 → 110`) e Rubem Berta 8,8 m (`252 → 0 → 285`). Parece dado ausente preenchido com 0.
- **Espírito Santo, 3,0 a 3,4 m:** `637, 637, 637, 637, 633` e depois `25, 25, 27...`. Não dá para saber qual lado está certo sem informação do terreno.
- **Arquipélago:** oscila entre 4680, 4685, 4674 e 4688 (total 4688), com diferença de até 11 prédios. Parece ruído da simulação, com efeito desprezível, porque o percentual fica em 100%.

Sobre os arredondamentos:
- O `percentage` é o arredondamento **para cima** do cálculo exato em 6.674 de 6.674 linhas.
- O `affected_population` é o arredondamento para cima de `população × percentage ÷ 100` em 6.674 de 6.674 linhas.
- Com isso a população afetada fica acima do cálculo exato: em média 27 pessoas por linha, e até 501. É um viés a avisar no dashboard.

Observações para o relatório:
- 40 bairros nunca são afetados até 10 m.
- Pessoas por prédio vão de 0,78 (São Caetano) a 10,05 (Jardim Europa). O total de prédios vem do OpenStreetMap e inclui os não residenciais.
- `high_at_low_level`, `big_jump` e `repeated_value` só poderiam ser confirmados com a altitude do terreno. Por enquanto ficam como "manter e avisar".

---

## Etapas 5 a 7: ainda não implementadas
- **Etapa 5, correção:** a política para cada anomalia (corrigir, interpolar, descartar ou manter e avisar) será decidida depois de revisar o `anomalies.csv`.
- **Etapa 6, revalidação:** roda as verificações de novo e confirma que a grade bairro × nível é 94 × 71, sem vazios.
- **Etapa 7, saída:** grava o CSV limpo em formato longo e **devolve o caminho dele**.

**Decisão sobre vetores e índice:** a montagem dos vetores por bairro e o cálculo do índice ficam no **dashboard**, e não na biblioteca. O índice usa `round((nivel - 3) * 10)`, porque a conta sem `round` pode dar `0.9999999999999991` em vez de `1`. A etapa 6 é o que garante ao dashboard que todos os vetores têm 71 posições.
