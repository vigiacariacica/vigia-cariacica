# Qualidade dos dados

_Última execução: 2026-11-24T16:41:05Z (UTC). Gerado automaticamente; regras em `vigia/qualidade.py`._

**Status:** ❌ há problemas (ver abaixo)

- Checagens feitas: 876 · falharam: 12 (bloqueantes: 0)
- Fontes que não responderam: externos
- Fora do ar há pouco tempo (bloqueio ou queda da fonte, sem alarme): tesouro (histórico em `data/qualidade/fontes_fora.csv`)
- Arquivos crus baixados hoje: 122 (hash SHA-256 em `data/qualidade/manifesto.csv`)

Quando uma checagem bloqueante falha, o arquivo novo **não** é gravado: fica a versão anterior.

## Checagens que falharam

| Arquivo | Regra | Bloqueante | Detalhe |
|---|---|---|---|
| emendas/anos | ano_fora_da_lista | não | a lista de anos da prefeitura não traz 2025, 2026; consultado(s) mesmo assim |
| emendas_2025.csv | erro_na_fonte | não | emendas/csv?exercicio=2025 respondeu HTTP 500 { "Message": "An error has occurred." }; a prefeitura precisa corrigir; nada gravado |
| emendas_2026.csv | erro_na_fonte | não | emendas/csv?exercicio=2026 respondeu HTTP 500 { "Message": "An error has occurred." }; a prefeitura precisa corrigir; nada gravado |
| emendas_2027.csv | ano_no_futuro | não | a prefeitura lista emendas no exercício 2027 (provavelmente data de validade digitada como ano) |
| emendas_2031.csv | ano_no_futuro | não | a prefeitura lista emendas no exercício 2031 (provavelmente data de validade digitada como ano) |
| obras_2026.csv | sem_dados | não | a prefeitura respondeu 'sem dados' para as obras de 2026; nada gravado |
| diarias | pseudonimo_sem_segredo | não | segredo VIGIA_SAL_PSEUDONIMO ausente: a coluna IdBeneficiario fica vazia (nome e CPF nunca são gravados) |
| vinculos.csv | folha_nominal_adiada | não | 2026/8: HTTPError: 524 Server Error: <none> for url: https://wstransparencia.cariacica.es.gov.br/ap; tenta de novo amanhã |
| vinculos.csv | folha_nominal_adiada | não | 2026/7: HTTPError: 524 Server Error: <none> for url: https://wstransparencia.cariacica.es.gov.br/ap; tenta de novo amanhã |
| vinculos.csv | folha_nominal_adiada | não | 2026/4: HTTPError: 524 Server Error: <none> for url: https://wstransparencia.cariacica.es.gov.br/ap; tenta de novo amanhã |
| vinculos.csv | folha_nominal_x_cargos | não | 2026/10: 8849 matrículas na folha nominal x 9063 na consulta por cargo (-2.4%) |
| fila_resumo_mensal.csv | links_da_fila | não | página da fila fora para o robô e nenhum link guardado |

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

## Dados antigos que mudaram depois de publicados

Anos já encerrados são baixados de novo uma vez por mês. A coluna Origem compara o arquivo cru de agora com o anterior: se a prefeitura não mudou o arquivo, a mudança foi do nosso leitor. O histórico do git guarda as duas versões.

| Detectado em | Arquivo | Linhas | Total (R$) | Origem |
|---|---|---|---|---|
| 2026-11-07 | pagamentos_2023.csv | 24625→24623 | 1.336.095.503,11→1.336.095.503,11 | nosso leitor (correção de 07/11/2026: 2 registros vazios removidos; total igual) |
