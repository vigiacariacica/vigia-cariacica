"""Os maiores problemas de Cariacica, para a página /problemas/.

Escolhidos pelo filtro do diagnóstico (estudo interno de 12/11/2026): muita gente
atingida, dano grave e o quanto a prefeitura pode resolver. Os números fixos vêm da conferência de 09/11/2026
(conferência dos números de 12/11/2026); fila, esgoto e contratos de emergência saem dos CSVs do robô e se
atualizam sozinhos. Para cada problema: o número, o que melhorou, o outro lado, as perguntas do Vigia (com prazo e
resposta, puxadas do registro de pedidos) e o que a pessoa pode fazer.

Regra: fato com fonte, sem culpar governo nenhum. "O que já fizemos" nunca diz que o Vigia consertou algo:
quem conserta é a prefeitura; o placar de resultados mostra o que mudou de verdade.
"""
from __future__ import annotations

import pandas as pd

from ..config import DADOS
from . import dados as D


def _anos_meses(dias: int) -> str:
    """Vai depois de "mais de": arredonda para baixo (512 dias = 16,8 meses = "1 ano e 4 meses"; arredondar para
    cima dava "mais de 1 ano e 5 meses", que é falso, 24/11/2026)."""
    m = int(dias / 30.44)
    a, r = divmod(m, 12)
    if a == 0:
        return f"{m} meses"
    return f"{a} ano" + ("s" if a > 1 else "") + (f" e {r} meses" if r > 1 else " e 1 mês" if r == 1 else "")


def _emergencias() -> dict[int, tuple[int, float]]:
    out = {}
    for ano in (2024, 2025, 2026):
        f = DADOS / "transparencia" / f"emergenciais_{ano}.csv"
        if f.exists():
            d = pd.read_csv(f, dtype=str, keep_default_na=False)
            out[ano] = (len(d), pd.to_numeric(d["ValorTotal"], errors="coerce").sum())
    return out


CAT_PROBLEMA = {"fila": "saude", "bebes": "saude", "esgoto": "saneamento", "morros": "moradia", "escola": "educacao",
                "violencia": "seguranca", "emergencias": "dinheiro", "dinheiro": "dinheiro"}


def problemas(fl: dict, cid: dict, pad: dict) -> list[dict]:
    r = pd.read_csv(DADOS / "fila" / "fila_resumo_mensal.csv")
    primeiro, ultimo = r.iloc[0], r[r["mes"] == fl["mes"]].iloc[0]
    neuro_ped, neuro_med = int(ultimo["neuro_pediatria_pedidos"]), int(ultimo["neuro_pediatria_mediana_dias"])
    em = _emergencias()
    ult_ano = max(em) if em else 2026
    mi = D.reais_cheio   # com todos os zeros
    sem_rede = cid["sem_rede"]

    return [
        {
            "resumo": f"{D.br(fl['pedidos'])} consultas e exames esperam vaga.",
            "slug": "fila", "titulo": "A fila da saúde",
            "numero": D.br(fl["pedidos"]),
            "legenda": "consultas e exames com especialista esperam vaga.",
            "texto": [
                f"Metade espera há {D.meses(fl['mediana'])}. Esperam há mais de 1 ano: {D.br(fl['ano'])}.",
                f"Crianças e adolescentes esperam neurologista: {D.br(neuro_ped)} pedidos. "
                f"Metade espera há mais de {_anos_meses(neuro_med)}.",
                f"A fila cresceu: eram {D.br(int(primeiro['pedidos']))} pedidos em maio e "
                f"{D.br(fl['pedidos'])} em {fl['mes_texto'].split(' de ')[0]}. Parte é exame novo na lista.",
                "Na Câmara, um projeto para mostrar o tempo de espera foi apresentado em junho de 2022. "
                "Está parado nas comissões desde julho de 2022.",
            ],
            "melhorou": "",
            "outro_lado": "A Secretaria de Saúde diz que a fila vai pela gravidade de cada caso. "
                          "E quem marca a consulta é o governo do Estado.",
            "fontes": [("Planilha da fila, Secretaria de Saúde de Cariacica",
                        "https://cariacica.es.gov.br/pagina/ler/951/semus-fila-de-espera-para-agendamento-de-consultas-e-exames"),
                       ("Nota Técnica 02/2026 da Saúde",
                        "https://docs.google.com/document/d/1QOnNc7PCWg3V6dTCrj-2m18CD_ZMuA1c/edit"),
                       ("Projeto de Lei 80/2022 na Câmara",
                        "https://cariacica.camarasempapel.com.br/spl/consulta-producao.aspx?termo=transpar%C3%AAncia%20na%20divulga%C3%A7%C3%A3o")],
            "perguntas": ["008949.2026-38", "009043.2026-22"],
            "link": ("/fila/", "Veja a fila do seu posto"),
            "acoes": [("Espera há mais de 1 ano?", "Reclame na Ouvidoria da Saúde: 162 (prefeitura) ou 136 (Disque Saúde).")],
        },
        {
            "resumo": "Quase 16 de cada 1.000 bebês morreram antes de 1 ano.",
            "slug": "bebes", "titulo": "Bebês e grávidas",
            "numero": "Quase 16",
            "legenda": "de cada 1.000 bebês nascidos em 2024 morreram antes de fazer 1 ano.",
            "texto": [
                "Em Vitória, foram quase 11 de cada 1.000.",
                # sífilis: o número único do projeto é o do DataSUS/SINAN (124, preliminar), não o do Plano Municipal
                # (131, outra base); e é caso de sífilis congênita, nunca "nasceram" (24/11/2026)
                "Em 2024, foram 124 casos de sífilis congênita, passada da mãe para o bebê na gravidez "
                "(DataSUS, dado preliminar). O teste e o remédio são de graça no SUS.",
                "Muitas dessas mortes podem ser evitadas com pré-natal bem feito no posto.",
            ],
            "melhorou": "Em 2025, o número ainda preliminar foi de quase 14 de cada 1.000. "
                        "É menos que em 2024, mas mais que de 2020 a 2023.",
            "selo_melhorou": ("Em 2025", "neutro"),
            "outro_lado": "",
            "fontes": [("DataSUS, mortes de bebês (SIM)", "http://tabnet.datasus.gov.br/cgi/deftohtm.exe?sim/cnv/inf10es.def"),
                       ("DataSUS, nascimentos (SINASC)", "http://tabnet.datasus.gov.br/cgi/deftohtm.exe?sinasc/cnv/nves.def"),
                       ("DataSUS, sífilis congênita (SINAN, dado preliminar de 2024)",
                        "https://datasus.saude.gov.br/acesso-a-informacao/doencas-e-agravos-de-notificacao-de-2007-em-diante-sinan/")],
            "perguntas": ["008925.2026-07", "008926.2026-77", "008936.2026-98"],
            "link": None,
            "acoes": [("Está grávida?", "Comece o pré-natal no posto logo no começo. É de graça."),
                      ("Faça o teste de sífilis no posto.", "O remédio também é de graça.")],
        },
        {
            "resumo": f"{D.br(sem_rede)} casas fora da rede de esgoto.",
            "slug": "esgoto", "titulo": "Esgoto",
            "numero": D.br(sem_rede),
            "legenda": "casas não têm esgoto ligado na rede.",
            "texto": [
                f"Nos {pad['n_renda_baixa']} bairros de menor renda, {D.de_cada(100 - pad['esgoto_renda_baixa'])} casas "
                "estão fora da rede.",
                "Pelo dado nacional do saneamento, em 2024 só cerca de 4 de cada 10 moradores tinham coleta de esgoto. "
                "O Censo mostra mais casas \"na rede\" porque conta também o cano de chuva.",
                # "Em 2021, a Justiça mandou resolver o esgoto" saiu: não achamos a decisão para pôr o link (24/11/2026)
            ],
            "melhorou": "Em janeiro de 2026, o governo do Estado inaugurou a estação de esgoto de Flexal e ampliou a de "
                        "Bandeirantes. O governo diz que a cobertura chegou a 80%.",
            "outro_lado": "",
            "fontes": [("IBGE, Censo 2022 por bairro", "https://www.ibge.gov.br/estatisticas/sociais/trabalho/22827-censo-demografico-2022.html"),
                       ("Ranking do saneamento 2026 (dados de 2024)",
                        "https://www.parana.pr.gov.br/sites/default/arquivos_restritos/files/documento/2026-06/ranking2026_v1_0.pdf"),
                       ("Governo do ES, estações de 2026",
                        "https://www.es.gov.br/Noticia/cariacica-alcanca-80-de-cobertura-em-esgotamento-sanitario-com-novas-estacoes-de-tratamento")],
            "perguntas": ["2026111046", "008929.2026-93"],
            "link": ("/bairros/", "Veja o esgoto do seu bairro"),
            "acoes": [("Esgoto vazando ou a céu aberto?", "Ligue para a Cesan: 115. A ligação é grátis.")],
        },
        {
            "resumo": "Mais de 25 mil pessoas em área de risco.",
            "slug": "morros", "titulo": "Morros com risco de deslizar",
            "numero": "Mais de 25 mil",
            "legenda": "pessoas moram em áreas de risco alto ou muito alto de deslizamento, enxurrada ou inundação.",
            "texto": [
                "São 92 áreas mapeadas pelo Serviço Geológico do Brasil em 2023: 48 de risco alto e 44 de risco muito alto.",
                "Em dia de chuva forte, quem mora ali precisa saber a hora de sair de casa.",
            ],
            "melhorou": "",
            "outro_lado": "",
            "fontes": [("Serviço Geológico do Brasil",
                        "https://www.sgb.gov.br/w/mais-de-25-mil-pessoas-vivem-em-areas-de-risco-geologico-em-cariacica-no-espirito-santo")],
            "perguntas": ["008923.2026-61", "008948.2026-65"],
            "link": None,
            "acoes": [("Receba o alerta de chuva no celular:", "mande o seu CEP por SMS para 40199. É de graça."),
                      ("Rachadura na parede ou no chão?", "Ligue para a Defesa Civil: 199.")],
        },
        {
            "resumo": "Mais de 1 de cada 3 crianças terminou o 2º ano sem ler.",
            "slug": "escola", "titulo": "Aprender a ler e creche",
            # MEC, Indicador Criança Alfabetizada 2024: 64,57% alfabetizadas (35,4% não)
            "numero": "Mais de 1 de cada 3",
            "legenda": "crianças das escolas públicas terminou o 2º ano sem saber ler e escrever. Dado de 2024.",
            "texto": [
                # INEP Sinopse 2025 (matrículas em creche) ÷ IBGE Censo 2022 (crianças de 0 a 3 anos): 24,3%
                "Só cerca de 1 de cada 4 crianças de 0 a 3 anos está matriculada em creche.",
                "Sem creche, muitas mães não conseguem trabalhar.",
            ],
            "melhorou": "Está melhorando: em 2023, eram mais de 4 de cada 10 crianças sem saber ler no fim do 2º ano.",
            "outro_lado": "",
            "fontes": [("MEC, Indicador Criança Alfabetizada 2024, Espírito Santo (Cariacica: 64,57)",
                        "https://www.gov.br/mec/pt-br/crianca-alfabetizada/monitoramento-e-avaliacao/es_ica2024.pdf"),
                       ("MEC, alfabetização de 2023 (A Tribuna)", "https://tribunaonline.com.br/_/268056"),
                       ("Creche: INEP, Sinopse Estatística da Educação Básica 2025, e IBGE, Censo 2022 (24,3%)",
                        "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/sinopses-estatisticas/educacao-basica"),
                       ("Lei 14.685/2023, fila da creche pública",
                        "https://www.camara.leg.br/noticias/1000169-lei-determina-divulgacao-obrigatoria-de-lista-de-espera-por-vaga-em-escolas-e-creches/")],
            "perguntas": ["008950.2026-11", "008935.2026-28", "008924.2026-34"],
            "link": ("/bairros/", "Veja as escolas do seu bairro"),
            "acoes": [("Precisa de creche?", "Peça a vaga e peça, por escrito, a sua posição na fila. A lei manda mostrar essa fila.")],
        },
        {
            # 24/11/2026: saiu a taxa de 2024 ("28 por 100 mil, a maior da Grande Vitória"): estava sem link e sem o
            # recorte (o Fórum só calcula cidades com mais de 100 mil moradores), e não achamos a tabela municipal
            # oficial de 2025. Saiu também "Quem mais morre são os jovens", sem fonte. Fica o número do governo do ES.
            "resumo": "52 assassinatos de janeiro a 4 de agosto de 2025.",
            "slug": "violencia", "titulo": "Violência",
            "numero": "52",
            "legenda": "homicídios e feminicídios em Cariacica de 1º de janeiro a 4 de agosto de 2025.",
            "texto": ["É o número do governo do Estado. Ainda não achamos o total oficial de 2025 inteiro."],
            "melhorou": "Está caindo: no mesmo período de 2024, foram 66. São 21 de cada 100 a menos.",
            "outro_lado": "",
            "fontes": [("Governo do ES, notícia de 05/08/2025 (Secretaria de Segurança)",
                        "https://www.es.gov.br/Noticia/cariacica-completa-30-dias-consecutivos-sem-registros-de-assassinatos")],
            "perguntas": ["2026111048", "008932.2026-12"],
            "link": None,
            "acoes": [("Em perigo?", "Ligue 190."),
                      ("Quer avisar a polícia sem dizer o seu nome?", "Ligue para o Disque-Denúncia: 181.")],
        },
        {
            "resumo": f"{mi(em[ult_ano][1])} em contratos sem concorrência em {ult_ano}." if em else "",
            "slug": "emergencias", "titulo": "Contratos sem concorrência",
            "numero": mi(em[ult_ano][1]) if em else "",
            "legenda": f"em contratos de emergência assinados em {ult_ano} (valor total de cada um). "
                       "Emergência é contrato feito sem concorrência.",
            "texto": [
                (f"Em 2024 foram {mi(em[2024][1])}. Em 2025, {mi(em[2025][1])}." if 2024 in em and 2025 in em else ""),
                "Sem concorrência, ninguém sabe se aquele era o melhor preço.",
                "Quatro das cinco maiores concorrências desde 2024 foram feitas numa sala, e não pela internet. "
                "O desconto foi menor. Isso não prova nada, mas merece pergunta.",
            ],
            "melhorou": "",
            "outro_lado": "Emergência é permitida pela lei quando há urgência de verdade, e dura até 1 ano. "
                          "Perguntamos à prefeitura o motivo de cada uma.",
            "fontes": [("Portal da Transparência de Cariacica, contratos de emergência",
                        "https://transparencia.cariacica.es.gov.br/"),
                       ("Portal Nacional de Contratações Públicas", "https://pncp.gov.br/app/editais?q=cariacica")],
            "perguntas": ["008833.2026-66", "008944.2026-76", "009023.2026-77", "009037.2026-87", "009040.2026-06",
                          "009048.2026-81"],
            "link": ("/dinheiro/", "Veja para onde vai o dinheiro"),
            "acoes": [("Fale com o seu vereador.", "A Câmara aprova o orçamento e pode chamar o secretário para explicar.")],
        },
        {
            "resumo": "R$ 122 de IPTU por morador, pouco mais da metade da Serra.",
            "slug": "dinheiro", "titulo": "Pouco dinheiro próprio",
            "numero": "R$ 122",
            "legenda": "de IPTU por morador em 2025. Na Serra, foram R$ 234.",
            "texto": [
                "O IPTU e os outros impostos da cidade rendem pouco. "
                "Com pouco dinheiro próprio, a cidade depende mais do dinheiro do Estado e da União.",
                "A prefeitura gastou R$ 649 por morador com saúde em 2025, o menor valor da Grande Vitória.",
            ],
            "melhorou": "",
            "outro_lado": "",
            "fontes": [("Tesouro Nacional, impostos de 2025",
                        "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2025&no_anexo=DCA-Anexo%20I-C&id_ente=3201308"),
                       ("Tesouro Nacional, gastos de 2025",
                        "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2025&no_anexo=DCA-Anexo%20I-E&id_ente=3201308")],
            "perguntas": ["008843.2026-87", "008842.2026-17", "008937.2026-71"],
            "link": ("/dinheiro/", "Veja para onde vai o dinheiro"),
            "acoes": [("Confira o carnê do IPTU.", "Se a sua casa estiver errada no cadastro, peça a correção na prefeitura.")],
        },
    ]
