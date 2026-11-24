# Mapa do dinheiro público em Cariacica

**O que este documento responde:** quem gasta dinheiro público em Cariacica, por onde o dinheiro
entra, em que ele vira, quem recebe, e qual pedaço disso o Vigia já enxerga. Serve de guia para
ampliar a cobertura sem repetir trabalho. Números em R$ milhões; fonte ao lado de cada tabela.
Atualizado em 07/11/2026 com os dados de `data/` dessa data.

## 1. Três camadas de dinheiro, não uma

A prefeitura é só uma das caixas por onde o dinheiro público passa na cidade. Cada camada tem a
própria fonte oficial, e o Vigia hoje cobre bem apenas a primeira.

| Camada | Quem gasta em Cariacica | Tamanho (ordem de grandeza) | Onde está publicado | Vigia hoje |
|---|---|---|---|---|
| **Município** | Prefeitura (19 secretarias, procuradoria e gabinetes), Fundo Municipal de Saúde, Fundo de Assistência Social, Câmara Municipal, IPC (previdência, 3 fundos), Instituto de Desenvolvimento | R$ 1.705,7 mi pagos sobre os empenhos de 2025 (`data/refinado/resumo_ano.csv`) | Portal da Transparência da prefeitura (API), Siconfi, PNCP, TCE-ES | ✅ coberto: todos os órgãos, cada pagamento |
| **Consórcios públicos** | CIM Polinorte (saúde e compras em grupo) e outros consórcios de que a prefeitura participa | R$ 57,8 mi pagos pela prefeitura a consórcios em 2025 (modalidade 71–76/93, `modalidade_ano.csv`); R$ 155,9 mi em contratos no PNCP | O que a prefeitura paga ao consórcio: portal. O que o consórcio compra: PNCP (CNPJ 02.618.132/0001-07) e portal do próprio consórcio | 🟡 o pagamento e as atas de adesão sim; o gasto do consórcio em si, não |
| **Terceiro setor com dinheiro público** | Organizações sociais, OSCIPs e associações que operam serviços (saúde, assistência) por contrato de gestão, termo de colaboração ou subvenção | R$ 91,4 mi em 2025 (modalidade 50, `modalidade_ano.csv`); R$ 84,8 mi a entidades (`recebedor_ano.csv`) | Portal (pagamento e contrato); a prestação de contas de cada entidade só por LAI ou no site dela | 🟡 o pagamento sim; no que a entidade gastou, não |
| **Estado do ES** | Governo do Estado gasta direto na cidade: escolas estaduais, unidades de saúde estaduais, polícia, Cesan (água e esgoto), Ceturb (Transcol), DER (rodovias), Fundo Cidades e convênios | Ainda não levantado para Cariacica | Portal da Transparência do ES e dados.es.gov.br; empresas estaduais têm portais próprios | ⏳ não coberto; a sonda (seção 6) testa se dá para filtrar por município |
| **União** | Direto às pessoas (INSS, Bolsa Família, BPC, seguro-desemprego) e direto à cidade (obras federais, emendas, FNDE/FNS, Correios, BR-262) | Ainda não levantado para Cariacica (a API da CGU dá o valor mensal por município) | Portal da Transparência da CGU (API com chave grátis), Transferegov, Obrasgov, FNDE, FNS | ⏳ só emendas Pix (Transferegov) e, por fonte de recurso, o que entra na prefeitura |

**Leitura:** o Vigia responde hoje "para onde vai o dinheiro **da prefeitura**". Para responder
"para onde vai o dinheiro público **em Cariacica**" faltam as camadas do Estado e da União, que
são justamente as que mais pesam na vida de quem mais precisa (Bolsa Família, BPC, Transcol,
esgoto da Cesan, escolas estaduais). A ordem para fechar esses buracos está na seção 6.

## 2. Por onde o dinheiro entra na prefeitura (2025)

Fonte: Siconfi/Tesouro, DCA Anexo I-C, receitas brutas realizadas (`data/siconfi/dca_receitas.csv`,
`cod_ibge=3201308`, `exercicio=2025`). Total bruto: R$ 2.006,5 mi (a dedução do FUNDEB sai depois).

| Entrada | R$ mi | Quem decide o valor | O que é |
|---|---|---|---|
| Cota-parte do ICMS | 468,5 | Estado, pela fórmula da lei (valor adicionado na cidade pesa muito) | Parte do imposto estadual sobre mercadorias que volta ao município |
| FUNDEB (recebido) | 413,3 + 42,6 de complementação da União | Fórmula federal: número de matrículas | Só pode ir para a educação básica; 70% para pagar profissionais da educação |
| ISS (imposto sobre serviços) | 183,7 | A prefeitura cobra (alíquota e fiscalização são dela) | Imposto municipal sobre serviços prestados na cidade |
| FPM (Fundo de Participação dos Municípios) | 168,4 | União, pela população | Parte do IR e do IPI federais |
| Receita patrimonial | 126,2 (96 são rendimentos do IPC) | Mercado | Juros das aplicações, sobretudo da previdência dos servidores |
| SUS, repasses fundo a fundo | 64,4 | Ministério da Saúde, por programa | Custeio da atenção básica, média e alta complexidade, vigilância |
| IRRF (imposto de renda retido) | 57,5 | Fórmula federal | IR retido na fonte dos próprios servidores fica com o município |
| Cota-parte do IPVA | 53,8 | Estado, pela frota licenciada em Cariacica | Metade do IPVA dos veículos da cidade |
| Convênios de capital com o Estado | 51,6 | Negociação política e técnica (Sedurb, Fundo Cidades) | Dinheiro carimbado para obras (drenagem, pavimentação) |
| IPTU | 45,9 | A prefeitura cobra (planta de valores, cadastro, dívida ativa) | Imposto sobre imóveis urbanos |
| COSIP | 37,9 | A prefeitura cobra na conta de luz | Só pode pagar iluminação pública |
| FNDE | 36,3 | Fórmula federal | Merenda (PNAE), transporte escolar (PNATE), salário-educação |
| Contribuições dos servidores ao IPC | 31,6 | Lei municipal | Previdência própria (intraorçamentária) |

**O que isso diz:** quase 7 em cada 10 reais da prefeitura vêm de fora (ICMS, FUNDEB, FPM, SUS,
IPVA), por fórmulas que a prefeitura não controla. O que ela controla de verdade é o ISS, o IPTU
(cobrança, cadastro, dívida ativa) e a disputa por convênios e emendas. É aí que gestão faz
diferença na receita, e é por isso que a dívida ativa e o cadastro do IPTU estão entre os pedidos de
LAI já protocolados.

## 3. O que a prefeitura faz com o dinheiro (pagamentos sobre os empenhos de 2025)

Fonte: portal da prefeitura, todos os órgãos, somado por `vigia/refino.py` (`data/refinado/`).
Total pago: R$ 1.705,7 mi em 21.050 empenhos para 2.116 credores diferentes.

### 3a. De onde veio cada real gasto (campo "fonte de recursos" do empenho)

| Origem | R$ mi | % |
|---|---|---|
| Impostos e transferências livres (IPTU, ISS, ICMS, FPM, IPVA, incluindo os 25% obrigatórios da educação e os 15% da saúde) | 902,7 | 52,9% |
| FUNDEB | 445,6 | 26,1% |
| Saúde: SUS fundo a fundo e convênios | 93,0 | 5,5% |
| Convênios da União e do Estado (obras, em geral) | 54,4 | 3,2% |
| Educação: salário-educação, FNDE, convênios | 53,4 | 3,1% |
| COSIP | 37,9 | 2,2% |
| Previdência (recursos do IPC) | 25,0 | 1,5% |
| Fundos e outros recursos vinculados | 24,5 | 1,4% |
| Royalties e compensações financeiras | 22,3 | 1,3% |
| Assistência social: FNAS e convênios | 20,7 | 1,2% |
| Operações de crédito (empréstimos) | 14,7 | 0,9% |
| Emendas Pix | 9,3 | 0,5% |
| Alienação de bens | 2,2 | 0,1% |

A prefeitura trocou o plano de códigos das fontes em 2023 (padrão da STN). O refino traduz os dois
planos para as mesmas categorias, para a série 2019–2026 ser comparável; cada código e o nome que a
prefeitura usa estão em `origem_detalhe_ano.csv`, com aviso quando o nome sugere outra categoria.

### 3b. Em que tipo de gasto

| Tipo (grupo da natureza da despesa) | R$ mi | % |
|---|---|---|
| Custeio: serviços, materiais, contratos, terceirizados (grupo 33) | 703,7 | 41,3% |
| Pessoal e encargos, ativos e aposentados (31) | 677,7 | 39,7% |
| Investimentos: obras e equipamentos (44) | 252,1 | 14,8% |
| Amortização da dívida (46) | 40,4 | 2,4% |
| Juros da dívida (32) | 31,7 | 1,9% |

Dentro do custeio, os maiores elementos de 2025 (`elemento_ano.csv`): outros serviços de terceiros
PJ 255,8; locação de mão de obra 103,9; auxílio-alimentação 59,5; contratos de gestão 45,5;
subvenções sociais 37,8; material de consumo via consórcio 36,0; TI 29,5; material de distribuição
gratuita 25,0. Pessoal: vencimentos 348,1; contratos por tempo determinado 146,2 (temporários);
aposentadorias do RPPS 80,5; obrigações patronais 53,7 + 31,6 intra.

### 3c. Quem recebeu

| Quem recebeu | R$ mi | % |
|---|---|---|
| Empresas | 699,5 | 41,0% |
| Servidores ativos e aposentados (folha, encargos, previdência) | 684,3 | 40,1% |
| Órgãos públicos, consórcios públicos e previdência (IPC, PASEP, CIM Polinorte, INSS fora da folha) | 106,9 | 6,3% |
| Entidades sem fins lucrativos (OS, OSCIP, associações) | 84,8 | 5,0% |
| Dívida (bancos e credores) | 72,2 | 4,2% |
| Consórcios de empresas | 33,3 | 2,0% |
| Concessionárias (energia, água, telefonia, correios) | 19,2 | 1,1% |
| Pessoas físicas (sem nome: LGPD) | 5,4 | 0,3% |

### 3d. Por órgão e por área

Órgãos que mais pagaram em 2025 (`orgao_ano.csv`): Educação 636,1; Fundo de Saúde 257,4; Serviços
(limpeza urbana, iluminação) 237,1; Finanças (dívida, PASEP, aportes) 147,6; Obras 85,4; IPC fundo
financeiro 77,7; Câmara 37,8; Assistência Social (fundo) 36,1; Defesa Social 32,8; Administração 28,8.

Áreas (função de governo, `funcao_ano.csv`): Educação 636,1; Urbanismo 317,8; Saúde 257,4;
Administração 168,3; Encargos especiais (dívida) 104,0; Previdência 94,2; Assistência social 46,7;
Legislativa 37,8; Segurança 14,8; Transporte 9,1; Cultura 6,7; Esporte 4,9; Habitação 1,3.

## 4. O que cada fonte entrega e o que falta nela

| Pedaço do dinheiro | Fonte oficial | Arquivo no Vigia | Situação | O que falta / como obter |
|---|---|---|---|---|
| Cada pagamento (CNPJ, fonte, natureza, órgão, função, contrato, descrição) | Portal da prefeitura, `api/despesa` | `data/transparencia/pagamentos_AAAA.csv` | ✅ 2019–2026, todo dia | Bairro do gasto não existe no portal; só obras e escolas têm endereço |
| Contratos (valor inicial, aditivos, fiscal, vigência) | Portal, `api/contratos` | `contratos_AAAA.csv`, `emergenciais_AAAA.csv` | ✅ | PDFs dos aditivos (para separar prorrogação de acréscimo): LAI ou portal, página do contrato |
| Licitações item a item, quem ganhou, por quanto, atas, caronas | PNCP | `data/pncp/*.csv`, banco | ✅ desde 2023 | Quem perdeu cada licitação (lances): Portal de Compras Públicas, ainda sem coletor |
| Obras (empresa, estágio, bairros, valores) | Portal, `api/obras` | `obras_AAAA.csv` (221 obras, 2010–2025) | 🟡 1ª coleta feita; 2026 "sem dados" no portal | Fotografar e cobrar as marcadas como paradas (tarefa no Plano) |
| Emendas parlamentares recebidas | Portal, `api/emendas` | `emendas_AAAA.csv` | 🟡 2025 e 2026 dão erro no portal (reclamação na Ouvidoria) | Transferegov cobre as emendas Pix; CGU cobre as demais (precisa da chave) |
| Diárias (valor, órgão, sem nome) | Portal, `api/diarias` | `diarias_AAAA.csv` | ✅ com pseudônimo | Concentração por pessoa só com o segredo `VIGIA_SAL_PSEUDONIMO` cadastrado |
| Receitas (previsto, lançado, realizado por código) | Portal, `api/receitas` | `receitas_AAAA.csv`, `receita_acompanhamento.csv` | ✅ | Sem mês: o acompanhamento diário é aproximação |
| Receita e orçamento mês a mês, créditos adicionais | TCE-ES (dados.es.gov.br) | `data/tcees/*.csv` | ✅ 2019–2026 | — |
| Contas anuais, comparação com a Grande Vitória, população | Siconfi | `data/siconfi/*.csv` | ✅ 2017–2025 | Restos a pagar e dívida consolidada estão nos arquivos (RREO/RGF) e ainda não aparecem no relatório |
| Empresas: abertura, capital, CNAE, sócios | Receita (BrasilAPI) | `data/receita/empresas.csv`, banco | ✅ 297 maiores | CNAEs secundários (para regra "atividade da empresa não combina com o contrato") |
| Empresas punidas no país | CGU (CEIS/CNEP) | banco | ⏳ | **Chave grátis da CGU** no segredo `CHAVE_TRANSPARENCIA` |
| Fornecedores de campanha que viraram fornecedores | TSE | `data/tse/fornecedores_campanha.csv` | em revisão | fora do repositório público até a revisão jurídica da R25 |
| Emendas Pix | Transferegov | `data/transferegov/*.csv` | 🟡 semanal, 1ª coleta domingo | — |
| Inflação (para comparar anos) | IBGE/SIDRA | `data/ibge/ipca.csv` | 🟡 código pronto, 1ª coleta no próximo diário | — |
| **Folha: quantos servidores por cargo, vínculo e órgão, e quanto custa cada grupo** | Portal, consulta de pessoal; TCE-ES (base de pessoal) | — | ⏳ maior buraco do lado municipal (40% do gasto) | A sonda testa `api/pessoal`; publicar só agregado por cargo/vínculo, nunca nome (LGPD) |
| IPC: onde o dinheiro dos servidores está aplicado, déficit, aportes | Portal do IPC, CADPREV (Previdência) | — | ⏳ | Relatórios mensais em PDF no site do IPC; CADPREV tem CSV (DRAA) |
| Diário Oficial: decretos de crédito, dispensas, nomeações | Diário do município | — | ⏳ | A sonda testa se o Querido Diário (Open Knowledge) indexa Cariacica; senão, DOM/ES (Amunes) |
| Câmara: projetos, votações, presença, emendas ao orçamento | camarasempapel.com.br | — | ⏳ ronda semanal pelo navegador | A sonda testa se o Actions alcança o site; aí vira coletor |
| Notas fiscais dos serviços prestados à prefeitura | Portal | — | ❌ a página dá erro (reclamação feita) | Ouvidoria |
| Prestação de contas das OS/OSCIPs (Instituto Esperança, Santa Casas, Adventista) | Contrato de gestão; sites das entidades | — | ⏳ | LAI pedido específico; Lei 13.019 obriga publicação |
| Gasto do Estado em Cariacica | transparencia.es.gov.br; dados.es.gov.br | — | ⏳ | A sonda lista os conjuntos; verificar filtro "município"/"localização do gasto" |
| Cesan (esgoto) e Ceturb (Transcol) em Cariacica | Portais das empresas; e-SIC do Estado | — | ⏳ | Pedido C3 (PPP de esgoto) já previsto no Plano |
| Transferências da União por mês (FPM, FUNDEB, SUS, FNAS…) | CGU, `api-de-dados/transferencias` | — | ⏳ | Chave da CGU; a sonda confirma o formato |
| Bolsa Família, BPC por município | CGU, `novo-bolsa-familia-por-municipio`, `bpc-por-municipio` | — | ⏳ | Chave da CGU |
| Convênios e contratos de repasse federais | Transferegov (discricionárias) | — | ⏳ | A sonda baixa o catálogo do módulo |
| Obras com dinheiro federal | Obrasgov | — | ⏳ | A sonda baixa o catálogo e uma consulta por município |
| Merenda, transporte, PDDE (liberações) | FNDE (SIGEF) | — | ⏳ | A sonda testa a página de liberações |
| Postos de saúde, médicos e equipes por unidade | CNES (API DATASUS) | — | ⏳ | A sonda testa `cnes/estabelecimentos`, `profissionais`, `equipes` |
| Quem mais precisa: renda, esgoto, água, lixo, alfabetização por bairro; CadÚnico; Ideb por escola | IBGE Censo 2022, MDS, INEP | `data/raiox/*.csv` | ✅ (manual, anual) | Pré-natal, mortalidade infantil, cobertura da saúde da família (DATASUS) pausados até dezembro |

## 5. Como os dados brutos viram informação (camada `data/refinado/`)

Os CSVs do portal são a prova; a camada refinada é a leitura. `python -m vigia refinar` roda todo
dia depois dos alertas e grava (colunas em `docs/DICIONARIO.md`):

- `resumo_ano.csv`: pago, população, por morador e, com o IPCA, a preços constantes.
- `origem_ano.csv` e `origem_detalhe_ano.csv`: de onde veio o dinheiro (14 categorias) e cada código.
- `tipo_ano.csv`, `modalidade_ano.csv`, `elemento_ano.csv`: em que virou, quem executou.
- `orgao_ano.csv`, `funcao_ano.csv`: por secretaria/fundo e por área, com nome único por código.
- `recebedor_ano.csv`: empresas, servidores, entidades, consórcios, dívida, concessionárias.
- `fornecedores.csv`: uma linha por raiz de CNPJ (matriz e filiais juntas, nome único mesmo quando o
  portal escreve três grafias), total por ano, primeiro ano, órgão e área principais, CNAE e situação.

Regras da camada: nenhum número é estimado; toda tabela é soma dos registros do portal; pessoa
física aparece só somada; o ano corrente é parcial; "pago" é pago sobre os empenhos do ano.

## 6. Como fechar os buracos, em ordem

1. **Cadastrar a chave grátis da CGU** (segredo `CHAVE_TRANSPARENCIA`; tarefa no Plano). Destrava de
   uma vez: empresas punidas (R13), transferências federais por mês, Bolsa Família, BPC, convênios e
   emendas por município. É a ação de maior alavancagem, e depende de quem administra a conta do Vigia.
2. **Rodar a sonda de fontes** (Actions > "Sonda de fontes" > Run workflow). Ela grava em `data/sonda/`
   uma amostra de 27 fontes candidatas (IBGE, CNES, Querido Diário, dados.es.gov.br, Tesouro, Transferegov,
   Obrasgov, CGU, Câmara, portal de pessoal, CIM Polinorte, FNDE, FNS) e um `RESULTADO.md` dizendo o que
   cada uma respondeu. Com as amostras no repositório, o coletor de cada fonte é escrito com o formato
   real, sem depender de navegador.
3. Com as amostras: coletores de **folha agregada** (portal/TCE-ES, sem nome), **CNES** (postos e
   médicos por unidade, cruzando com `data/raiox` para a Ficha do Bairro), **Diário Oficial**
   (créditos suplementares, dispensas), **transferências e benefícios federais** (CGU).
4. **Estado**: descobrir, pela sonda, se o portal do ES publica gasto por município; se não, pedido de
   LAI ao Estado pedindo a despesa liquidada em Cariacica por órgão e ano.
5. **Regras novas que os dados refinados permitem**: gasto por origem fora da média (ex.: queda do SUS
   com alta do custeio próprio), CNAE da empresa que não combina com o objeto (precisa dos CNAEs
   secundários), crescimento real por morador acima da inflação por órgão.

## 7. Limites honestos

- O portal não diz o bairro de cada pagamento. Gasto por bairro só por aproximação: obras (campo
  Bairros), escolas e postos (endereço no CNES/INEP) e convênios com nome do bairro no título da fonte.
- "Pago" no portal é acumulado por empenho; o caixa do ano está no Siconfi (diferença histórica ~1%).
- Folha com nome de servidor existe nas bases do TCE-ES, mas o Vigia só publica agregados (LGPD).
- O gasto do Estado e da União na cidade não está, hoje, em nenhum arquivo do Vigia: tudo o que o
  relatório mostra é dinheiro que passou pela prefeitura.
