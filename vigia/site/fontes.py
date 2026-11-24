"""A página "Nossas fontes": de onde vem cada número do site, como fazemos a conta, quando atualiza e o
limite de cada dado. Ao criar uma página nova no site, acrescente a parte dela aqui."""
from __future__ import annotations

PRINCIPIOS = [
    ("Só dado oficial.", "Vem da prefeitura, da Câmara, do Governo do ES, do Governo Federal, do IBGE e do "
                         "Tribunal de Contas."),
    ("Um robô faz as contas.", "É um programa que baixa os dados e refaz as contas sozinho. Quando um dado é "
                               "copiado à mão, a página avisa."),
    ("Toda página diz a fonte.", "Fica no pé da página, com link para o dado original."),
    ("Dado com limite, a gente avisa.", "Se falta um pedaço, ou se o dado é antigo, está escrito."),
    ("Errou, corrigiu.", "Se você achar um erro, fale com a gente. Corrigimos e dizemos o que mudou."),
    ("Nada de dado pessoal.", "Sem nome de servidor, sem CPF e sem dizer quem está na fila."),
]

PALAVRAS = [
    ("De cada 10", "A porcentagem dita do jeito que se fala. 72% vira 7 de cada 10."),
    ("Metade espera há", "O meio da fila. Metade das pessoas espera menos que isso. A outra metade espera mais."),
    ("Por morador", "O total dividido pelo número de moradores. Serve para comparar cidades de tamanhos diferentes."),
    ("Valor pago", "O dinheiro que já saiu da conta da prefeitura para quem fez o serviço."),
    ("Valor liquidado", "Quando a prefeitura confere que recebeu o que comprou. Depois vem o pagamento."),
    ("Situação no sistema", "O que a prefeitura escreveu no sistema dela. Pode estar atrasado. Por isso a gente pergunta."),
    ("Lei de Acesso à Informação", "A lei que manda o governo responder qualquer pessoa em até 20 dias."),
    ("Licitação", "Concorrência para escolher quem faz o serviço pelo melhor preço."),
    ("Contrato de emergência", "Contrato feito às pressas, sem concorrência, por causa de uma urgência. Dura até 1 ano."),
    ("Aditivo", "Mudança no contrato depois de assinado: mais prazo, mais dinheiro ou mais serviço."),
    ("Tribunal de Contas", "O órgão que confere as contas do Estado e das prefeituras do Espírito Santo."),
]

PARTES = [
    {
        "id": "bairros", "titulo": "Meu bairro", "link": "/bairros/",
        "o_que": "Esgoto, água, lixo, leitura e renda de cada bairro. E os postos, as escolas e as obras do bairro.",
        "fontes": [
            ("IBGE, Censo 2022, resultados por bairro",
             "https://www.ibge.gov.br/estatisticas/sociais/trabalho/22827-censo-demografico-2022.html",
             "casas, moradores, esgoto, água, lixo, leitura e renda"),
            ("Ministério da Saúde, cadastro de estabelecimentos de saúde (CNES)",
             "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos?codigo_municipio=320130&codigo_tipo_unidade=2",
             "endereço e bairro de cada posto"),
            ("Governo do ES, dados abertos, mapa das escolas", "https://dados.es.gov.br/",
             "endereço e bairro de cada escola"),
            ("MEC, Ideb por escola", "https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb",
             "nota de cada escola"),
            ("Portal da Transparência de Cariacica, sistema de obras", "https://transparencia.cariacica.es.gov.br/",
             "obras, bairros, valor pago e situação"),
        ],
        "como": [
            "Comparamos cada bairro com a cidade inteira.",
            "Bairro com menos de 100 casas não entra na lista dos piores. Com poucas casas, o número muda muito.",
            "A obra que passa por mais de um bairro aparece em todos eles, com o valor da obra inteira.",
        ],
        "atualiza": "O Censo é de 2022 e só muda no próximo. Postos e escolas, toda segunda. Obras, todo dia.",
        "limites": [
            "O Censo junta alguns bairros pequenos com o vizinho.",
            "O sistema de obras tem poucas obras de 2025 e nenhuma de 2026.",
            "Obra sem bairro no sistema não aparece em nenhum bairro. Ela entra na conta da cidade.",
        ],
    },
    {
        "id": "mapa", "titulo": "Mapa", "link": "/mapa/",
        "o_que": "Onde mora a gente: moradores, aperto, casas sem esgoto e renda de cada bairro, no mapa.",
        "fontes": [
            ("IBGE, Censo 2022, resultados por bairro",
             "https://www.ibge.gov.br/estatisticas/sociais/trabalho/22827-censo-demografico-2022.html",
             "moradores, casas, esgoto e renda"),
            ("IBGE, malha de bairros do Censo 2022",
             "https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/26565-malhasde-setores-censitarios-divisoes-intramunicipais.html",
             "o desenho de cada bairro e a área em km²"),
        ],
        "como": [
            "O robô baixa o desenho dos bairros do IBGE e desenha o mapa. Não usa mapa de outra empresa.",
            "Cada cor junta cerca de 20 bairros: a mais clara tem os 20 com menos, a mais escura os 20 com mais.",
            "Moradores por km² é o número de moradores dividido pela área do bairro.",
        ],
        "atualiza": "O Censo é de 2022 e só muda no próximo.",
        "limites": [
            "A área sem bairro no Censo, quase toda zona rural, fica cinza.",
            "Bairro grande com pouca gente parece vazio, mesmo tendo muitas casas espalhadas.",
        ],
    },
    {
        "id": "obras", "titulo": "Obras no bairro", "link": "/bairros/",
        "o_que": "Cada obra que a prefeitura registrou com o nome do bairro, quanto já pagou e em que pé está.",
        "fontes": [
            ("Portal da Transparência de Cariacica, sistema de obras, um arquivo por ano desde 2010",
             "https://transparencia.cariacica.es.gov.br/", "nome, bairros, valor do contrato, valor pago e situação"),
        ],
        "como": [
            "Lemos o campo de bairros de cada obra e ligamos ao nome do bairro no Censo.",
            "A situação é copiada do sistema e trocada por palavras simples. Pronta e entregue, por exemplo.",
            "Quando a obra está em andamento e o prazo do contrato já passou, a gente avisa.",
        ],
        "atualiza": "Todo dia, junto com o resto do Portal da Transparência.",
        "limites": [
            "Só aparece a obra que a prefeitura registrou no sistema de obras.",
            "Obra paga como serviço comum, sem registro no sistema de obras, fica de fora.",
            "Serviço da cidade toda, como tapa-buraco, não entra em nenhum bairro. Fica na lista da cidade.",
            "A situação é a que a prefeitura escreveu. Pode estar atrasada.",
        ],
    },
    {
        "id": "fila", "titulo": "Fila da saúde", "link": "/fila/",
        "o_que": "Quantas consultas e exames com especialista esperam vaga em cada posto, e há quanto tempo.",
        "fontes": [
            ("Secretaria de Saúde de Cariacica, fila de espera de consultas e exames",
             "https://cariacica.es.gov.br/pagina/ler/951/semus-fila-de-espera-para-agendamento-de-consultas-e-exames",
             "um pedido por linha, com o posto e a data do pedido"),
        ],
        "como": [
            "Contamos os pedidos de cada posto.",
            "Metade espera há: o meio da fila, em dias, virado em meses.",
            "Não usamos nome nem nada que mostre quem está na fila.",
        ],
        "atualiza": "O robô olha todo dia. A prefeitura publica uma planilha por mês.",
        "limites": [
            "A mesma pessoa pode ter mais de um pedido.",
            "Se a prefeitura atrasa a planilha, o site mostra o último mês publicado.",
        ],
    },
    {
        "id": "vereadores", "titulo": "Vereadores", "link": "/vereadores/",
        "o_que": "Os projetos de lei e os pedidos de cada um dos 19 vereadores. E a conta do salário e do gasto da Câmara.",
        "fontes": [
            ("Câmara Municipal de Cariacica, sistema de projetos, consulta por autor",
             "https://cariacica.camarasempapel.com.br/consulta-producao.aspx", "projetos, resumos, situação e pedidos"),
            ("Portal da Transparência da Câmara", "https://transparenciacmc.cariacica.es.gov.br/Despesa.Secretaria.aspx",
             "gasto da Câmara por ano e salário na folha"),
            ("Leis municipais 6.410/2022 e 6.865/2026", "https://cariacica.camarasempapel.com.br/",
             "limite de gasto de cada gabinete"),
        ],
        "como": [
            "Contamos os projetos de lei de cada vereador desde janeiro de 2025.",
            "Lemos o resumo oficial de cada um e separamos por impacto: muda algo, muda pouco, simbólico ou pode ser barrado.",
            "A conta da Câmara divide o gasto total pelas leis aprovadas.",
            "Não dividimos o salário de cada vereador pelas leis dele. Mais projetos não quer dizer mais trabalho bom.",
        ],
        "atualiza": "A Câmara bloqueia o robô. Por enquanto, copiamos os dados pelo navegador, uma vez por mês.",
        "limites": [
            "A separação por impacto é nossa e pode ter erro. Cada projeto tem link para você conferir.",
            "Ainda não mostramos votos e presença. Já perguntamos à Câmara.",
        ],
    },
    {
        "id": "dinheiro", "titulo": "Dinheiro", "link": "/dinheiro/",
        "o_que": "Quanto a prefeitura gastou no ano, em quê, e quanto isso dá por morador.",
        "fontes": [
            ("Tribunal de Contas do ES, dados abertos, despesas dos municípios",
             "https://dados.es.gov.br/dataset/despesas-municipios", "gasto da prefeitura por área"),
            ("Tesouro Nacional, contas anuais dos municípios (Siconfi)", "https://siconfi.tesouro.gov.br/",
             "gasto com saúde de Cariacica e das cidades vizinhas"),
            ("IBGE, estimativa de população", "https://www.ibge.gov.br/cidades-e-estados/es/cariacica.html",
             "número de moradores"),
        ],
        "como": [
            "Usamos o gasto que a prefeitura já conferiu que recebeu.",
            "Dividimos pelo número de moradores e por 12 meses.",
        ],
        "atualiza": "Uma vez por ano, quando as contas do ano fecham.",
        "limites": ["É a média da cidade. Não diz quanto chega a cada bairro."],
    },
    {
        "id": "problemas", "titulo": "Maiores problemas", "link": "/problemas/",
        "o_que": "Os problemas que atingem mais gente em Cariacica, com o número de cada um e o que já perguntamos.",
        "fontes": [
            ("Ministério da Saúde, DataSUS, mortes de bebês e nascimentos", "http://tabnet.datasus.gov.br/",
             "mortes de bebês"),
            ("Serviço Geológico do Brasil, áreas de risco", "https://www.sgb.gov.br/", "moradores em área de risco"),
            ("Portal da Transparência de Cariacica, contratos de emergência", "https://transparencia.cariacica.es.gov.br/",
             "contratos sem concorrência"),
            ("Tesouro Nacional (Siconfi)", "https://siconfi.tesouro.gov.br/", "dinheiro próprio da cidade"),
        ],
        "como": [
            "Escolhemos os problemas que atingem mais gente, fazem mais estrago e a cidade pode resolver.",
            "Fila, esgoto e contratos de emergência se atualizam sozinhos.",
            "Os outros números conferimos na fonte em novembro de 2026.",
        ],
        "atualiza": "Fila, esgoto e contratos, sozinhos. O resto, quando sai dado novo.",
        "limites": ["Alguns números vêm de reportagem que cita o dado oficial. Nesses casos, dizemos o jornal."],
    },
    {
        "id": "perguntas", "titulo": "Perguntas", "link": "/perguntas/",
        "o_que": "As perguntas oficiais que fizemos à prefeitura, à Câmara e ao Governo do ES, com prazo e resposta.",
        "fontes": [
            ("Sistemas de pedido de informação da prefeitura, da Câmara e do Governo do ES, e a Ouvidoria", "", ""),
            ("Lei de Acesso à Informação, Lei 12.527/2011", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm",
             "prazo de resposta"),
        ],
        "como": [
            "Cada pergunta tem o número oficial do pedido e o prazo da lei: 20 dias, ou 30 na Ouvidoria.",
            "Quando a resposta chega, mostramos o que disseram.",
        ],
        "atualiza": "Quando mandamos uma pergunta nova ou chega uma resposta.",
        "limites": ["Prazo que cai no fim de semana passa para a segunda-feira."],
    },
]
