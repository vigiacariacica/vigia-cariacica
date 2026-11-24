# Qualidade dos dados

_Última execução: 2026-11-15T07:21:58Z (UTC). Gerado automaticamente; regras em `vigia/qualidade.py`._

**Status:** ❌ há problemas (ver abaixo)

- Checagens feitas: 471 · falharam: 3 (bloqueantes: 0)
- Fontes que não responderam: pncp (compras externas: 3 sem resposta)
- Fora do ar há pouco tempo (bloqueio ou queda da fonte, sem alarme): pncp, vizinhos (histórico em `data/qualidade/fontes_fora.csv`)
- Arquivos crus baixados hoje: 4 (hash SHA-256 em `data/qualidade/manifesto.csv`)

Quando uma checagem bloqueante falha, o arquivo novo **não** é gravado: fica a versão anterior.

## Checagens que falharam

| Arquivo | Regra | Bloqueante | Detalhe |
|---|---|---|---|
| https://pncp.gov.br/api/pncp/v1/orgaos/00489828000155/compras/2024/59 | resposta_http | não | HTTP 0 |
| https://pncp.gov.br/api/pncp/v1/orgaos/00536717000152/compras/2025/22 | resposta_http | não | HTTP 0 |
| https://pncp.gov.br/api/pncp/v1/orgaos/02618132000107/compras/2025/24 | resposta_http | não | HTTP 0 |

## Conciliação: portal da prefeitura x Tesouro (Siconfi)

Total empenhado no ano, em R$ milhões. As duas fontes são da própria prefeitura; diferença acima de 2% indica dado faltando ou erro de leitura.

| Ano | Portal | Siconfi | Diferença | |
|---|---|---|---|---|
| 2019 | 702,0 | 708,9 | -0,97% | ✅ |
| 2020 | 778,2 | 785,6 | -0,94% | ✅ |
| 2021 | 892,4 | 903,5 | -1,22% | ✅ |
| 2022 | 1.177,0 | 1.186,2 | -0,78% | ✅ |
| 2023 | 1.336,1 | 1.349,7 | -1,01% | ✅ |
| 2024 | 1.646,0 | 1.654,3 | -0,50% | ✅ |
| 2025 | 1.695,8 | 1.713,8 | -1,05% | ✅ |

A diferença de cerca de 1% se repete em todos os anos (classificação por área difere entre as duas bases). Uma mudança brusca nesse padrão é o sinal de alerta.

## Exclusões aplicadas pelas regras

Casos que uma regra deixou de fora de propósito, listados para que a exclusão possa ser conferida.

| Regra | Detalhe |
|---|---|
| R25 | BANCO DO BRASIL SA (00.000.000/1143-67): R$ 1.095.651,75 pagos depois da eleição; fora porque o vínculo com a campanha é obrigação legal ou monopólio (banco, concessionária, Correios) ou órgão público |
| R25 | EDP ESPIRITO SANTO DISTRIBUICAO DE ENERGIA S.A. (28.152.650/0001-71): R$ 34.583.298,42 pagos depois da eleição; fora porque o vínculo com a campanha é obrigação legal ou monopólio (banco, concessionária, Correios) ou órgão público |

## Dados antigos que mudaram depois de publicados

Anos já encerrados são baixados de novo uma vez por mês. A coluna Origem compara o arquivo cru de agora com o anterior: se a prefeitura não mudou o arquivo, a mudança foi do nosso leitor. O histórico do git guarda as duas versões.

| Detectado em | Arquivo | Linhas | Total (R$) | Origem |
|---|---|---|---|---|
| 2026-11-07 | pagamentos_2023.csv | 24625→24623 | 1.336.095.503,11→1.336.095.503,11 | nosso leitor (correção de 07/11/2026: 2 registros vazios removidos; total igual) |
