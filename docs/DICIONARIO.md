# Dicionário de dados

O que é cada arquivo de `data/` e o que significa cada coluna. Todo arquivo é CSV em UTF-8, separado
por vírgula, com ponto decimal e datas como a fonte entrega. Valores em reais, sem correção pela
inflação (a correção fica em `data/refinado/`). Pessoa física nunca aparece com nome ou CPF.

Os arquivos marcados **bruto** são cópia fiel do que a fonte publicou (só limpeza de formato); os
marcados **derivado** são calculados pelo Vigia a partir dos brutos, e o código que os gera está
indicado. Quem quiser conferir um número derivado refaz a conta a partir do bruto.

## data/transparencia/ (portal da prefeitura, bruto)

Fonte: `https://wstransparencia.cariacica.es.gov.br/api/...` (API pública do portal). Coletores:
`vigia/coletores/transparencia.py` e `portal_extra.py`. Todo dia o ano corrente e o anterior são
baixados de novo; no dia 1 de cada mês, todos os anos.

### pagamentos_AAAA.csv — um registro por empenho (nota de empenho) do ano, todos os órgãos

| Coluna | Significado |
|---|---|
| Ano, Data | Exercício e data do empenho |
| IdEmpenho, NumeroEmpenho | Identificadores do empenho no portal (`NumeroEmpenho` = número/ano) |
| ValorEmpenhado | Valor reservado no orçamento para este credor |
| ValorLiquidado | Valor conferido (o serviço/produto foi entregue) |
| ValorPago | Valor pago, **acumulado** neste empenho, inclusive pagamentos feitos em anos seguintes |
| CpfCnpjFornecedor | CNPJ formatado; CPF mascarado (`***.212.345-**`); `99.999.999/9999-99` = folha |
| NomeFornecedor | Nome do credor como a prefeitura escreveu (o mesmo CNPJ pode ter grafias diferentes); vazio para pessoa física |
| CodOrgao, Orgao | Órgão orçamentário (secretaria, fundo, Câmara, IPC) |
| CodUnidadeGestora, UnidadeGestora | Unidade que executou (quase sempre igual ao órgão) |
| CodFuncao, Funcao | Área de governo (12 = Educação, 10 = Saúde, 15 = Urbanismo, 28 = Encargos especiais…) |
| CodSubFuncao, SubFuncao | Detalhe da área (361 = Ensino fundamental, 301 = Atenção básica…) |
| CodPrograma, Programa, CodAcao, Acao | Programa e ação do PPA/LOA a que o gasto pertence |
| CodFonte, Fonte | **De onde veio o dinheiro.** `1.500.0025.0000`: 1 = exercício corrente (2 = anteriores); 500 = fonte (padrão STN desde 2023; antes, plano do ES); o resto detalha. Tradução em `vigia/refino.py` |
| CodNaturezaDespesa, NaturezaDespesa | **Em que virou.** `33903900`: 3 = corrente, 3 = outras despesas correntes, 90 = aplicação direta, 39 = outros serviços PJ, 00 = subelemento |
| NumeroProcesso, NumeroContrato, Licitacao | Processo administrativo, contrato e licitação de origem (número/ano) |
| Descricao | Histórico do empenho (vazio para pessoa física) |

### contratos_AAAA.csv e emergenciais_AAAA.csv — um por contrato (emergenciais = sem licitação, por urgência)

| Coluna | Significado |
|---|---|
| NumeroContrato, AnoContrato, TipoContrato | Identificação e tipo (Serviço, Obra, Compra…) |
| Processo, AnoProcesso | Processo administrativo |
| ValorContratado | Valor original assinado |
| Aditivo | Soma dos termos aditivos (prorrogação, reajuste e acréscimo juntos; o portal não separa) |
| ValorTotal | ValorContratado + Aditivo |
| CPFCNPJ, Fornecedor | Contratado |
| Secretaria, Fiscal | Quem contratou e o servidor fiscal do contrato (cargo público: nome publicado pela prefeitura) |
| DataInicio, DataFinal, DataPublicacao, DataAssinatura | Vigência e publicação |
| Situacao, Coronavirus, Prioritario | Situação; se foi contrato da pandemia; se é prioritário |
| Objeto | O que foi contratado |
| UnidadeGestora | PREFEITURA, IPC ou INSTITUTO DE DESENVOLVIMENTO |

### penalizados.csv — fornecedores punidos pela própria prefeitura

Fornecedor, CPFCPNJ, TipoPenalidade, Descricao, InicioSuspensao, TerminoSuspensao, DataPenalidade,
Situacao, Valor, DataPublicacao, Exercicio.

### obras_AAAA.csv — uma por obra cadastrada (2010–2025; 2026 "sem dados" no portal)

Id, Nome, Contratos, NumeroContrato, Empresa, Secretaria, Tipo, ValorContratado, Estagio (andamento
declarado), Vigencia, **Bairros** (único campo do portal que localiza gasto na cidade), Situacao,
ValorPago, ValorEmpenhado, ValorLiquidado.

### emendas_AAAA.csv — emendas parlamentares recebidas (2025 e 2026 dão erro HTTP 500 no portal)

numero, partido, sigla, Parlamentar, data, destino (secretaria beneficiada), beneficiario, valor,
Situacao, descricao. Espelha o registro oficial da prefeitura; nenhum alerta cita parlamentar.

### diarias_AAAA.csv — diárias de viagem pagas a servidores, sem nome

Ano, Data, Processo, ValorEmpenhado, ValorLiquidacoes, ValorPago, **IdBeneficiario** (pseudônimo
HMAC do servidor: mostra repetição sem identificar; vazio se o segredo `VIGIA_SAL_PSEUDONIMO` não
existir), órgão, função, programa, fonte e natureza como em pagamentos.

### receitas_AAAA.csv e receita_acompanhamento.csv

`receitas`: Numero (código da receita), Nome, Exercicio, ValorPrevisto (LOA), ValorLancado,
ValorRealizado (acumulado no ano, sem mês), UnidadeGestora. `receita_acompanhamento` (derivado,
`portal_extra.py`): uma linha por dia de coleta e código, com `fracao_do_ano`, `esperado_pro_rata`
e `diferenca`: termômetro da arrecadação, não o cálculo legal do excesso.

## data/siconfi/ (Tesouro Nacional, bruto)

Fonte: `apidatalake.tesouro.gov.br` (Siconfi). Coletor: `vigia/coletores/siconfi.py`. Sete cidades
da Grande Vitória, 2017 em diante. Colunas comuns: exercicio, instituicao, cod_ibge, uf, anexo,
rotulo, coluna (ex.: "Despesas Liquidadas"), cod_conta, conta, valor, populacao (a que o Tesouro
usa, origem IBGE).

| Arquivo | O que é |
|---|---|
| entes.csv | Cadastro das 7 cidades: cod_ibge, nome, população do ano corrente, CNPJ |
| dca_receitas.csv | Contas anuais (DCA), receitas por código (ICMS, FPM, IPTU…), brutas e deduções |
| dca_despesa_funcao.csv | DCA, despesa por função de governo (empenhada, liquidada, paga, restos a pagar) |
| dca_despesa_natureza.csv | DCA, despesa por natureza (pessoal, custeio, investimento, elemento) |
| rreo_balanco_orcamentario.csv | Execução bimestral (RREO): previsão x realizado, por bimestre |
| rreo_despesa_funcao.csv | RREO, despesa por função por bimestre |
| rgf_pessoal.csv | Relatório de gestão fiscal: gasto com pessoal x limite da LRF |

## data/tcees/ (Tribunal de Contas do ES, bruto)

Fonte: dados.es.gov.br, conjuntos `receitas-municipios` e `despesas-municipios` (sistema CidadES).
Coletor: `vigia/coletores/tcees.py`. Só Cariacica, 2019 em diante, **valores do mês** (somar os
meses dá o ano).

- `receitas_AAAA.csv`: Ano, Mes, unidade gestora, ClassificacaoReceita e nomes dos níveis,
  CodigoFonteReduzida/NomeFonteReduzida, PrevisaoInicial (inteira no mês 1), PrevisaoAtualizada,
  Arrecadada.
- `despesas_AAAA.csv`: Ano, Mes, órgão, função, fonte reduzida, PrevisaoInicial, PrevisaoAtualizada
  (dotação atual: a diferença para a inicial são os créditos adicionais), Empenhada, Liquidada, Paga.

## data/tesouro/ (Tesouro Nacional, transferências mensais, bruto)

Coletor: `vigia/coletores/tesouro.py`. Fonte: [Tesouro Transparente](https://www.tesourotransparente.gov.br/ckan/dataset/af4e7c47-2132-4d9a-bd7c-34e28a210b03), um CSV nacional por mês; o Vigia guarda Cariacica, Vitória, Vila Velha, Serra e Viana, de 2021 em diante.

- `transferencias.csv`: `municipio`, `ano`, `mes` (01–12, lido do conteúdo do arquivo), `transferencia` (ex.: FPM, FUNDEB), `item` (ex.: COUN VAAT, COUN VAAR = complementação da União ao Fundeb), `valor` (soma dos três decêndios do mês, R$).
- `recursos.csv`: cada arquivo do catálogo já baixado, com data de modificação e SHA-256 (só baixa de novo o que mudou).

## data/pncp/ (Portal Nacional de Contratações Públicas, derivado do banco)

Fonte: `pncp.gov.br/api`. Coletor: `vigia/coletores/pncp.py`; o banco SQLite (release "banco")
guarda tudo, inclusive cidades vizinhas; os CSVs são a parte de Cariacica (`vigia/exportar.py`).

| Arquivo | Uma linha por | Colunas principais |
|---|---|---|
| orgaos.csv | órgão municipal encontrado no PNCP | cnpj, razao_social, esfera, poder |
| contratacoes.csv | licitação, dispensa ou inexigibilidade | id_pncp, modalidade, situacao, objeto, amparo_legal, valor_estimado, valor_homologado, datas, srp (registro de preços), link_origem |
| itens.csv | item de uma contratação | id_pncp, numero_item, descricao, material_servico, quantidade, unidade, valor_unit_estimado, situacao |
| resultados.csv | vencedor de um item | id_pncp, numero_item, ni_fornecedor (CNPJ/CPF), nome_fornecedor, porte, quantidade, valor_unit, valor_total, percentual_desconto |
| contratos.csv | contrato publicado | id_pncp, id_pncp_compra, numero, tipo_contrato, objeto, ni_fornecedor, valor_inicial, valor_global, vigencia, data_publicacao |
| termos.csv | termo aditivo | id_contrato, numero, tipo, valor_acrescido, valor_global, prazo_aditado_dias, qualifica_* (o que o termo mudou) |
| atas.csv | ata de registro de preços (inclusive de outros órgãos usadas por "carona") | id_ata, nome_orgao, numero, objeto, vigência, cancelada |

## data/receita/empresas.csv (Receita Federal via BrasilAPI, bruto)

Uma por CNPJ dos maiores fornecedores: cnpj, razao_social, nome_fantasia, data_abertura, situacao,
data_situacao, capital_social, porte, natureza_juridica (texto), cnae, cnae_descricao, opcao_mei,
opcao_simples, municipio, uf, fonte, consultado_em. Sócios ficam só no banco (LGPD).

## data/tse/fornecedores_campanha.csv (TSE, derivado)

> Este arquivo está (fora do repositório público enquanto a R25 está em revisão jurídica; ver docs/DECISOES.md).

Empresas contratadas pelas campanhas municipais de Cariacica (2020 e 2024), **sem candidato nem
partido**: cnpj, fornecedor, ano_eleicao, cargos atendidos, candidaturas, valor_campanha, cnae,
tipo_despesa. Entrada da regra R25. Gerado por `vigia/coletores/tse.py`.

## data/transferegov/ (emendas Pix, bruto)

Planos de ação, executores, metas e relatórios de gestão das transferências especiais para
Cariacica, sem colunas bancárias. Coletor semanal `vigia/coletores/transferegov.py`.

## data/ibge/ipca.csv (IBGE/SIDRA, bruto)

ano, mes, indice (IPCA número-índice, base dez/1993 = 100), referencia. Coletor
`vigia/coletores/ibge.py`. Usado pelo refino para trazer valores a preços constantes.

## data/transparencia/licitacoes_AAAA.csv (portal da prefeitura, bruto)

Uma linha por item de licitação, dispensa, inexigibilidade ou adesão a ata, desde 2019 (`vigia/coletores/licitacoes.py`):
Numero, Processo, Modalidade, Situacao (homologação, deserta, fracassada, revogada...), datas, Comissao,
Secretaria, Objeto, Item, Unidade, Quantidade, ValorReferencia (do item), ValorTotal (quantidade x referência) e
ValorTotalHomologado (**do processo inteiro**, repetido em cada item).

## data/folha/ (portal da prefeitura, só agregado, `vigia/coletores/folha.py`)

- `folha_mensal.csv`: ano, mes, valor (total da consulta de pessoal do mês; não inclui encargos).
- `cargos_AAAA.csv`: ano, mes, cd_cargo, cargo, servidores, vencimento_padrao, outros_vencimentos,
  remuneracao_bruta, descontos, remuneracao_liquida (somas da prefeitura por cargo).
- `lotacoes_AAAA.csv`: o mesmo por lotação, com cd_secretaria, secretaria e nivel.
- `vinculos.csv`: ano, mes, vinculo (Estatutário, Contrato Temporário, Comissionado, CLT...), servidores
  (matrículas distintas), tempo_* (matrículas por tempo desde a admissão até o fim do mês), valor_v
  (vencimentos e vantagens) e valor_d (descontos). Somado na memória a partir da folha nominal; nenhum nome,
  CPF ou matrícula é gravado.

## data/divida/pedidos_emprestimo.csv (SADIPEM/Tesouro, bruto, `vigia/coletores/divida.py`)

Cada pedido de empréstimo (PVL) de Cariacica: id_pleito, num_pvl, status, data_protocolo, tipo_operacao,
finalidade, credor, moeda, valor, pvl_contradado_credor (1 = contratado). Os Anexos 2, 4 e 5 do RGF das cidades
da Grande Vitória ficam em `data/siconfi/rgf_divida.csv`, `rgf_operacoes_credito.csv` e `rgf_caixa.csv`, no
formato dos outros arquivos do Siconfi.

## data/estado/ (Governo do ES, dados.es.gov.br, filtrado, `vigia/coletores/estado.py`)

- `transferencias_AAAA.csv`: ICMS, IPVA, IPI, Fundo de Redução das Desigualdades, CIDE e compensação financeira
  repassados a Cariacica, mês a mês.
- `convenios_AAAA.csv`: convênios do Estado com a prefeitura ou com entidade de Cariacica (`com_a_prefeitura`),
  sem colunas de banco nem nome de responsável.
- `convenios_pagamentos_AAAA.csv`: pagamentos desses convênios (só favorecido com CNPJ).
- `convenios_aditivos_AAAA.csv` e `recursos.csv` (data de modificação de cada arquivo do Estado já baixado).

## data/previdencia/isp.csv e data/cauc/cauc.csv (`vigia/coletores/externos.py`)

- `isp.csv`: ano_isp, cod_ibge, ente, planilha, indicador, valor. Indicador de Situação Previdenciária do
  Ministério da Previdência, cidades da Grande Vitória.
- `cauc.csv`: data_pesquisa, cod_ibge, ente, item (código da exigência), situacao (data até quando está
  comprovada, "!" ou "Desabilitado") e pendente (sim quando "!"). Uma fotografia por dia.

## data/fila/ (Secretaria Municipal de Saúde, somado, `vigia/coletores/fila.py`)

Fila de espera de consultas e exames especializados, a partir da planilha mensal da Saúde. **Só somas:** a
planilha oficial traz nome e data de nascimento dos pacientes, e nada disso é gravado (nem o arquivo).
- fila_resumo_mensal.csv: por mês: pedidos, pessoas diferentes (um pedido não é uma pessoa), procedimentos na
  lista, mediana de dias de espera (do pedido ao último dia do mês), mais de 180 dias, de 1 ano e de 2 anos,
  crianças até 12 anos e idosos 60+ (idade calculada pela data de nascimento no último dia do mês; a coluna de
  idade da planilha não confere e fica só como medida de qualidade em idade_planilha_confere_pct), sem_idade, e os
  mesmos números para prioridade "MUITO ALTA", neurologia pediátrica (com pessoas e até 5 anos) e neurologia adulto.
  Para crescimento, use o comparável da seção do relatório (só procedimentos presentes em todos os meses).
- fila_especialidade_AAAA-MM.csv e fila_unidade_AAAA-MM.csv: pedidos, mediana e mais de 1 ano por procedimento
  e por unidade que pediu.
- arquivos.csv: url, hash SHA-256 e mês de cada planilha lida (prova de qual arquivo gerou cada número).

## data/resultados.csv (preenchido à mão ou pela rotina das respostas)

Placar de resultados (`docs/DECISOES.md`): data, campanha, tipo, o_que_mudou, fonte (link oficial) e
pedido (protocolo). Só entra o que mudou de verdade e tem fonte.

## data/refinado/ (derivado, `vigia/refino.py`)

Todas as tabelas somam `ValorPago`, `ValorLiquidado` e `ValorEmpenhado` de `pagamentos_AAAA.csv`
(todos os órgãos). Colunas comuns às tabelas por ano: ano, empenhado, liquidado, pago, registros
(quantos empenhos), pct_do_ano (pago ÷ total pago do ano).

| Arquivo | Uma linha por | Colunas específicas |
|---|---|---|
| resumo_ano.csv | ano | fornecedores (credores distintos), populacao, pago_por_morador; com IPCA: ano_base_precos, pago_real, pago_real_por_morador |
| origem_ano.csv | origem × ano | origem (chave) e origem_nome: de onde veio o dinheiro, 14 categorias (tabela `ORIGENS` em `refino.py`) |
| origem_detalhe_ano.csv | código de fonte × ano | CodFonte, Fonte (nome da prefeitura), origem atribuída, exercicio_anterior, origem_pelo_nome, aviso (quando o nome sugere outra categoria) |
| tipo_ano.csv | tipo × ano | tipo: Pessoal e encargos / Custeio / Investimentos / Juros / Amortização / Inversões (grupo da natureza) |
| modalidade_ano.csv | modalidade × ano | quem executa: aplicação direta, entidade sem fins lucrativos, consórcio público, intraorçamentária, outro ente |
| orgao_ano.csv | órgão × ano | CodOrgao, Orgao |
| funcao_ano.csv | função × ano | CodFuncao, funcao (nome único por código, mesmo quando o portal escreve SAUDE/SAÚDE) |
| elemento_ano.csv | elemento × ano | elemento (6 dígitos), elemento_nome, tipo |
| recebedor_ano.csv | tipo de recebedor × ano | recebedor: Empresa / Servidores ativos e aposentados / Órgão público, consórcio público ou previdência / Entidade sem fins lucrativos / Dívida / Consórcio de empresas / Concessionária / Pessoa física |
| fornecedores.csv | raiz de CNPJ (8 dígitos: matriz e filiais juntas) | cnpj (mais frequente), nome (mais frequente), tipo, total_pago, empenhos, primeiro_ano, ultimo_ano, anos_com_pagamento, orgaos, orgao_principal, funcao_principal, elemento_principal, contratos, pago_AAAA (uma coluna por ano) e, quando a Receita foi consultada, cnae, cnae_descricao, natureza_juridica, porte, capital_social, data_abertura, situacao |
| deflator.csv | ano | meses (com índice no ano), indice_medio, ano_base, fator_para_ano_base |

Como o tipo de recebedor é decidido: a natureza manda antes do nome (grupo 31 = servidores, mesmo
quando o credor registrado é o INSS, o IPC ou a própria prefeitura; grupos 32 e 46 = dívida);
depois o documento (CPF = pessoa física); depois o nome e a natureza jurídica da Receita (órgão
público, entidade sem fins lucrativos, concessionária, consórcio de empresas); o resto é empresa.

## data/alertas.csv e data/casos.csv (derivado, `vigia/alertas/`)

`alertas.csv`: id (estável), regra, nome_regra, gravidade, titulo, pergunta, detalhe, valor,
valor_excesso, orgao, fornecedor, fornecedor_doc, referencia, data_referencia, link (fonte oficial),
outros_links, primeira_vez, status, nota. As 26 regras estão em `docs/REGRAS.md`.
`casos.csv`: marcação humana de cada alerta (status, nota, quem, quando).

## data/qualidade/ (derivado, `vigia/qualidade.py`)

- checagens.csv: cada checagem da última coleta (fonte, arquivo, regra, ok, bloqueante, detalhe).
- manifesto.csv: SHA-256 de cada arquivo cru baixado (arquivo_bruto, fonte, baixado_em, bytes).
- alteracoes.csv: dado antigo que mudou depois de publicado, com a origem da mudança.
- banco.csv: retrato das tabelas do banco a cada coleta.

## data/raiox/ (IBGE e INEP, derivado, `ferramentas/raiox/`)

- bairros-cariacica.csv e bairros-indicadores.csv: por bairro (Censo 2022): população, domicílios,
  renda média e mediana, % esgoto em rede, % esgoto precário, % sem banheiro, % água em rede, % lixo
  coletado, % alfabetizados 15+. Desde 24/11/2026, bairros-cariacica.csv traz também as contagens exatas
  domicilios_sem_rede (domicílios permanentes menos os ligados à rede, V00309 + V00310) e pessoas_15mais.
- cariacica-municipio.csv: Cariacica inteira (agregado por município do Censo 2022, com a zona rural), as mesmas
  variáveis. É a coluna "Cariacica" do site (`ferramentas/raiox/processar_municipio.py`).
- ideb-escolas-cariacica.csv: por escola: rede, etapa, Ideb 2023 e 2025, aprovação, notas.
- ideb-cidades.csv, ideb-municipios.csv, indicadores-grande-vitoria.csv: comparação com as vizinhas
  (pobreza no CadÚnico, Ideb, etc.), com fonte e data em cada linha.

## data/sonda/ (amostras da sonda de fontes)

Primeiros 200 KB da resposta de cada fonte candidata, com CPFs mascarados, e `RESULTADO.md` com o
que cada uma respondeu. Não são dados publicados pelo Vigia: servem para escrever os coletores.
Gerado por `ferramentas/sonda/sondar.py` no workflow "Sonda de fontes".
