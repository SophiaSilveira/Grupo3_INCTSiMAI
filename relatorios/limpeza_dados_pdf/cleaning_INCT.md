# Log da limpeza da base do INCT

Registro de cada passo da limpeza: o que foi feito, por que, o que apareceu ao rodar e o que foi decidido.
Este conteúdo alimenta a seção "Limpeza da base fornecida" do README e o relatório `limpeza_dados.pdf`.

> **ARQUIVO DE BASE PARA O DASHBOARD: `dados/processados/inct_limpo.json`**
> É a base do INCT já limpa, com um item por bairro e vetores de 71 posições (um por nível). Não use o `data.json` original.

## Estrutura do código
- `app.py`: fornece os caminhos e chama **uma única função**, `clean_inct_data`, que roda as 7 etapas. Entrada: `dados/originais/data.json`. Saídas: `dados/processados/anomalies.csv`, `dados/processados/corrections.csv` e `dados/processados/inct_limpo.json`.
- `scripts/inct_cleaning.py`: biblioteca com uma função por etapa (carga, normalização, detecção, relatório, correção, revalidação e saída) e a função de entrada `clean_inct_data`.
- `scripts/inct_checks.py`: as verificações de anomalias e as funções compartilhadas que montam a tabela de anomalias.
- O arquivo original nunca é alterado.
- `scripts/*_old.py`: versão anterior, mantida só como referência. O código atual foi reescrito etapa por etapa a partir dela.

**Caminho do dado:** `data.json` → carga → normalização → detecção → `anomalies.csv` → correção → revalidação → `inct_limpo.json`.

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
Critério usado para dizer que um valor está errado: com o rio subindo, os prédios afetados de um bairro não podem diminuir, e um valor isolado muito diferente dos vizinhos não é uma tendência. A explicação de por que cada caso foi corrigido do jeito escolhido está na etapa 5.

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

## Etapa 5: Correção (`apply_corrections`)
**O que faz:** corrige `affected_buildings` com duas regras e recalcula os campos que dependem dele.

**Regra 1, zero no meio da série:** o zero marcado como `zero_after_affected` é trocado por uma reta entre os valores válidos mais próximos do mesmo bairro, arredondada.

**Regra 2, nenhum valor maior que os níveis seguintes:** se um valor é maior que algum nível posterior do mesmo bairro, ele é baixado para o menor valor dos níveis seguintes. **Isso assume que os valores posteriores é que estão certos.**

**Linhas alteradas:** `percentage` e `affected_population` são recalculados com a regra que o arquivo já usa (arredondamento para cima). As demais linhas não são tocadas.

**Não corrigido, só avisado:** `high_at_low_level`, `big_jump` e `repeated_value`. Só dá para confirmar com a altitude do terreno.

**Por que corrigimos assim:**

O critério é uma regra física: com o rio subindo, o número de prédios afetados de um bairro **não pode diminuir**. Um valor que viola isso está errado, e o que falta decidir é qual dos dois valores do par está errado e como substituí-lo.

| Caso | Por que é um problema | Por que corrigimos assim |
|---|---|---|
| Quedas (12 ocorrências, 5 bairros) | O número diminuiu com o nível subindo, o que é fisicamente impossível. | Baixamos o valor alto para o menor valor dos níveis seguintes. Assumimos que os valores posteriores estão certos. |
| Valor isolado (Espírito Santo, 4,7 m: `46 → 2101 → 47`) | É 44 vezes o vizinho e some no nível seguinte. Não é uma tendência, é provável erro de digitação. | A regra das quedas já resolve, porque o 2101 fica acima do nível seguinte e é baixado para 47. |
| Zeros no meio da série (4 ocorrências, 3 bairros) | O bairro já tinha prédios afetados e volta a zero com o rio mais alto. Parece dado ausente preenchido com 0. | Interpolação entre os vizinhos válidos, porque a série é suave nesses trechos e o zero não é plausível. |
| Espírito Santo, 3,0 a 3,4 m (`637 ... 633`, depois `25, 25, 27...`) | Os primeiros valores são muito maiores que os seguintes e quebram a regra física. | Apostamos que os 25 estão certos, porque a série de 25 em diante cresce de forma suave. Sem o terreno, não dá para confirmar. |
| Arquipélago (oscila 4674 a 4688, total 4688) | Quedas pequenas, de até 11 prédios. | A mesma regra das quedas ajusta o valor, e o percentual continua em 100%. |
| Percentual alto em nível baixo, saltos grandes, valores repetidos | Podem ser reais (área baixa que alaga de uma vez, bairro já quase todo alagado). | Mantidos e avisados. Só dá para confirmar com a altitude do terreno, e não queremos inventar dado. |

**Ordem das regras:** a interpolação dos zeros roda antes da regra das quedas. Se rodasse depois, um zero no meio da série puxaria para zero todos os valores anteriores do bairro.

**Por que corrigimos em vez de descartar:** o dashboard usa vetores de 71 posições por bairro, e a revalidação exige a grade 94 × 71 completa. Descartar uma linha deixaria um buraco no vetor.

**Resultado ao rodar:** 24 valores de `affected_buildings` corrigidos (4 pela regra 1 e 20 pela regra 2). Cada correção está em `dados/processados/corrections.csv`, com valor antes, valor depois e motivo (44 linhas, contando os campos recalculados).

| Bairro | Valores corrigidos | O que mudou |
|---|---|---|
| Arquipélago | 14 | baixou em até 11 prédios (de 4685 para 4674 ou 4680); o percentual continua em 100% |
| Espírito Santo | 6 | 3,0 a 3,4 m: 637 e 633 viraram 25; 4,7 m: 2101 virou 47 |
| Centro Histórico | 2 | 9,7 m: 0 virou 2077; 9,8 m: 0 virou 2103 |
| Lageado | 1 | 8,1 m: 0 virou 109 |
| Rubem Berta | 1 | 8,8 m: 0 virou 268 |

**Decisão mais frágil:** Espírito Santo de 3,0 a 3,4 m. Assumimos que os 25 estão certos e os 637 errados, porque a série de 25 em diante é suave. Não há como confirmar sem o terreno.

---

## Etapa 6: Revalidação (`revalidate`)
**O que faz:** roda todas as verificações de novo sobre os dados corrigidos e **para com erro** se a grade estiver incompleta ou se sobrar alguma anomalia de gravidade `error`.

**Resultado ao rodar:** passou. A grade é 94 × 71, sem vazios, e não sobrou nenhum erro. Ficaram 57 avisos e informações, mantidos de propósito.

**Conferência feita à parte:** `affected_buildings` não diminui em nenhum bairro (0 quedas), `total_buildings` e `population` não mudaram, e só 24 das 6.674 linhas diferem do arquivo original.

---

## Etapa 7: Saída (`save_outputs`)
**O que faz:** grava a base limpa em **JSON**, com um item por bairro e os valores que mudam com o nível em vetores, e devolve o caminho dele. Não é gerado CSV da base limpa.

**Arquivo de base para o dashboard: `dados/processados/inct_limpo.json`**

Formato:
```json
{
  "level_min": 3.0, "level_step": 0.1, "level_count": 71,
  "neighborhoods": {
    "Anchieta": {
      "total_buildings": 589, "population": 791,
      "affected_buildings": [28, 292, ...71 valores],
      "percentage": [5, 50, ...71 valores],
      "affected_population": [40, ...71 valores]
    }
  }
}
```
- 94 bairros, em ordem alfabética. Cada vetor tem 71 posições, do nível mais baixo (3,0 m) ao mais alto (10,0 m).
- `total_buildings` e `population` são números únicos, porque não mudam com o nível (a etapa 3 confere isso).
- Os valores são números inteiros, em UTF-8.

**Como o dashboard usa:** a posição de um nível em qualquer vetor é `round((nivel - 3.0) * 10)`, ou seja, `round((nivel - level_min) / level_step)`. O passo é 0,1, então não basta subtrair 3,0: o nível 3,5 tem posição 5, e não 0,5. O `round` é necessário porque a conta sem ele pode dar `1.0000000000000009` em vez de `1`. Se o slider trabalhar em décimos de metro (30 a 100), a posição é `valor - 30`, sem conta com decimais.

**Por que JSON:** guarda listas dentro de dicionários de forma natural, dá para ler a olho e o `json.load` do Python já devolve `bairro → campos`. O volume é pequeno (cerca de 20 mil números), então o formato não pesa no desempenho.

**Por que os vetores têm sempre 71 posições:** a etapa 6 só deixa passar se a grade for 94 × 71, sem vazios.

**Conferência feita à parte:** comparando o JSON com o arquivo original pela fórmula do índice, só diferem 24 valores de `affected_buildings`, 10 de `percentage` e 10 de `affected_population`. `total_buildings` e `population` não mudaram.

**Limitações que continuam valendo:**
- `percentage` e `affected_population` mantêm o arredondamento para cima do arquivo original, então a população afetada fica acima do cálculo exato (em média 27 pessoas por linha).
- Os avisos mantidos (`high_at_low_level`, `big_jump`, `repeated_value`) não foram validados contra o terreno.
