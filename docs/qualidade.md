# Qualidade dos dados

_Última execução: 2026-11-24T19:51:47Z (UTC). Gerado automaticamente; regras em `vigia/qualidade.py`._

**Status:** ⚠️ fonte fora do ar há pouco tempo (sem alarme; vira alarme se passar de 20 h)

- Checagens feitas: 441 · falharam: 6 (bloqueantes: 0)
- Fontes que não responderam: nenhuma
- Fora do ar há pouco tempo (bloqueio ou queda da fonte, sem alarme): transparencia, emendas, obras, diarias, receitas, licitacoes, folha (histórico em `data/qualidade/fontes_fora.csv`)
- Arquivos crus baixados hoje: 4 (hash SHA-256 em `data/qualidade/manifesto.csv`)

Quando uma checagem bloqueante falha, o arquivo novo **não** é gravado: fica a versão anterior.

## Checagens que falharam

| Arquivo | Regra | Bloqueante | Detalhe |
|---|---|---|---|
| fila_resumo_mensal.csv | links_da_fila | não | página da fila fora para o robô e nenhum link guardado |
| diarias | pseudonimo_sem_segredo | não | segredo VIGIA_SAL_PSEUDONIMO ausente: a coluna IdBeneficiario fica vazia (nome e CPF nunca são gravados) |
| receitas_2025.csv | erro_na_fonte | não | HTTP 403 <!DOCTYPE html> <!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]--> <!--[if IE 7]> <html class="n; arquivo anterior mantido |
| receitas_2026.csv | erro_na_fonte | não | HTTP 403 <!DOCTYPE html> <!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]--> <!--[if IE 7]> <html class="n; arquivo anterior mantido |
| licitacoes_2025.csv | erro_na_fonte | não | HTTP 403 <!DOCTYPE html> <!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]--> <!--[if IE 7]> <html class="n; arquivo anterior mantido |
| licitacoes_2026.csv | erro_na_fonte | não | HTTP 403 <!DOCTYPE html> <!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]--> <!--[if IE 7]> <html class="n; arquivo anterior mantido |

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
