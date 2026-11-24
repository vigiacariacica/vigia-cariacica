# Metodologia: de onde vem cada número e como conferir

Este documento explica, fonte por fonte, **como o Vigia Cariacica obtém os dados**, o que faz com
eles e **como qualquer pessoa pode conferir à mão**. Se um número publicado pelo Vigia não puder ser
refeito por este caminho, é um erro nosso e queremos saber (abra uma *issue* no GitHub).

Tudo é dado público, obtido de fontes oficiais, sem login, sem senha e sem burlar nenhum bloqueio.
Base legal: Lei de Acesso à Informação (Lei 12.527/2011), Lei Complementar 131/2009 (transparência
em tempo real) e Lei 14.133/2021, art. 174 (Portal Nacional de Contratações Públicas).

## Sumário

1. [Portal da Transparência da Prefeitura](#1-portal-da-transparência-da-prefeitura-de-cariacica)
2. [Tesouro Nacional (Siconfi)](#2-tesouro-nacional-siconfi)
3. [PNCP: compras, itens, preços e contratos](#3-pncp-portal-nacional-de-contratações-públicas)
4. [Receita Federal (dados das empresas)](#4-receita-federal-dados-das-empresas)
5. [CGU: empresas punidas (CEIS/CNEP)](#5-cgu-empresas-punidas-ceis-e-cnep)
6. [TCE-ES: receita e despesa mês a mês](#6-tce-es-receita-e-despesa-mês-a-mês)
7. [TSE: fornecedores das campanhas municipais](#7-tse-fornecedores-das-campanhas-municipais)
8. [Transferegov: emendas Pix](#8-transferegov-emendas-pix)
9. [Das fontes aos alertas](#9-das-fontes-aos-alertas)
10. [Checagens de qualidade](#10-checagens-de-qualidade)
11. [Onde cada dado fica guardado](#11-onde-cada-dado-fica-guardado)
12. [Dados pessoais (LGPD)](#12-dados-pessoais-lgpd)
13. [Como reproduzir tudo no seu computador](#13-como-reproduzir-tudo-no-seu-computador)
14. [Limitações conhecidas](#14-limitações-conhecidas)
15. [IBGE: inflação (IPCA)](#15-ibge-inflação-ipca)
16. [Camada refinada: o mapa do dinheiro](#16-camada-refinada-o-mapa-do-dinheiro)
17. [Sonda de fontes](#17-sonda-de-fontes)

---

## 1. Portal da Transparência da Prefeitura de Cariacica

**O que é:** a base oficial da prefeitura com cada empenho e pagamento, cada contrato e seus
aditivos, os contratos emergenciais e as empresas punidas. É a fonte mais detalhada que existe.

**Endereço da API:** `https://wstransparencia.cariacica.es.gov.br/api` (documentação oficial em
`https://wstransparencia.cariacica.es.gov.br/Help`). É a mesma base do site
`https://transparencia.cariacica.es.gov.br`.

**Código:** `vigia/coletores/transparencia.py`. **Saída:** `data/transparencia/`.

| O que | Chamada | Arquivo gerado |
|---|---|---|
| Pagamentos (cada empenho, com valor empenhado, liquidado e pago, CNPJ/CPF, área, programa, processo, contrato e descrição) | `GET /despesas/csv?exercicio=AAAA&tipoDespesa=P` | `pagamentos_AAAA.csv` |
| Contratos (valor contratado, aditivo, valor total, vigência, objeto) | `GET /contratos/csv?unidadeGestoraId=U&exercicio=AAAA` | `contratos_AAAA.csv` |
| Contratos emergenciais | `GET /contratos-emergenciais/csv?unidadeGestoraId=U&exercicio=AAAA` | `emergenciais_AAAA.csv` |
| Fornecedores punidos pela prefeitura | `GET /fornecedoresPenalizados/anos` e `GET /fornecedoresPenalizados/csv?Exercicio=AAAA` | `penalizados.csv` |
| Total pago a um fornecedor no ano (usado como link de conferência) | `GET /despesa/fornecedor?exercicio=AAAA&nomeCPFCNPJ=<CNPJ>` | — |
| Emendas parlamentares | `GET /emendas/anos` e `GET /emendas/csv?exercicio=AAAA` | `emendas_AAAA.csv` |
| Obras | `GET /obras/anos` e `GET /obras/csv?exercicio=AAAA` | `obras_AAAA.csv` |
| Diárias pagas a servidores (sem nome nem CPF) | `GET /diarias/anos` e `GET /diarias/csv?unidadeGestoraId=U&exercicio=AAAA` | `diarias_AAAA.csv` |
| Receitas: previsto, lançado e realizado | `GET /receitas/csv?unidadeGestoraId=U&exercicio=AAAA` | `receitas_AAAA.csv`, `receita_acompanhamento.csv` |

Unidades gestoras consultadas (`GET /UnidadesGestoras`): 6 = Prefeitura, 3 = IPC (previdência),
26 = Instituto de Desenvolvimento.

**Quando:** todo dia, os dois anos mais recentes. No dia 1 de cada mês, todos os anos desde 2019
(para detectar dado antigo alterado).

**Tratamento, passo a passo:**
1. O arquivo é baixado e seu SHA-256 é anotado em `data/qualidade/manifesto.csv` (quem baixar o
   mesmo arquivo no mesmo momento obtém o mesmo hash).
2. Os CSVs da prefeitura vêm em **windows-1252** e são **malformados**: descrições têm aspas soltas e
   quebras de linha. Um leitor comum junta milhares de linhas numa só. Por isso cada registro é
   separado pelo começo `AAAA,` seguido de 6 campos numéricos, as colunas fixas são lidas da
   esquerda e a descrição é o que sobra antes do último campo (`ler_csv_malformado`).
3. Valores em formato brasileiro (`1.234,56`) viram `1234.56`. Espaços repetidos são removidos.
   Nenhum valor é arredondado, somado ou alterado.
4. **Proteção de dados pessoais:** em pagamento a pessoa física, o nome e a descrição são
   substituídos por "PESSOA FÍSICA" e "(omitida: pagamento a pessoa física)" (há pensões alimentícias,
   família acolhedora, restituições). Valor, data, área, programa e natureza ficam. Em todo o resto,
   qualquer CPF que apareça num texto é mascarado.
5. O arquivo só é gravado se passar nas checagens da seção 10.

**Como conferir à mão:** abra no navegador, por exemplo,
`https://wstransparencia.cariacica.es.gov.br/api/despesa/fornecedor?exercicio=2025&nomeCPFCNPJ=27.320.787/0001-25`
e compare o total com a soma da coluna `ValorPago` das linhas desse CNPJ em `data/transparencia/pagamentos_2025.csv`.

**Cuidados de leitura:**
- O "pago" de cada linha é o pago acumulado daquele empenho, inclusive em anos seguintes.
- CPF de pessoa física vem mascarado pela própria prefeitura no campo do fornecedor
  (`****47.207**`), mas aparece inteiro em nomes de MEI e em descrições; o Vigia mascara.
- "Aditivo" no contrato soma prorrogação de prazo (legal em serviço contínuo) e acréscimo de objeto
  (limitado a 25%). O portal não separa os dois.
- A folha de pagamento aparece como um "fornecedor" com CNPJ `99.999.999/9999-99`; folha,
  previdência, tributos e órgãos públicos ficam fora dos rankings de fornecedores.

### Emendas, obras, diárias e receitas

**Código:** `vigia/coletores/portal_extra.py`, com as mesmas peças do coletor acima (arquivo cru com
SHA-256, leitura em windows-1252, checagem antes de gravar). Roda todo dia; cada uma é uma fonte separada
no comando, então a falha de uma não impede as outras.

**Emendas parlamentares** (`emendas_AAAA.csv`): emendas de deputados e senadores destinadas à prefeitura,
com número, autor, partido, data, destino, secretaria beneficiada, valor, situação e descrição. O valor
vem como `R$ 486.104,00` e vira `486104.00`. A descrição é texto livre e às vezes tem quebra de linha fora
de aspas, o que faz um leitor de CSV comum inventar registros; o leitor do Vigia separa os registros pelo
formato do começo da linha (sete campos e um valor em reais) e confere a contagem pelos valores em reais
do arquivo. Anos consultados: todos os da lista `emendas/anos` e, sempre, o ano corrente e o anterior.

Defeitos da fonte encontrados em 07/11/2026 (registrados como aviso em `docs/qualidade.md` a cada coleta):
- a lista de anos traz 2031 e 2027, que parecem datas de validade digitadas como ano (as emendas de 2027
  têm data 31/12/2027), e não traz 2025 nem 2026;
- `emendas/csv?exercicio=2025` e `exercicio=2026` respondem `HTTP 500 {"Message":"An error has occurred."}`,
  um erro no servidor da prefeitura. Até ser corrigido, as emendas desses anos não podem ser vistas pelo
  portal. O arquivo de um ano com erro nunca é apagado;
- numa emenda de 2027, o campo `numero` traz o nome do parlamentar. O Vigia grava como veio.

**Obras** (`obras_AAAA.csv`): nome, contrato, secretaria, tipo, estágio, vigência, bairros, situação e os
valores contratado, empenhado, liquidado e pago. `Contratos` vem como `083/2023 - EXATA CONSTRUTORA LTDA`;
quando o campo tem um contrato só, o Vigia acrescenta `NumeroContrato` e `Empresa` (o original fica). Ano
sem obra responde só `Nome / sem dados` (2026, em 07/11/2026; 2025 tinha uma única obra): isso vira aviso e
nunca substitui um arquivo existente.

**Diárias** (`diarias_AAAA.csv`): diárias pagas a servidores nas três unidades gestoras, com data,
processo, órgão, programa, ação, fonte, natureza e valores empenhado, liquidado e pago (linha negativa é
anulação). **Nome e CPF não são gravados.** Para ver concentração sem expor ninguém, a coluna
`IdBeneficiario` traz um pseudônimo:

    IdBeneficiario = HMAC-SHA256(segredo, "<5 dígitos visíveis do CPF>|<nome sem acento, maiúsculo>")[:10]

O segredo fica só no GitHub (`VIGIA_SAL_PSEUDONIMO`). Sem ele, ninguém liga o pseudônimo à pessoa, nem
refaz o cálculo a partir de uma lista de nomes. O mesmo servidor tem o mesmo pseudônimo em todos os anos,
enquanto o segredo não mudar. Sem o segredo configurado, a coluna fica vazia (nunca há segredo fixo no
código) e um arquivo que já tem pseudônimos não é substituído. Anos: os da lista `diarias/anos`, desde 2019;
ano fechado só é baixado de novo na revisão mensal.

**Receitas** (`receitas_AAAA.csv`): para cada código de receita, o previsto, o lançado e o realizado no
ano, das três unidades gestoras (coluna `UnidadeGestora`). Os valores são **acumulados no ano, sem mês**
(cerca de 12 mil linhas por ano na Prefeitura), e os níveis se somam (1000000000 inclui 1100000000), então
não some a coluna inteira.

**Acompanhamento da arrecadação** (`receita_acompanhamento.csv`): a cada coleta, uma linha por unidade e
por grupo do topo (código de 10 dígitos terminado em nove zeros: 1000000000 receitas correntes,
2000000000 receitas de capital e, quando houver, intraorçamentárias e deduções), com `previsto`,
`realizado`, `fracao_do_ano` (dia do ano ÷ dias do ano), `esperado_pro_rata` (previsto × fração) e
`diferenca` (realizado − esperado). Rodar duas vezes no mesmo dia não duplica a linha.

É um **termômetro grosseiro**, não o cálculo legal. A lei define excesso de arrecadação como o saldo
positivo das diferenças acumuladas **mês a mês** entre o previsto e o realizado, considerando a tendência do
exercício (Lei 4.320/1964, art. 43, § 3º), e dinheiro vinculado só pode ser usado na sua finalidade (Lei de
Responsabilidade Fiscal, art. 8º, parágrafo único), então a conta é feita por fonte de recurso. Receita
também tem sazonalidade (o IPTU se concentra no começo do ano). O cálculo oficial precisa ser pedido à
prefeitura. O termômetro existe para o histórico do git mostrar como a receita evolui e para conferir quando
a prefeitura alega "excesso de arrecadação" para abrir crédito suplementar.

**Como conferir:** abra, por exemplo,
`https://wstransparencia.cariacica.es.gov.br/api/emendas/csv?exercicio=2024` (ou `obras/csv?exercicio=2024`,
`diarias/csv?unidadeGestoraId=6&exercicio=2026`, `receitas/csv?unidadeGestoraId=6&exercicio=2026`) e compare
com o arquivo do mesmo ano em `data/transparencia/`.

## 2. Tesouro Nacional (Siconfi)

**O que é:** as contas que a própria prefeitura declara ao Tesouro Nacional, padronizadas para todos
os municípios. Serve para a visão geral (receita, despesa por área, gasto com pessoal) e para
comparar Cariacica com as outras 6 cidades da Grande Vitória.

**API:** `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/` (documentação:
`https://apidatalake.tesouro.gov.br/docs/siconfi/`). **Código:** `vigia/coletores/siconfi.py`.
**Saída:** `data/siconfi/`.

| O que | Chamada | Arquivo |
|---|---|---|
| Receitas do ano (DCA Anexo I-C) | `GET /dca?an_exercicio=AAAA&no_anexo=DCA-Anexo I-C&id_ente=IBGE` | `dca_receitas.csv` |
| Despesa por natureza (DCA I-D) e por área/função (DCA I-E) | idem, `DCA-Anexo I-D` / `DCA-Anexo I-E` | `dca_despesa_natureza.csv`, `dca_despesa_funcao.csv` |
| Execução bimestral (RREO) | `GET /rreo?an_exercicio=AAAA&nr_periodo=B&co_tipo_demonstrativo=RREO&no_anexo=...&id_ente=IBGE` | `rreo_*.csv` |
| Gasto com pessoal x limite da LRF (RGF) | `GET /rgf?...&co_poder=E` | `rgf_pessoal.csv` |

Cidades (código IBGE): Cariacica 3201308, Vitória 3205309, Vila Velha 3205200, Serra 3205002,
Viana 3205101, Guarapari 3202405, Fundão 3202207. O coletor confere esses códigos no cadastro do
Siconfi a cada execução (`data/siconfi/entes.csv`).

**Quando:** todo dia; anos fechados só são baixados de novo nos dois últimos anos (as prefeituras
retificam declarações).

**Como conferir:** abra
`https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2025&no_anexo=DCA-Anexo%20I-E&id_ente=3201308`.

**Cuidado:** os códigos de conta de receita mudaram em 2022; para séries longas, use o nome da conta.

## 3. PNCP (Portal Nacional de Contratações Públicas)

**O que é:** onde, por lei (Lei 14.133/2021, art. 174), todo órgão público publica licitações,
dispensas, contratos, aditivos e atas. Para municípios a obrigação vale de fato desde 2023.
O Vigia desce **até o item**: o que foi comprado, quanto, de quem e por qual preço unitário.

**APIs:** consulta `https://pncp.gov.br/api/consulta` e detalhe `https://pncp.gov.br/api/pncp`
(documentação: `https://pncp.gov.br/api/consulta/swagger-ui/index.html`).
**Código:** `vigia/coletores/pncp.py`. **Saída:** banco (`banco/vigia.db`) e, para Cariacica,
`data/pncp/`.

Etapas, na ordem em que rodam:

| # | O que | Chamada |
|---|---|---|
| 1 | Contratações publicadas por órgãos municipais de Cariacica, por mês e modalidade | `GET /consulta/v1/contratacoes/publicacao?dataInicial=&dataFinal=&codigoModalidadeContratacao=&codigoMunicipioIbge=3201308` |
| 2 | Contratos de cada órgão municipal | `GET /consulta/v1/contratos?dataInicial=&dataFinal=&cnpjOrgao=` |
| 3 | Atas de registro de preço | `GET /consulta/v1/atas?...&cnpjOrgao=` |
| 4 | Compras de **outros** órgãos usadas por Cariacica via adesão ("carona") | `GET /pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}` |
| 5 | Itens de cada contratação | `GET /pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens` |
| 6 | Resultado de cada item (quem ganhou, preço unitário, desconto) | `.../itens/{n}/resultados` |
| 7 | Termos aditivos de cada contrato | `GET /pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}/termos` |
| 8 | **Semanal:** contratações, itens e resultados de Vitória, Vila Velha, Serra, Viana, Guarapari e Fundão (pregão e dispensa, últimos 12 meses), que servem de **referência de preço** | igual às etapas 1, 5 e 6 |

Órgãos municipais: a Prefeitura (27.150.549/0001-19) e o Fundo Municipal de Saúde
(13.917.136/0001-02) entram sempre (`config.toml`); Câmara, previdência e outros são descobertos pelo
código IBGE e conferidos pela esfera municipal ("M").

**Comportamento da coleta:** uma chamada a cada 1,5 s (a API bloqueia quem chama rápido demais);
em caso de erro 429/5xx, espera e tenta de novo até 6 vezes. **Cada resposta é guardada inteira**
na tabela `bruto` do banco, com URL e data: é a prova de onde veio cada número. Períodos com mais
de 60 dias usam a resposta guardada; os recentes são baixados de novo (o órgão pode corrigir), e isso
vale também para os itens e resultados das compras recentes. No semanal, compras do último ano que
ainda não têm nenhum resultado são visitadas de novo (o resultado pode ser homologado meses depois).
A API às vezes ignora o filtro de CNPJ: o coletor refiltra cada resposta e aborta a página se o
filtro foi ignorado.

**Como conferir:** cada linha de `data/pncp/contratacoes.csv` tem `id_pncp` no formato
`CNPJ-1-SEQUENCIAL/ANO`; a página oficial é `https://pncp.gov.br/app/editais/{CNPJ}/{ANO}/{SEQUENCIAL}`.
Contratos (`CNPJ-2-SEQ/ANO`): `https://pncp.gov.br/app/contratos/{CNPJ}/{ANO}/{SEQ}`.

## 4. Receita Federal (dados das empresas)

**O que é:** dados cadastrais públicos de cada CNPJ que contratou com o município: data de abertura,
situação, capital social, porte, atividade (CNAE), opção pelo MEI e quadro de sócios.

**Fonte:** Receita Federal, consultada pela BrasilAPI (`https://brasilapi.com.br/api/cnpj/v1/{cnpj}`),
que republica os dados abertos do CNPJ. **Código:** `vigia/coletores/empresas.py`
(`enriquecer`). **Saída:** banco; `data/receita/empresas.csv` (sem sócios, telefone e e-mail).

**Quando:** todo dia para CNPJs novos; os já consultados há mais de 30 dias são consultados de novo
(40 por execução), porque situação cadastral e opção pelo MEI mudam.

**Como conferir:** consulta oficial no site da Receita (Comprovante de Inscrição e de Situação
Cadastral) ou os dados abertos do CNPJ em `https://dados.gov.br` (conjunto "Cadastro Nacional da
Pessoa Jurídica").

## 5. CGU: empresas punidas (CEIS e CNEP)

**O que é:** cadastros federais de empresas inidôneas, suspensas ou punidas pela Lei Anticorrupção.

**API:** `https://api.portaldatransparencia.gov.br/api-de-dados/ceis` e `/cnep`
(`?codigoSancionado=<CNPJ>`). Exige uma chave gratuita, cadastrada por e-mail. No GitHub ela fica no
segredo `CHAVE_TRANSPARENCIA` e **nunca** no código. Sem chave, a etapa é pulada e a regra R13 não
roda. Alternativa sem chave: baixar os arquivos em `https://portaldatransparencia.gov.br/download-de-dados`
e rodar `python -m vigia importar-sancoes ARQUIVO`.

**Quando:** semanal, sempre consultando de novo (punição nova não pode ficar de fora). **Como conferir:** `https://portaldatransparencia.gov.br/sancoes/consulta?cpfCnpj=<CNPJ>`.

## 6. TCE-ES: receita e despesa mês a mês

**O que é:** o que a própria prefeitura envia todo mês ao Tribunal de Contas do ES (sistema CidadES,
IN 68/2020): cada receita arrecadada e cada despesa, com a previsão do orçamento e a fonte do dinheiro.

**Fonte:** dados abertos do TCE-ES no portal do Governo do ES (CKAN), conjuntos `receitas-municipios`
e `despesas-municipios` (`https://dados.es.gov.br/api/3/action/package_show?id=receitas-municipios`).
Um ZIP por ano com os 78 municípios. **Código:** `vigia/coletores/tcees.py`. **Saída:**
`data/tcees/receitas_AAAA.csv` (linha a linha) e `data/tcees/despesas_AAAA.csv` (somada por mês,
órgão, função e fonte). **Quando:** todo dia; só baixa um ano quando o CSV ainda não existe ou quando a
data de modificação do recurso no catálogo mudou (anotada em `data/tcees/recursos.csv`, com o SHA-256 do
ZIP baixado).

**Tratamento:**
1. Só recursos em ZIP com exatamente um ano no nome; dois ZIPs para o mesmo ano é erro (não adivinha).
2. O ZIP vai para um arquivo temporário e é lido em blocos; só ficam as linhas com
   `EsferaAdministrativa = Cariacica`. O ZIP nacional não é guardado: o SHA-256 vai para o manifesto, e
   qualquer pessoa baixa o mesmo arquivo na fonte.
3. O ZIP precisa ter um único CSV, e a coluna `Ano` precisa ser o ano do recurso; senão, nada é gravado.
4. Valores com vírgula viram ponto. "Arrecadada", "Empenhada", "Liquidada" e "Paga" são valores **do
   mês**; "PrevisaoInicial" (a previsão da LOA) aparece inteira no mês 1.
5. Passa pelas checagens da seção 10. Um ano com erro não impede os outros (a execução fica vermelha e diz
   qual ano falhou). O ano corrente ainda sem linhas de Cariacica até março é só aviso.

**Indicador (relatório):** arrecadado no ano até o último mês x mesmo período do ano anterior; projeção do
ano no ritmo do ano anterior (arrecadado até o mês × total do ano anterior ÷ arrecadado no mesmo período do
ano anterior); distância da previsão da LOA. Calculado para a fonte 500 (impostos e transferências de
impostos, o dinheiro livre) e para todas as fontes **sem as receitas intraorçamentárias** (classificação
começando por 7 ou 8, como a contribuição patronal paga ao IPC, que contaria o mesmo dinheiro duas vezes).
As duas colunas usam o **mesmo mês** (o último com dado nas duas). A projeção é uma estimativa e está
marcada como tal. Em janeiro, sem dado do ano, a seção mostra o ano anterior.

**Aumento líquido da dotação** (créditos adicionais menos cancelamentos = dotação atualizada − dotação da
LOA): o arquivo do TCE-ES não documenta o que "PrevisaoAtualizada" quer dizer mês a mês. O código testa as
duas leituras possíveis (valor do último mês; soma dos meses) contra a "DOTAÇÃO ATUALIZADA" do RREO
Anexo 01 do Tesouro (`data/siconfi/rreo_balanco_orcamentario.csv`, "SUBTOTAL DAS DESPESAS" mais a "RESERVA
DO RPPS", que o TCE-ES inclui na dotação) no mesmo bimestre, e só mostra o número se uma delas bater com
tolerância de 2% (e se a dotação inicial também bater). Se nenhuma bater, a linha fica "—" com uma nota.
Em 07/11/2026 a leitura que bateu foi a **soma dos meses** (o mês 1 traz a LOA mais os créditos de janeiro;
os outros meses, só os créditos do mês), ao milhar de reais, em 2025 e 2026.

**Conferência da receita:** a seção compara a receita do TCE-ES (todas as fontes, sem intra) até o fim do
último bimestre publicado com a receita realizada "Até o Bimestre" do RREO Anexo 01 do Tesouro. As duas vêm
da prefeitura por caminhos diferentes; em 07/11/2026 bateram ao centavo (2025: R$ 1.807,4 mi no ano; 2026:
R$ 1.484,5 mi até agosto). Se a diferença passar de 2%, a seção mostra um aviso e o problema vai para
`docs/qualidade.md`. Código: `vigia/indicadores.py`.

**Como conferir:** baixe o ZIP do ano no endereço acima, filtre Cariacica e some a coluna `Arrecadada`
da fonte 500 até o mês.

## 7. TSE: fornecedores das campanhas municipais

**O que é:** a lista de empresas que prestaram serviço às campanhas de Cariacica (prefeito, vice e vereador)
nas eleições municipais de 2020 e 2024, tirada das prestações de contas que as candidaturas entregam à
Justiça Eleitoral. É a entrada da regra R25, que pergunta como essas empresas foram escolhidas quando, depois
da eleição, passam a receber da prefeitura.

**Fonte:** TSE, dados abertos de prestação de contas eleitorais, arquivo de despesas contratadas
(`https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_AAAA.zip`,
dentro dele `despesas_contratadas_candidatos_AAAA_ES.csv`). **Código:** `vigia/coletores/tse.py`.
**Saída:** `data/tse/fornecedores_campanha.csv` (fora do repositório público enquanto a R25 está em revisão jurídica; ver docs/DECISOES.md). **Quando:** no coletor semanal, mas só baixa se o arquivo
ainda não existir (o dado da eleição não muda); `python -m vigia coletar tse --forcar` refaz.

**Tratamento:** dos ZIPs nacionais, só o arquivo do ES; dele, só as despesas de candidaturas de Cariacica
(`NM_UE`), de **todos os partidos**, com fornecedor de CNPJ de 14 dígitos (pessoa física fica de fora). Uma
linha por CNPJ e eleição: nome na Receita, cargos atendidos, número de candidaturas, valor contratado somado,
atividade (CNAE) e tipos de despesa. **Sem nome de candidato e sem partido**, de propósito: o mesmo critério
vale para todos, e as publicações do Vigia não citam políticos. Regras de publicação (`limpar()`):
- "Doações financeiras a outros candidatos/partidos" não é contratação e sai: o "fornecedor" seria o CNPJ
  de outra campanha (que leva o nome do político, ex.: "ELEICAO 2020 <nome> VEREADOR") ou de partido.
  Também sai qualquer CNPJ com atividade "organizações políticas" (CNAE 94.92).
- MEI: na Receita, o nome da empresa é o nome e o CPF do dono. O nome fica "MEI (nome do titular
  omitido)": a R25 usa o CNPJ, e o nome não é necessário. Se o MEI receber da prefeitura, o nome que
  aparece no alerta é o que o portal da prefeitura publica no pagamento.

**A regra (R25):** um alerta por CNPJ. Soma o `ValorPago` dos pagamentos da prefeitura
(`data/transparencia/pagamentos_*.csv`) em empenhos dos anos **seguintes** à primeira eleição em que a
empresa atendeu campanhas; cada ano conta uma vez, mesmo que ela tenha atendido 2020 e 2024. Alerta a partir
de R$ 1 milhão. O texto mostra também quanto a empresa já recebia **antes** (do início dos dados, 2019, até
o ano da eleição): quem já era fornecedora não "passou a receber" depois da campanha. Gravidade média só com
R$ 10 milhões ou mais depois e menos de R$ 1 milhão antes; senão, baixa.

Ficam de fora órgãos públicos e os casos em que o **vínculo com a campanha não indica escolha**, por ser
obrigação legal ou monopólio: banco (toda campanha precisa de conta bancária, Lei 9.504/1997, art. 22),
concessionária de energia elétrica, água encanada ou gás canalizado, e Correios. A decisão é por CNPJ: pela
atividade (CNAE) ou porque todas as despesas de campanha com a empresa foram desse tipo (tarifa bancária,
conta de luz ou água, postagem). Combustível, cartão de abastecimento, telefonia, gráfica e locação têm
concorrência e entram. Cada exclusão que passaria do mínimo é listada em `docs/qualidade.md`, seção
"Exclusões aplicadas pelas regras". Prestar serviço a campanha não é ilegal: o alerta é uma pergunta sobre
a escolha da empresa e a concorrência.

**Como conferir:** o alerta traz um link oficial por ano de pagamento (o principal é o ano de maior valor),
cada um com o total pago pela prefeitura à empresa naquele ano; as despesas de campanha estão em
`https://divulgacandcontas.tse.jus.br`.

## 8. Transferegov: emendas Pix

**O que é:** "emenda Pix" é o apelido da transferência especial (Constituição, art. 166-A, I): o dinheiro
da emenda de um deputado ou senador cai direto na conta da prefeitura, sem convênio. A prefeitura informa no
Transferegov, sistema do governo federal, o plano de ação (o que vai fazer com o dinheiro), quem executa, as
metas e, depois, os relatórios de gestão. É onde se confere se isso foi feito e quanto já foi executado.

**API:** `https://api.transferegov.gestao.gov.br/transferenciasespeciais/` (pública, sem chave, no padrão
PostgREST). **Código:** `vigia/coletores/transferegov.py`. **Saída:** `data/transferegov/`. **Quando:** semanal.

| O que | Chamada | Arquivo |
|---|---|---|
| Planos de ação (um por emenda): parlamentar, ano, área, situação, valores de custeio e investimento | `GET /plano_acao_especial?cnpj_beneficiario_plano_acao=eq.27150549000119` | `emendas_pix_planos.csv` |
| Executores de cada plano e o valor de cada um | `GET /executor_especial?id_plano_acao=in.(...)` | `emendas_pix_executores.csv` |
| Metas de cada executor | `GET /meta_especial?id_executor=in.(...)` | `emendas_pix_metas.csv` |
| Relatórios de gestão (valor executado e pendente) | `GET /relatorio_gestao_novo_especial?id_plano_acao=in.(...)` | `emendas_pix_relatorios.csv` |

**Tratamento:**
1. Cada consulta é lida página por página (`limit`/`offset`, em ordem estável), pedindo a contagem total
   (cabeçalho `Content-Range`); se a contagem não vier, a leitura segue até uma página vazia. As listas de
   ids vão em lotes de 50.
2. Cada resposta crua é guardada e tem o SHA-256 anotado no manifesto, como no portal da prefeitura.
3. Toda linha devolvida é conferida contra o filtro pedido: se a API ignorar o filtro, a coleta para (não
   baixa o país inteiro nem mistura outra cidade).
4. **Nenhum dado bancário vai para o git:** as colunas de banco, agência, conta e situação da conta são
   descartadas antes de gravar.
5. As quatro tabelas são baixadas antes de gravar qualquer uma, e cada arquivo passa pela checagem da seção 10
   (não pode perder linhas nem valor em relação à versão anterior).

**Como conferir:** abra
`https://api.transferegov.gestao.gov.br/transferenciasespeciais/plano_acao_especial?cnpj_beneficiario_plano_acao=eq.27150549000119`
no navegador e compare com `data/transferegov/emendas_pix_planos.csv`. A conferência feita no navegador em
07/11/2026 achou 19 planos de ação (2021 a 2026).

## 9. Das fontes aos alertas

As 26 regras estão em `vigia/regras.py` (o catálogo) e a lista legível é gerada do próprio código em
[`docs/REGRAS.md`](REGRAS.md). Cada regra tem:

- a **pergunta** que ela faz à prefeitura;
- por que o padrão importa e a **base legal**;
- **como verificar** no processo original;
- o que **pode ser legítimo** (explicações que desfazem o alerta).

Os limites (por exemplo, "1,5 vez a mediana dos vizinhos" ou "aditivo acima de 25%") estão em
`config.toml` (R01–R20) e no topo de cada função em `vigia/alertas/portal.py` (R21–R26). A R25 cruza os
pagamentos com as empresas contratadas por campanhas eleitorais (seção 7). A R26 cruza os contratos
emergenciais que terminam nos próximos 150 dias com as licitações de Cariacica publicadas no PNCP.

**Cada linha de [`data/alertas.csv`](../data/alertas.csv) tem:**

| Coluna | O que é |
|---|---|
| `id` | identificador estável: `sha1("regra|chave")`, 12 caracteres. O mesmo fato tem o mesmo id em todas as execuções; um post cita o id |
| `regra`, `nome_regra` | código (R01–R26) e nome |
| `gravidade` | alta, média ou baixa, pelo critério de cada regra |
| `titulo` | o fato, em uma frase |
| `pergunta` | a pergunta à prefeitura |
| `detalhe` | números e contexto |
| `valor`, `valor_excesso` | valor envolvido e, quando houver, o excesso estimado |
| `orgao`, `fornecedor`, `fornecedor_doc` | quem contratou e quem recebeu (CPF mascarado) |
| `referencia`, `data_referencia` | id do contrato/compra no PNCP, ou ano/contrato do portal |
| `link`, `outros_links` | **fonte oficial** para conferir. Alertas sobre a empresa (R09–R17) apontam para o maior contrato dela com o município no PNCP |
| `primeira_vez` | data em que o alerta apareceu pela primeira vez |
| `status`, `nota` | andamento humano (de `data/casos.csv`): novo, em análise, confirmado, denunciado, descartado |

Um alerta **não é prova**. Antes de qualquer publicação, siga o
[Protocolo de verificação](PROTOCOLO_DE_VERIFICACAO.md).

## 10. Checagens de qualidade

Erro zero não existe; o que garantimos é que **erro não passa calado**. Resultado de cada execução
em [`docs/qualidade.md`](qualidade.md); código em `vigia/qualidade.py`.

1. **Antes de gravar** (portal da prefeitura): colunas obrigatórias; id, data, valor e CNPJ/CPF no
   formato certo em 99,9% das linhas; comparação com a versão anterior (não pode perder mais de 2%
   dos registros nem do total). Falhou: o arquivo novo é descartado e fica o anterior.
2. **Rede de segurança:** nenhum CSV do repositório pode encolher mais de 2% em relação ao último
   commit; se encolher, volta à versão do commit.
3. **Banco:** conferido **antes** de exportar; nenhuma tabela pode encolher mais de 2%. Banco suspeito
   não gera CSV nem alerta e nunca substitui o bom na release (que é baixada com verificação e
   atualizada com nome novo a cada vez). A lista de alertas não pode perder mais de 20% das linhas de
   uma vez; se a análise quebrar no meio, as saídas voltam à versão anterior.
4. **Conciliação:** total empenhado no portal x declarado ao Tesouro, ano a ano. A diferença
   histórica é estável (~1%); acima de 2%, aviso.
5. **Dado antigo alterado:** na revisão mensal, se um ano fechado mudou pouco, a mudança é registrada
   em `data/qualidade/alteracoes.csv`; se mudou mais de 2%, o arquivo novo só entra depois de conferido
   (pode ser download cortado). A origem é decidida pelo hash do arquivo cru: se a prefeitura não mudou
   o arquivo, a mudança foi do nosso leitor; com menos registros, fica "a verificar".
6. **Falha visível:** fonte fora do ar, acesso negado (HTTP 401/403) ou checagem bloqueante deixa a
   execução vermelha no GitHub. Respostas inesperadas do PNCP aparecem em `docs/qualidade.md` e o
   item não é marcado como baixado (é tentado de novo).
7. **Testes automáticos** antes de cada coleta, inclusive um teste de ponta a ponta com uma API falsa
   que confere as 20 regras do PNCP, o cache, a marcação humana e que nenhum CPF vaza.

## 11. Onde cada dado fica guardado

| Onde | O que | Por quê |
|---|---|---|
| `data/` (git) | CSVs de Cariacica: portal, Siconfi, TCE-ES, PNCP, empresas, TSE, emendas Pix, alertas, qualidade | abre no Excel; o histórico do git mostra o que mudou em cada coleta |
| Release `banco` do GitHub (`vigia-AAAAMMDDTHHMM.db.gz.enc`), **criptografada** | SQLite com tudo, inclusive cidades vizinhas, sócios das empresas e as respostas cruas das APIs; os 14 últimos bancos diários e 8 retratos semanais | grande demais para o git; tem dados pessoais (sócios, CPF de fornecedor pessoa física nas respostas do PNCP), por isso fica cifrado (AES-256) com uma chave guardada só no segredo `VIGIA_CHAVE_BANCO` do GitHub |
| Artefato de cada execução (30 dias, só enquanto o repositório é privado) | arquivos crus do portal, painel HTML e dossiês | auditoria de curto prazo; têm dados pessoais, por isso não ficam públicos |

O banco é a ferramenta de trabalho do robô, não a publicação. Tudo o que é publicado está em `data/`,
e cada número de lá aponta para a fonte oficial, onde qualquer pessoa confere sem precisar do banco.
Quem mantém o projeto e tem a chave abre o banco assim:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in vigia-AAAAMMDDTHHMM.db.gz.enc -out vigia.db.gz
gunzip vigia.db.gz     # abre com o DB Browser for SQLite (https://sqlitebrowser.org/)
```

## 12. Dados pessoais (LGPD)

Os dados tratados são públicos e publicados por órgãos oficiais, usados para controle social da
administração pública (LGPD, art. 7º, §§ 3º e 4º, e art. 23). Mesmo assim, o que vai para a lista
pública e para os CSVs segue a regra do mínimo necessário:

- CPF de pessoa física aparece mascarado (`***.456.789-**`), inclusive dentro de nomes e descrições
  (há um teste que varre todos os CSVs e documentos do repositório e falha se achar um CPF inteiro);
- pagamento a pessoa física no portal da prefeitura sai sem nome e sem descrição;
- diárias saem sem nome e sem CPF; quem recebeu vira um pseudônimo (`IdBeneficiario`) calculado com um
  segredo guardado só no GitHub (seção 1, "Diárias");
- telefone e e-mail das empresas e a lista de sócios não são exportados para CSV (ficam só no banco,
  usados pelas regras R14–R16);
- nomes de pessoa física não aparecem nos títulos das regras R14 e R15;
- o arquivo do TSE não tem nome de candidato, partido nem fornecedor pessoa física (só empresas);
- o arquivo do Transferegov não tem os dados bancários da conta da prefeitura;
- nome de servidor só entra se a lista vier de pedido de LAI (arquivo em `data/entrada/`), e só para
  a regra R14; a lista pública não mostra o nome.

Nada aqui autoriza expor pessoas. O [Protocolo de verificação](PROTOCOLO_DE_VERIFICACAO.md) proíbe
publicar nome de servidor ou sócio em rede social.

## 13. Como reproduzir tudo no seu computador

Precisa de Python 3.12 ou mais novo.

```bash
git clone https://github.com/vigiacariacica/vigia-cariacica
cd vigia-cariacica
pip install -r requirements.txt
python -m pytest -q                     # confere que tudo funciona (usa dados fictícios)
python -m vigia coletar transparencia   # portal da prefeitura (minutos)
python -m vigia coletar emendas obras diarias receitas   # demais consultas do portal
python -m vigia coletar transferegov    # emendas Pix (governo federal)
python -m vigia coletar siconfi         # Tesouro (~15 min)
python -m vigia coletar pncp empresas   # PNCP de Cariacica (horas na primeira vez)
python -m vigia alertas                 # 26 regras → data/alertas.csv
python -m vigia painel                  # saida/painel.html
python -m vigia dossie --top 5          # dossiês dos 5 alertas mais graves, com pedido de LAI
```

A primeira coleta do PNCP leva horas (a API limita a velocidade); as seguintes são incrementais.
Os mesmos dados e o mesmo código geram os mesmos alertas: as versões das bibliotecas são fixas em
`requirements.txt`. Para conferir um alerta, não é preciso rodar nada: basta abrir o link oficial.

## 14. Limitações conhecidas

- O PNCP só tem as compras que os órgãos publicaram; para municípios, a obrigação vale desde 2023.
  Antes disso, a fonte é o portal da prefeitura.
- Os dados são lançados pelos próprios órgãos e podem ter erros (valor ou data errados). Por isso
  todo alerta pede conferência no link oficial e no Diário Oficial.
- A comparação de preços (R01) depende de as descrições dos itens serem parecidas; itens de
  especificação diferente podem ser comparados por engano. A regra exige várias referências de pelo
  menos dois órgãos e deixa serviços de fora.
- O PNCP não mostra quem perdeu a licitação; sinais de combinação entre concorrentes são aproximados.
- Os limites de dispensa mudam todo ano por decreto (`vigia/limites.py`); confira o decreto do ano
  antes de usar um alerta de fracionamento.
- As emendas de 2025 e 2026 não podem ser vistas pelo portal enquanto a prefeitura não corrigir o erro
  HTTP 500 (07/11/2026). Os anos 2027 e 2031 da lista dela são, provavelmente, datas de validade.
- As receitas do portal são acumuladas no ano, sem mês: o acompanhamento diário é uma aproximação, não o
  cálculo legal do excesso de arrecadação.
- O ano corrente é parcial.

## 15. IBGE: inflação (IPCA)

Fonte: API SIDRA do IBGE, tabela 1737, variável 2266 (IPCA, número-índice, base dez/1993 = 100),
Brasil, todos os meses: `https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/all?formato=json`.
Coletor `vigia/coletores/ibge.py`, todo dia (uma chamada). Gera `data/ibge/ipca.csv` (ano, mes,
indice, referencia), guardado desde 2015. A resposta crua fica no manifesto como `ibge_ipca.json`.

Para conferir: abra a URL no navegador e compare o valor do mês com a linha do CSV.

## 16. Camada refinada: o mapa do dinheiro

`python -m vigia refinar` (roda todo dia depois dos alertas; código em `vigia/refino.py`) lê os
pagamentos do portal e grava em `data/refinado/` tabelas por ano: origem do dinheiro (campo fonte
de recursos), tipo de gasto e quem executa (natureza da despesa), órgão, função, elemento, tipo de
recebedor, e uma tabela de fornecedores por raiz de CNPJ. Com o IPCA, `resumo_ano.csv` ganha valor a
preços do último ano fechado e por morador (população do Siconfi). Colunas em `docs/DICIONARIO.md`;
a leitura em `docs/MAPA_DO_DINHEIRO.md`.

Como conferir um número refinado: filtre `data/transparencia/pagamentos_AAAA.csv` pela coluna
correspondente (CodFonte, CodNaturezaDespesa, CodOrgao, CodFuncao ou os 8 primeiros dígitos do
CNPJ) e some `ValorPago`. A tradução de cada código está no topo de `vigia/refino.py`
(`_FONTES_STN`, `_FONTES_ANTIGAS`, `TIPOS`, `MODALIDADES`), e `origem_detalhe_ano.csv` lista cada
código com o nome que a prefeitura usa e a categoria atribuída.

## 17. Sonda de fontes

`ferramentas/sonda/sondar.py`, no workflow "Sonda de fontes" (manual ou ao mudar o arquivo), baixa
de dentro do GitHub Actions uma amostra de cada fonte que o Vigia ainda não usa (IBGE, CNES, Querido
Diário, dados.es.gov.br, Tesouro, Transferegov, Obrasgov, CGU, Câmara, portal de pessoal, consórcio,
FNDE, FNS) e grava em `data/sonda/` com um `RESULTADO.md`. Serve para escrever coletores com o formato
real em mãos, já que o ambiente do Claude na nuvem não alcança essas APIs. CPFs são mascarados e a
consulta de pessoal guarda só o cabeçalho.
