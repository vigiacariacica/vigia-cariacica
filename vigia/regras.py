"""Catálogo único das regras de alerta (R01–R27).

Cada regra tem: nome, a PERGUNTA que ela faz à prefeitura, por que importa, base legal, como
conferir e o que pode ser legítimo. Isso aparece no painel, nos dossiês e em data/alertas.csv.
Um alerta NUNCA é prova: é uma pergunta com link para a fonte oficial.

R01–R20: PNCP, Receita Federal e CGU (código em vigia/alertas/motor.py).
R21–R27: portal da transparência da prefeitura; R25 cruza com o TSE e R26 e R27 com o PNCP (código em vigia/alertas/portal.py).
"""

REGRAS = {
    "R01": {
        "nome": "Preço acima do pago pelos vizinhos",
        "pergunta": "Por que a prefeitura pagou mais que as cidades vizinhas pelo mesmo item, e qual pesquisa de preços justificou o valor?",
        "porque": "O preço unitário pago ficou bem acima da mediana do mesmo item comprado por outras "
                  "prefeituras da Grande Vitória no mesmo período. É o principal sinal de sobrepreço.",
        "base_legal": "Lei 14.133/2021, art. 23 (o valor estimado deve ser compatível com o mercado) e "
                      "art. 11, III (evitar sobrepreço e superfaturamento).",
        "verificar": [
            "Abrir o termo de referência e confirmar se o item é realmente o mesmo (marca, tamanho, embalagem).",
            "Ver a pesquisa de preços do processo: quais fontes a prefeitura usou para estimar o valor?",
            "Comparar a quantidade: compras muito pequenas costumam ter preço unitário maior.",
            "Checar se o preço inclui frete, instalação ou entrega fracionada em várias escolas/unidades.",
        ],
        "legitimas": ["Item de especificação superior", "Entrega descentralizada ou urgente",
                      "Quantidade pequena", "Variação de mercado no período (ex.: alimentos)"],
    },
    "R02": {
        "nome": "Mesmo item comprado muito mais caro em outra compra do próprio município",
        "pergunta": "Por que o mesmo item saiu mais caro nesta compra do que em outras da própria prefeitura?",
        "porque": "O próprio município pagou bem menos pelo mesmo item em outras compras próximas. "
                  "Variação grande dentro da mesma prefeitura indica falha na pesquisa de preços ou direcionamento.",
        "base_legal": "Lei 14.133/2021, art. 23, §1º, II (contratações similares feitas pela Administração).",
        "verificar": ["Comparar as especificações das duas compras.",
                      "Ver se as datas coincidem com alta de preço de mercado.",
                      "Ver quem ganhou cada uma e se a compra mais cara teve menos concorrentes."],
        "legitimas": ["Especificação diferente", "Quantidade muito diferente", "Urgência documentada"],
    },
    "R03": {
        "nome": "Aditivos de valor acima (ou perto) do limite legal",
        "pergunta": "Quanto dos aditivos foi acréscimo de quantidade (que tem limite legal) e quanto foi reajuste ou prorrogação?",
        "porque": "A soma dos acréscimos de valor passou de 25% do valor inicial (50% em reformas), "
                  "o limite da lei, ou está perto disso. Aditivos são o caminho mais comum para "
                  "inflar um contrato depois da licitação.",
        "base_legal": "Lei 14.133/2021, art. 125 (limites de 25% e 50%). Pela jurisprudência do TCU, "
                      "acréscimos e supressões não se compensam para o cálculo do limite.",
        "verificar": ["Ler cada termo aditivo e a justificativa técnica.",
                      "Separar acréscimo de quantidade (conta no limite) de reajuste/repactuação/prorrogação (não conta).",
                      "Ver se o objeto do aditivo é o mesmo do contrato original."],
        "legitimas": ["Reajuste ou repactuação contratual (não é acréscimo)",
                      "Prorrogação de serviço contínuo (renova o valor anual)",
                      "Dado do PNCP lançado de forma errada pelo órgão"],
    },
    "R04": {
        "nome": "Possível fracionamento: várias dispensas para o mesmo fornecedor",
        "pergunta": "Essas dispensas eram uma única necessidade dividida em partes? Por que não houve licitação?",
        "porque": "O mesmo fornecedor recebeu várias dispensas do mesmo órgão no mesmo ano que, somadas, "
                  "passam do limite da dispensa. Dividir uma compra para fugir da licitação é proibido.",
        "base_legal": "Lei 14.133/2021, art. 75, I e II, e §1º (soma no exercício por ramo de atividade); "
                      "art. 337-E do Código Penal (contratação direta ilegal).",
        "verificar": ["Ver se os objetos das dispensas são do mesmo ramo de atividade.",
                      "Ver se a necessidade era previsível (estava no Plano de Contratações Anual?).",
                      "Conferir o decreto de valores do ano."],
        "legitimas": ["Objetos de ramos diferentes", "Necessidades realmente imprevisíveis",
                      "Valores que incluem contratos de outro órgão com o mesmo CNPJ"],
    },
    "R05": {
        "nome": "Possível fracionamento: dispensas com objeto parecido",
        "pergunta": "Essas compras parecidas poderiam ter sido feitas numa só licitação?",
        "porque": "Várias dispensas com objeto semelhante, no mesmo órgão e ano, somam mais que o limite "
                  "da dispensa. Pode indicar divisão artificial da compra.",
        "base_legal": "Lei 14.133/2021, art. 75, §1º.",
        "verificar": ["Ler os objetos e confirmar se são do mesmo ramo.",
                      "Ver se havia como prever a necessidade e licitar de uma vez."],
        "legitimas": ["Semelhança só no texto", "Compras para unidades com orçamento próprio",
                      "Emergências reais e diferentes"],
    },
    "R06": {
        "nome": "Emergência que se repete",
        "pergunta": "Qual foi a emergência em cada contratação e por que ela se repetiu com o mesmo fornecedor?",
        "porque": "Contratações emergenciais (sem licitação) repetidas para o mesmo fornecedor ou objeto. "
                  "A lei proíbe recontratar a mesma empresa em emergência; emergência repetida costuma "
                  "ser falta de planejamento ou emergência 'fabricada'.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII (prazo máximo de 1 ano, vedada a recontratação da mesma empresa).",
        "verificar": ["Ler a justificativa da emergência.",
                      "Ver se havia licitação em andamento para resolver o problema de vez."],
        "legitimas": ["Emergências diferentes de verdade (enchentes, epidemias)", "Alguns entendem que a proibição vale só para a mesma emergência"],
    },
    "R07": {
        "nome": "Adesão a ata de outro órgão ('carona') com agravantes",
        "pergunta": "Qual estudo mostrou que aderir à ata de outro órgão era mais vantajoso do que licitar?",
        "porque": "O contrato foi feito aproveitando a licitação de OUTRO órgão, sem licitação própria. "
                  "É legal, mas foi justamente o problema que o TCE-ES apontou em 2025 num contrato da "
                  "Educação de Cariacica: ata de consórcio sem quantitativos e com desconto mínimo.",
        "base_legal": "Lei 14.133/2021, art. 86, §§2º a 5º (requisitos e limites da adesão) e art. 82 "
                      "(a ata deve indicar quantidades).",
        "verificar": ["Ver o estudo que justificou a adesão e a pesquisa de preços que comprovou vantagem.",
                      "Conferir se a ata original define quantidades máximas.",
                      "Conferir o limite de adesões (50% por órgão, dobro do total)."],
        "legitimas": ["Ata de órgão grande com preço comprovadamente vantajoso"],
    },
    "R08": {
        "nome": "Licitação com desconto quase zero",
        "pergunta": "Quantas empresas disputaram e por que o desconto sobre o valor estimado foi quase zero?",
        "porque": "O valor homologado ficou praticamente igual ao estimado. Em compras grandes, isso pode "
                  "indicar pouca competição, combinação entre concorrentes ou estimativa inflada.",
        "base_legal": "Lei 14.133/2021, art. 11 (seleção da proposta mais vantajosa).",
        "verificar": ["Ver quantas empresas participaram e quantas foram desclassificadas.",
                      "Ver se o edital tinha exigências que afastam concorrentes."],
        "legitimas": ["Estimativa bem feita", "Mercado com poucos fornecedores", "Orçamento sigiloso"],
    },
    "R09": {
        "nome": "Empresa aberta pouco antes de contratar",
        "pergunta": "Como uma empresa aberta há tão pouco tempo comprovou capacidade técnica para esse contrato?",
        "porque": "A empresa foi aberta poucos meses antes do primeiro contrato. Empresas criadas para "
                  "um contrato específico são marca comum de empresas de fachada.",
        "base_legal": "Lei 14.133/2021, arts. 66 e 67 (habilitação técnica e econômica).",
        "verificar": ["Ver os atestados de capacidade técnica apresentados.",
                      "Ver se a empresa tem sede real, funcionários e outros clientes.",
                      "Ver quem são os sócios e se têm outras empresas."],
        "legitimas": ["Empresa nova de verdade com equipe experiente", "Mudança de CNPJ de grupo existente",
                      "Consórcio de empresas criado para a própria licitação (normal; olhe as empresas que o formam)"],
    },
    "R10": {
        "nome": "Capital social muito pequeno para o tamanho do contrato",
        "pergunta": "Como uma empresa com esse capital social comprovou capacidade econômica para esse contrato?",
        "porque": "O capital declarado é uma fração mínima do valor contratado. Sozinho não prova nada, "
                  "mas somado a outros sinais ajuda a identificar empresas sem estrutura. Vale só para empresas "
                  "(sociedades, empresário individual, cooperativas): associação, fundação, organização social, "
                  "sindicato e consórcio não têm capital social, e a Receita mostra R$ 0.",
        "base_legal": "Lei 14.133/2021, art. 69 (qualificação econômico-financeira).",
        "verificar": ["Ver o balanço exigido na habilitação.", "Ver se houve exigência de garantia."],
        "legitimas": ["Capital social antigo e nunca atualizado", "Serviços com pouco investimento"],
    },
    "R11": {
        "nome": "MEI recebendo acima do limite anual do MEI",
        "pergunta": "Como um MEI recebeu mais que o limite de faturamento do MEI?",
        "porque": "Empresa registrada como MEI recebeu, só deste município, mais do que o faturamento "
                  "anual permitido ao MEI. Pode ser 'laranja' ou empresa desenquadrada.",
        "base_legal": "Lei Complementar 123/2006, art. 18-A (limite do MEI).",
        "verificar": ["Ver se a empresa foi desenquadrada depois.", "Ver quem é o titular."],
        "legitimas": ["Desenquadramento já feito e ainda não refletido na base"],
    },
    "R12": {
        "nome": "CNPJ com situação irregular na Receita",
        "pergunta": "A empresa estava regular na Receita quando contratou e quando recebeu?",
        "porque": "A empresa está baixada, suspensa ou inapta na Receita Federal.",
        "base_legal": "Lei 14.133/2021, art. 68 (regularidade fiscal).",
        "verificar": ["Ver a data em que a situação mudou e comparar com a data do contrato e dos pagamentos."],
        "legitimas": ["Situação mudou depois do contrato encerrado"],
    },
    "R13": {
        "nome": "Empresa punida (CEIS/CNEP)",
        "pergunta": "A punição da empresa valia na data do contrato e para este município?",
        "porque": "A empresa consta no cadastro de empresas inidôneas, suspensas ou punidas pela Lei Anticorrupção.",
        "base_legal": "Lei 14.133/2021, arts. 14 e 156; Lei 12.846/2013.",
        "verificar": ["Ver a abrangência da sanção: algumas valem só para o órgão que puniu "
                      "ou só para um estado; a declaração de inidoneidade vale para todos.",
                      "Comparar o período da sanção com a data do contrato."],
        "legitimas": ["Sanção restrita a outro ente", "Sanção fora do período do contrato"],
    },
    "R14": {
        "nome": "Sócio com o mesmo nome de servidor municipal",
        "pergunta": "É a mesma pessoa ou um homônimo? Se for a mesma, ela tinha relação com a contratação?",
        "porque": "Um sócio da empresa tem o mesmo nome completo de um servidor do município. "
                  "Pode ser conflito de interesse proibido, MAS pode ser só um homônimo.",
        "base_legal": "Lei 14.133/2021, art. 9º, §1º (agente público do órgão não pode participar da "
                      "licitação ou do contrato) e art. 14, IV (vínculo com dirigente ou agente da licitação).",
        "verificar": ["Confirmar se é a mesma pessoa (CPF parcial, cidade, idade) ANTES de qualquer conclusão.",
                      "Ver o cargo e a lotação do servidor: tem relação com o contrato?"],
        "legitimas": ["Homônimo", "Servidor sem qualquer relação com a contratação (ainda assim vedado em alguns casos)"],
    },
    "R15": {
        "nome": "Empresas diferentes com sócio em comum",
        "pergunta": "Essas empresas com sócio em comum disputaram as mesmas licitações?",
        "porque": "Empresas que contratam com o mesmo órgão compartilham sócio. Se elas concorrem "
                  "entre si, a competição pode ser de fachada (rodízio, cobertura).",
        "base_legal": "Lei 14.133/2021, art. 14 e art. 337-F do Código Penal (fraude ao caráter competitivo).",
        "verificar": ["Ver se as empresas participaram da mesma licitação.",
                      "Ver se uma deu 'proposta de cobertura' para a outra ganhar."],
        "legitimas": ["Empresas do mesmo grupo que nunca disputaram o mesmo certame"],
    },
    "R16": {
        "nome": "Empresas diferentes com mesmo telefone, e-mail ou endereço",
        "pergunta": "Essas empresas com o mesmo contato são independentes entre si?",
        "porque": "Dados de contato em comum entre empresas que contratam com o mesmo órgão podem indicar "
                  "o mesmo dono por trás (laranjas) ou o mesmo contador.",
        "base_legal": "Lei 14.133/2021, art. 337-F do Código Penal.",
        "verificar": ["Ver se o dado em comum é de um escritório de contabilidade.",
                      "Ver se as empresas disputaram as mesmas licitações."],
        "legitimas": ["Contador ou escritório compartilhado", "Mesmo prédio comercial"],
    },
    "R17": {
        "nome": "Fornecedor concentra grande parte dos gastos do órgão",
        "pergunta": "Esse fornecedor chegou a essa fatia por licitações com concorrência?",
        "porque": "Um único fornecedor ficou com uma fatia muito grande do que o órgão contratou no ano. "
                  "É informativo: ajuda a decidir onde olhar primeiro.",
        "base_legal": "Princípio da competitividade (Lei 14.133/2021, art. 5º).",
        "verificar": ["Ver se os contratos vieram de licitações competitivas."],
        "legitimas": ["Serviço essencial único (ex.: coleta de lixo, OS de saúde)"],
    },
    "R18": {
        "nome": "Datas inconsistentes",
        "pergunta": "As datas estão certas no processo original e no Diário Oficial?",
        "porque": "Contrato assinado antes da publicação da compra, ou vigência que termina antes de começar. "
                  "Pode ser erro de lançamento ou processo montado 'de trás para frente'.",
        "base_legal": "Lei 14.133/2021, arts. 54 e 94 (publicidade como condição de eficácia).",
        "verificar": ["Conferir as datas no processo original e no Diário Oficial."],
        "legitimas": ["Erro de digitação no PNCP", "Publicação tardia no PNCP"],
    },
    "R19": {
        "nome": "Contrato emergencial prorrogado",
        "pergunta": "O termo registrado como prorrogação estendeu um contrato emergencial? Com qual justificativa, e onde está a licitação definitiva?",
        "porque": "Contrato feito por emergência, sem licitação, que recebeu termo de prorrogação. A lei de "
                  "licitações proíbe prorrogar contrato emergencial: a emergência deve ser resolvida no prazo "
                  "e, nesse meio tempo, a prefeitura deve fazer a licitação. Gravidade alta quando o prazo total "
                  "(original mais prorrogação) passa de 1 ano, o teto da lei; média quando fica dentro de 1 ano, "
                  "porque há entendimentos que aceitam prorrogar dentro desse limite.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII (\"vedadas a prorrogação dos respectivos contratos\") e "
                      "§6º (apuração de responsabilidade de quem deu causa à emergência).",
        "verificar": ["Ler a justificativa do termo de prorrogação.",
                      "Ver se a soma do prazo inicial com a prorrogação passou de 1 ano.",
                      "Ver se havia licitação aberta para o mesmo serviço e em que pé estava."],
        "legitimas": ["Alguns órgãos de controle aceitam esticar o prazo desde que o total não passe de 1 ano",
                      "Erro de lançamento no PNCP (termo que na verdade é de outro contrato)"],
    },
    "R20": {
        "nome": "O mesmo serviço contratado por emergência de novo",
        "pergunta": "Por que esse serviço voltou a ser contratado por emergência e quando sai a licitação definitiva?",
        "porque": "O município contratou por emergência, mais de uma vez e em momentos diferentes, um serviço "
                  "parecido. Serviço contínuo (gestão de unidade de saúde, limpeza, ambulância) não deveria "
                  "virar emergência todo ano: isso costuma indicar falta de planejamento ou emergência 'fabricada'.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII e §6º (a emergência não pode decorrer de falta de "
                      "planejamento; quem deu causa deve ser responsabilizado).",
        "verificar": ["Pedir pela LAI o andamento da licitação ou chamamento definitivo para o serviço.",
                      "Comparar o valor de cada emergência com o anterior.",
                      "Ver se o TCE-ES já tem processo sobre o serviço."],
        "legitimas": ["Emergências reais e distintas (deslizamentos em locais diferentes, epidemias)",
                      "Licitação que fracassou ou foi suspensa pelo Tribunal de Contas"],
    },
    # ------------------------------------------------------------------
    # R21–R24: portal da transparência da prefeitura (pagamentos e contratos de 2019 em diante); R25 abaixo
    # ------------------------------------------------------------------
    "R21": {
        "nome": "Salto de pagamentos a um fornecedor",
        "pergunta": "Qual contrato explica esse aumento e como ele foi licitado?",
        "porque": "O fornecedor recebeu no ano pelo menos R$ 5 milhões e 4 vezes o maior valor dos três anos "
                  "anteriores. Contrato novo licitado explica; o alerta pede que se diga qual.",
        "base_legal": "Lei 14.133/2021, art. 11 (proposta mais vantajosa) e LC 131/2009 (transparência da execução).",
        "verificar": ["Abrir o link oficial e ver os pagamentos do ano ao fornecedor.",
                      "Achar no portal o contrato e a licitação que deram origem aos pagamentos.",
                      "Ver se houve aditivo ou contrato emergencial no período."],
        "legitimas": ["Contrato novo, licitado com concorrência", "Obra grande que começou naquele ano",
                      "Pagamento atrasado de anos anteriores"],
    },
    "R22": {
        "nome": "Aditivos no portal municipal além do que a prorrogação explica (triagem)",
        "pergunta": "Quanto dos aditivos foi prorrogação de prazo, quanto foi reajuste e quanto foi acréscimo de objeto?",
        "porque": "O contrato recebeu aditivos acima de 25% do valor original. O portal só publica o total dos "
                  "aditivos, sem separar prorrogação, reajuste e acréscimo, então esta regra é uma triagem e nunca dá "
                  "gravidade alta. Supondo 12 meses no valor original e reajuste de até 6% ao ano, calcula-se o que a "
                  "prorrogação explica e o máximo com acréscimo de 25% desde o início (o acréscimo legal se repete em "
                  "cada ano prorrogado). Média quando o total passa desse máximo, ou sobra mais de 25% e R$ 1 milhão "
                  "além da prorrogação; baixa no resto. A confirmação vem dos termos aditivos (regra R03 no PNCP, ou "
                  "pedido pela Lei de Acesso).",
        "base_legal": "Lei 14.133/2021, art. 125 (acréscimo limitado a 25%; 50% em reforma) e art. 107 "
                      "(prorrogação de serviço contínuo). Contratos antigos: Lei 8.666/1993, art. 65, §1º.",
        "verificar": ["Pedir os termos aditivos e a justificativa de cada um.",
                      "Separar prorrogação, reajuste/repactuação e acréscimo de quantidade.",
                      "Conferir se o contrato original cobria 12 meses ou mais (se mais, a sobra é maior)."],
        "legitimas": ["Reajuste anual por índice", "Repactuação por convenção coletiva",
                      "Contrato original com prazo menor que 12 meses"],
    },
    "R23": {
        "nome": "Contrato emergencial (sem licitação) acima de R$ 1 milhão",
        "pergunta": "Qual foi a emergência e quando sai a licitação definitiva?",
        "porque": "Contratação emergencial dispensa licitação. Deve ser exceção, por prazo curto, e seguida de licitação.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII (até 1 ano, vedada prorrogação e recontratação) e §6º.",
        "verificar": ["Ler a justificativa da emergência no processo.",
                      "Ver se havia licitação em andamento para o mesmo serviço.",
                      "Comparar com emergências anteriores do mesmo serviço (regras R06 e R20)."],
        "legitimas": ["Desastre, epidemia ou interrupção súbita de serviço essencial",
                      "Licitação suspensa pelo Tribunal de Contas"],
    },
    "R24": {
        "nome": "Pagamento a fornecedor durante punição da própria prefeitura",
        "pergunta": "Eram pagamentos de contratos anteriores à punição?",
        "porque": "O fornecedor recebeu pagamentos no período em que estava suspenso ou declarado inidôneo pela prefeitura.",
        "base_legal": "Lei 14.133/2021, art. 156 (sanções) e Lei 8.666/1993, art. 87.",
        "verificar": ["Ver a data de assinatura do contrato que gerou os pagamentos.",
                      "Ler a decisão da punição: ela alcança contratos em andamento?"],
        "legitimas": ["Pagamento por serviço prestado antes da punição", "Contrato em andamento não alcançado pela sanção"],
    },
    # ------------------------------------------------------------------
    # R25: portal da prefeitura x TSE (empresas contratadas por campanhas de Cariacica em 2020 e 2024)
    # ------------------------------------------------------------------
    "R25": {
        "nome": "Fornecedor de campanha eleitoral que recebeu da prefeitura depois da eleição",
        "pergunta": "Como essa empresa foi escolhida para os contratos da prefeitura depois de prestar serviço a "
                    "campanhas eleitorais na cidade, e houve concorrência?",
        "porque": "A empresa foi contratada por candidaturas de Cariacica numa eleição municipal (dados do TSE) e, "
                  "nos anos seguintes, recebeu da prefeitura pelo menos R$ 1 milhão. Um alerta por empresa, com o que "
                  "ela recebeu antes e depois da eleição (os dados do portal começam em 2019). Gravidade média quando "
                  "recebeu R$ 10 milhões ou mais depois e menos de R$ 1 milhão antes; senão, baixa. Prestar serviço a "
                  "campanha não é ilegal; o cruzamento existe para dar transparência à relação entre quem atende "
                  "campanhas e quem recebe do município, com o mesmo critério para todos. O Vigia não publica nome "
                  "de candidato nem de partido. Ficam de fora órgãos públicos e os vínculos que não indicam escolha, "
                  "por serem obrigação legal ou monopólio: bancos (toda campanha precisa de conta bancária), "
                  "concessionárias de energia, água e gás canalizado e Correios. Cada exclusão aparece em "
                  "docs/qualidade.md. Quando a maior parte do valor é auxílio-alimentação ou outro benefício de "
                  "servidores pago por meio da empresa (administradora de cartão), o alerta diz isso e fica em baixa: "
                  "o dinheiro vai para os servidores, e a empresa fica só com a taxa de administração.",
        "base_legal": "Constituição Federal, art. 37 (impessoalidade e moralidade); Lei 14.133/2021, art. 5º "
                      "(impessoalidade) e art. 9º (vedações a quem participa da contratação).",
        "verificar": ["Abrir os links oficiais (um por ano) e ver os pagamentos da prefeitura à empresa.",
                      "Achar os contratos que geraram os pagamentos e ver a modalidade de cada um (licitação, "
                      "dispensa, adesão a ata) e quantas empresas disputaram.",
                      "Conferir no TSE (https://divulgacandcontas.tse.jus.br) as despesas de campanha com a empresa."],
        "legitimas": ["Empresa que já fornecia à prefeitura antes da eleição (o alerta mostra quanto)",
                      "Empresa de serviço comum (posto de combustível, gráfica, locação de estruturas) que atende "
                      "campanhas e prefeituras ao mesmo tempo",
                      "Contrato ganho em licitação aberta, com vários concorrentes"],
    },
    # ------------------------------------------------------------------
    # R26: portal da prefeitura x PNCP (a pergunta antes da próxima emergência)
    # ------------------------------------------------------------------
    "R26": {
        "nome": "Contrato emergencial perto do fim sem licitação parecida à vista",
        "pergunta": "O contrato emergencial termina em breve. Já existe licitação publicada para substituí-lo?",
        "porque": "Contrato emergencial vale no máximo 1 ano e não pode ser prorrogado nem repetido. Quando ele "
                  "termina sem licitação pronta, a saída costuma ser uma nova emergência (regras R06 e R20). Esta "
                  "regra olha os contratos emergenciais do portal que terminam nos próximos 150 dias e procura no "
                  "PNCP uma licitação ou credenciamento de Cariacica com objeto parecido, publicado depois do "
                  "início da emergência. Não achando, pergunta antes que a próxima emergência aconteça. Obras "
                  "pontuais (encosta, contenção, chuva) ficam de fora, porque terminam com a obra. Gravidade média "
                  "a partir de R$ 1 milhão; abaixo disso, baixa.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII (até 1 ano, vedadas a prorrogação e a recontratação da "
                      "mesma empresa) e §6º (apuração de responsabilidade quando a emergência vem de falta de "
                      "planejamento).",
        "verificar": ["Abrir o CSV oficial dos contratos emergenciais do ano e conferir a data final do contrato.",
                      "Procurar no PNCP (https://pncp.gov.br) e no portal de compras da prefeitura uma licitação "
                      "para o mesmo serviço.",
                      "Perguntar à secretaria responsável qual é o plano para quando o contrato terminar."],
        "legitimas": ["Licitação publicada só no portal de compras da prefeitura, ainda não enviada ao PNCP",
                      "Chamamento público de organização social, que pode não aparecer no PNCP",
                      "Serviço que não será mais necessário depois do fim do contrato"],
    },
    # ------------------------------------------------------------------
    # R27: portal da prefeitura x PNCP (o contrato regular que chega ao teto de prazo)
    # ------------------------------------------------------------------
    "R27": {
        "nome": "Contrato de serviço no teto de prazo sem licitação nova à vista",
        "pergunta": "O contrato chega ao fim do prazo máximo em breve. Já existe licitação publicada para substituí-lo?",
        "porque": "Serviço contínuo contratado pela Lei 8.666 pode durar até 60 meses, mais 12 em caso excepcional. "
                  "Quando um contrato grande chega a esse teto sem licitação nova, a saída costuma ser uma "
                  "contratação emergencial, mais cara e sem disputa. Foi o que aconteceu com a limpeza dos postos e "
                  "das escolas em 2026. Esta regra olha os contratos de serviço do portal acima de R$ 5 milhões que "
                  "terminam nos próximos 150 dias depois de 60 meses ou mais e procura no PNCP uma licitação de "
                  "Cariacica com objeto parecido publicada nos 18 meses antes do fim. Gravidade alta quando o "
                  "contrato custa R$ 10 milhões ou mais por ano.",
        "base_legal": "Lei 8.666/1993, art. 57, II e §4º (prazo dos serviços contínuos); Lei 14.133/2021, art. 75, "
                      "VIII e §6º (emergência e apuração de responsabilidade).",
        "verificar": ["Abrir o CSV oficial dos contratos do ano e conferir as datas de início e fim.",
                      "Procurar no PNCP e no portal de compras da prefeitura uma licitação para o mesmo serviço.",
                      "Conferir no Plano de Contratações Anual (PNCP) a data prevista para a nova contratação."],
        "legitimas": ["Licitação publicada só no portal de compras da prefeitura, ainda não enviada ao PNCP",
                      "Contrato regido pela Lei 14.133, que admite prazos de até 10 anos",
                      "Serviço que será feito pela própria prefeitura ou por consórcio público"],
    },
    "R29": {
        "nome": "Emergência previsível: contrato emergencial no lugar de um contrato que já tinha data para acabar",
        "pergunta": "O fim do contrato anterior estava marcado desde a assinatura. Por que a licitação nova não saiu "
                    "a tempo e o serviço passou a ser contratado por emergência?",
        "porque": "Emergência serve para o imprevisível (art. 75, VIII da Lei 14.133). Quando um contrato regular "
                  "chega ao fim na data que ele mesmo previa e o serviço passa para uma emergência, sem disputa, o "
                  "problema era previsível, e a lei manda apurar a responsabilidade de quem deixou de planejar "
                  "(§6º). A regra junta cada emergencial acima de R$ 1 milhão com o contrato regular da mesma "
                  "secretaria, com objeto parecido, que terminou até 120 dias antes (ou terminaria até 60 dias "
                  "depois) do início da emergência, e só alerta quando nenhuma licitação parecida foi publicada (PNCP "
                  "ou portal) com pelo menos 90 dias de antecedência do fim. Origem: a limpeza das escolas em 2026. "
                  "Gravidade alta a partir de R$ 10 milhões.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII e §6º; Lei 8.666/1993, art. 24, IV (contratos antigos).",
        "verificar": ["Abrir os dois contratos no portal (links do alerta) e conferir datas e objetos.",
                      "Procurar a licitação nova no portal de licitações e no PNCP e anotar a data de publicação.",
                      "Ler a justificativa da emergência no processo: ela cita o fim do contrato anterior?"],
        "legitimas": ["Licitação feita a tempo, mas impugnada, suspensa pelo Tribunal de Contas ou deserta",
                      "Empresa anterior abandonou o contrato ou foi punida antes do fim",
                      "Objeto parecido, mas serviço diferente (o texto dos objetos engana a comparação)"],
    },
    "R30": {
        "nome": "Seleção sem conclusão enquanto o mesmo serviço roda por emergência",
        "pergunta": "A licitação (ou o chamamento) para este serviço ainda não foi concluída, meses depois de publicada. "
                    "O que falta para concluí-la, e até quando a emergência vai continuar?",
        "porque": "Uma emergência deve durar só o tempo de terminar a contratação regular. Se a licitação ou o "
                  "chamamento ficam 'em andamento' ou 'suspensos' por meses enquanto a emergência paga o serviço sem "
                  "disputa, a exceção vira regra. A regra cruza os contratos emergenciais valendo hoje, acima de "
                  "R$ 1 milhão, com as licitações do portal da prefeitura em situação 'em andamento' ou 'suspensa' "
                  "publicadas há mais de 120 dias, com objeto parecido. Origem: o PA do Trevo. A situação do portal "
                  "nem sempre é atualizada (em 13/11/2026 ele ainda mostrava 'em andamento' o chamamento 2/2025, que "
                  "teve vencedora em agosto de 2025 e foi revogado em dezembro); por isso a regra usa as correções "
                  "provadas por documento: as que o robô deduz dos documentos anexados no PNCP e as conferidas à "
                  "mão em data/transparencia/situacao_corrigida.csv. Seleção anulada ou revogada sai da conta, e "
                  "a suspensa mostra desde quando. Gravidade alta a partir de R$ 10 milhões.",
        "base_legal": "Lei 14.133/2021, art. 75, VIII (emergência por no máximo 1 ano, sem prorrogação nem "
                      "recontratação da mesma empresa) e §6º.",
        "verificar": ["Abrir a licitação no portal e ler os ANEXOS, não só o campo situação: anulação, revogação, "
                      "suspensão, ata de resultado ou link para pasta com os documentos (impugnação, recurso, "
                      "suspensão pelo Tribunal de Contas). Achou ato que o portal não mostra? Anotar em "
                      "data/transparencia/situacao_corrigida.csv com a data e o link.",
                      "Procurar no TCE-ES se há processo sobre a licitação ou o chamamento.",
                      "Conferir a data de fim da emergência e se já existe outra emergência para depois."],
        "legitimas": ["Suspensão determinada pelo Tribunal de Contas ou pela Justiça",
                      "Portal desatualizado: a licitação já terminou e o contrato regular está para começar",
                      "Licitação refeita do zero por erro no edital"],
    },
    "R31": {
        "nome": "Contrato sem publicação no PNCP",
        "pergunta": "A lei diz que, sem publicação no Portal Nacional de Contratações Públicas (PNCP), o contrato não "
                    "tem eficácia. Este contrato foi publicado lá?",
        "porque": "Desde a Lei 14.133, todo contrato tem que ser divulgado no PNCP, e essa divulgação é condição para o "
                  "contrato valer. A regra procura, entre os contratos do portal da prefeitura assinados desde 2025, "
                  "acima de R$ 1 milhão e com mais de 30 dias, os que não têm correspondente nos contratos de Cariacica "
                  "publicados no PNCP (mesma raiz de CNPJ do fornecedor e mesmo número, ou valor a menos de 1%). "
                  "Ficam de fora autorizações e concessões de uso, convênios e parcerias. Pode ser falha da coleta ou "
                  "número diferente: por isso a gravidade é média.",
        "base_legal": "Lei 14.133/2021, art. 94 (divulgação no PNCP como condição de eficácia do contrato) e art. 174.",
        "verificar": ["Procurar o contrato no PNCP (pncp.gov.br) pelo nome do fornecedor e pelo órgão Município de "
                      "Cariacica.",
                      "Conferir se foi publicado por outro órgão (fundo municipal, consórcio) ou como nota de empenho.",
                      "Ver no portal a data de assinatura e a de publicação do extrato."],
        "legitimas": ["Publicado no PNCP com outro número ou por outro CNPJ do município",
                      "Contrato de adesão publicado só pelo órgão dono da ata (ainda assim, o contrato do aderente "
                      "precisa ser divulgado)",
                      "Atraso de publicação já corrigido",
                      "Contrato de licitação aberta ainda pela Lei 8.666 (edital até 2023), que seguia a regra antiga de "
                      "publicação do extrato na imprensa oficial"],
    },
    "R32": {
        "nome": "Licitação na forma presencial",
        "pergunta": "A lei manda fazer licitação de preferência pela internet. Por que esta foi presencial, onde está a "
                    "motivação e onde estão as gravações da sessão?",
        "porque": "Na forma presencial só disputa quem vai até a sala no dia; na eletrônica, empresas de todo o país. A "
                  "Lei 14.133 admite a presencial só com motivação e com a sessão gravada em áudio e vídeo. A regra "
                  "lista as licitações de Cariacica publicadas no PNCP desde 2024, acima de R$ 1 milhão, na forma "
                  "presencial, com o desconto obtido quando o contrato já saiu. Gravidade alta acima de R$ 10 milhões "
                  "com desconto menor que 5%. Em 12/11/2026, as quatro presenciais contratadas somavam R$ 504 milhões "
                  "estimados e tiveram 2,2% de desconto; nas sete concorrências eletrônicas da prefeitura acima de R$ "
                  "10 milhões (sem registro de preços), o desconto típico foi de 7%. São poucos casos e as presenciais "
                  "são maiores, então a comparação levanta a pergunta, não prova nada. Quando a abertura ainda não aconteceu, qualquer pessoa pode pedir esclarecimento ou impugnar o "
                  "edital até 3 dias úteis antes.",
        "base_legal": "Lei 14.133/2021, art. 17, §2º (forma eletrônica preferencial; presencial motivada e gravada) e "
                      "art. 164 (impugnação e pedido de esclarecimento por qualquer pessoa).",
        "verificar": ["Ler no edital a justificativa da forma presencial.",
                      "Pedir a ata e a gravação da sessão e ver quantas empresas participaram.",
                      "Comparar o desconto com licitações eletrônicas parecidas da própria prefeitura e de cidades vizinhas."],
        "legitimas": ["Motivação técnica registrada no processo (ex.: visita técnica obrigatória, falha do sistema)",
                      "Muitas empresas participaram e o preço estimado já era justo"],
    },
    "R33": {
        "nome": "Empenho feito depois do fim do contrato",
        "pergunta": "O contrato com este fornecedor já tinha acabado quando o dinheiro foi empenhado. Com que contrato, "
                    "aditivo ou ato esse pagamento foi feito, e a que serviço se refere?",
        "porque": "Depois do fim do contrato, a prefeitura só deveria pagar o que foi prestado durante a vigência, com "
                  "empenho feito dentro dela (resto a pagar). Um empenho novo, feito depois do fim, sem contrato valendo, "
                  "pode ser indenização, reconhecimento de dívida, diferença de quantidade ou serviço prestado sem "
                  "cobertura: tudo isso exige processo próprio e justificativa, e muitas vezes o empenho nem diz o número "
                  "do contrato. A regra olha empenhos com valor pago a partir de R$ 500 mil, feitos até um ano depois do "
                  "fim do último contrato do fornecedor no portal, quando nenhum contrato dele cobria a data e nenhum "
                  "começava nos 30 dias seguintes. Compra de material e equipamento fica de fora, porque pode ser feita "
                  "só com nota de empenho (art. 95, II). Origem: o PA do Trevo, onde saíram R$ 10,6 milhões depois do fim de "
                  "três contratos de gestão, quatro de cinco empenhos sem número de contrato. Gravidade alta a partir de "
                  "R$ 1 milhão.",
        "base_legal": "Lei 4.320/1964, arts. 60 a 63 (empenho prévio e liquidação do serviço prestado); Lei 14.133/2021, "
                      "art. 95 (contrato obrigatório) e art. 149 (nulidade e indenização do que foi executado).",
        "verificar": ["Abrir o empenho no portal e ler a descrição e o processo.",
                      "Procurar no portal um contrato, aditivo ou ata de registro de preço do fornecedor que o "
                      "cadastro não mostra.",
                      "Pedir pela Lei de Acesso o processo do pagamento (cálculo, parecer jurídico e ato que autorizou)."],
        "legitimas": ["Contrato ou aditivo novo que o portal não cadastrou",
                      "Indenização por serviço prestado de boa-fé, com processo e parecer (Lei 14.133, art. 149)",
                      "Diferenças ou reequilíbrio do contrato encerrado, reconhecidos em processo",
                      "Compra por ata de registro de preço sem contrato formal"],
    },
}

GRAVIDADE_PONTOS = {"alta": 3, "media": 2, "baixa": 1}
GRAVIDADE_NOME = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}


def markdown() -> str:
    """docs/REGRAS.md, gerado deste catálogo a cada execução (o documento nunca diverge do código)."""
    partes = [f"# As {len(REGRAS)} regras de alerta", "",
              "_Gerado automaticamente de `vigia/regras.py`. Não edite à mão._", "",
              "Cada regra procura um padrão conhecido e faz uma **pergunta** à prefeitura. Nenhuma prova "
              "irregularidade sozinha. Os limites de R01–R20 estão em `config.toml`; os de R21–R27, em "
              "`vigia/alertas/portal.py`.", ""]
    for codigo, r in REGRAS.items():
        partes += [f"## {codigo} — {r['nome']}", "", f"**Pergunta:** {r['pergunta']}", "", r["porque"], "",
                   f"**Base legal:** {r['base_legal']}", "", "**Como verificar:**", ""]
        partes += [f"- {v}" for v in r["verificar"]]
        partes += ["", f"**Pode ser legítimo se:** {'; '.join(r['legitimas'])}.", ""]
    return "\n".join(partes)
