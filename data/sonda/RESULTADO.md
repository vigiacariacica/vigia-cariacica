# Sonda de fontes

Rodada em 2026-11-10 23:59 (UTC) no GitHub Actions. Amostras (até 200 KB) ao lado; esta tabela diz o que cada fonte respondeu. Fontes com nome de pessoa guardam só a estrutura ou o cabeçalho.

| Fonte | Para que serve | HTTP | Tipo | Bytes | s | O que veio |
|---|---|---|---|---|---|---|
| [tesouro_show_pvl_oc_cp](https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=pvl-oc-cp) | Cronogramas de pagamento das operações de crédito contratadas (URLs dos arquivos) | 200 | application/json | 4267 | 2.4 | chaves: help, success, result |
| [tesouro_show_pvl_oc_cl](https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=pvl-oc-cl) | Cronogramas de liberação (desembolso) das operações contratadas | 200 | application/json | 4219 | 2.4 | chaves: help, success, result |
| [tesouro_show_pvl_resumo_oc](https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=pvl-resumo-oc) | Resumo dos cronogramas de pagamento (contratadas e a contratar) | 200 | application/json | 4275 | 2.4 | chaves: help, success, result |
| [tesouro_show_cauc](https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=cauc) | CAUC: arquivos (URLs e datas) | 200 | application/json | 6354 | 2.4 | chaves: help, success, result |
| [tesouro_cauc_municipios](https://www.tesourotransparente.gov.br/ckan/dataset/72b5f371-0c35-4613-8076-c99c821a6410/resource/07af297a-5e59-494a-a88a-55ddfd2f4b01/download/relatorio-situacao-de-varios-entes---municipios---uf-todas---abrangencia-1.csv) | CAUC de todos os municípios (começo do arquivo e tamanho) | 200 | text/csv | 200590 | 3.6 | 592 linhas na amostra; cabeçalho: "Data da Pesquisa: 10/11/2026" |
| [isp_2025_planilha](https://www.gov.br/previdencia/pt-br/assuntos/rpps/indice-de-situacao-previdenciaria/arquivos/resultado-final-isp-2025-_-publicado-em-04_12_2025-1.xlsx) | ISP 2025: planilha com o resultado de cada regime (arquivo inteiro) | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 3550002 | 5.8 | binário xlsx, 3550002 bytes guardados |
| [portal_pessoal_mensal_2025](https://wstransparencia.cariacica.es.gov.br/api/pessoal/mensal?exercicio=2025) | Folha: total por mês de 2025 | 200 | application/json | 630 | 1.4 | lista de 12+ itens; campos: mes, valor |
| [portal_pessoal_cargo_2025_12](https://wstransparencia.cariacica.es.gov.br/api/pessoal/cargo?exercicio=2025&mes=12) | Folha por cargo, dez/2025 (agregado, sem nome) | 200 | application/json | 167097 | 2.1 | lista de 579+ itens; campos: CargoNome, cd_CargoServidor, NumeroServidores, VencimentoPadrao, OutrosVencimentos, RemuneracaoBruta, Descontos, RemuneracaoLiquida |
