"""Coletor do Portal da Transparência da Prefeitura de Cariacica.

Fonte oficial: https://wstransparencia.cariacica.es.gov.br/Help (API pública,
mesma base do portal https://transparencia.cariacica.es.gov.br).

É a fonte mais detalhada que temos: cada pagamento feito pela prefeitura,
com CNPJ do fornecedor, processo, contrato, área e descrição. Também traz
os contratos com valor original e aditivos, os contratos emergenciais e os
fornecedores punidos pela própria prefeitura.

Cuidados conhecidos (descobertos em nov/2026):
- Os CSVs vêm em windows-1252, não UTF-8.
- O CSV de despesas é malformado: descrições têm aspas soltas e quebras de
  linha. Um leitor de CSV comum junta milhares de linhas numa só. Por isso
  cada registro é separado pelo início "AAAA," seguido de 6 campos numéricos, e as colunas fixas
  são lidas da esquerda; a descrição é tudo o que sobra antes do último campo.
- CPFs de pessoas físicas vêm mascarados (****47.207**) no campo do fornecedor, mas aparecem
  inteiros em nomes de MEI e em descrições. Por isso: pagamento a pessoa física sai sem nome e sem
  descrição (proteger_pessoa_fisica) e todo CSV passa por vigia.texto.mascarar_cpfs ao ser gravado.
"""
from __future__ import annotations

import io
import csv
import logging
import re
from datetime import date

import pandas as pd

import os

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao

log = logging.getLogger("vigia.transparencia")
BASE = "https://wstransparencia.cariacica.es.gov.br/api"
PASTA = DADOS / "transparencia"
ANO_INICIAL = 2019          # dois anos antes da gestão atual, para comparação
ANOS_ATUALIZADOS = 2        # ano corrente e anterior são baixados de novo todo dia

# Unidades gestoras visíveis no portal (api/UnidadesGestoras)
UNIDADES = {6: "PREFEITURA", 3: "IPC PREVIDENCIA", 26: "INSTITUTO DE DESENVOLVIMENTO"}

COLUNAS_PAGAMENTO = [
    "Ano", "Data", "IdEmpenho", "NumeroEmpenho", "ValorEmpenhado", "ValorLiquidado", "ValorPago",
    "CpfCnpjFornecedor", "NomeFornecedor", "CodOrgao", "Orgao", "CodUnidadeGestora", "UnidadeGestora",
    "CodFuncao", "Funcao", "CodSubFuncao", "SubFuncao", "CodPrograma", "Programa", "CodAcao", "Acao",
    "CodFonte", "Fonte", "CodNaturezaDespesa", "NaturezaDespesa", "NumeroProcesso", "NumeroContrato",
    "Licitacao", "Descricao",
]
# Início de registro. Exigir os campos numéricos logo depois do ano evita confundir com um
# texto da descrição que, depois de uma quebra de linha, comece com "2023, ..." (aconteceu em 2023).
_NUM = r'(?:"-?[\d.,]*"|-?[\d.,]*)'
INICIO_DESPESA = rf"\d{{4}}(?:,{_NUM}){{6}},"
INICIO_CONTRATO = rf"[^,\r\n]{{1,20}},\d{{4}},[^,\r\n]*,[^,\r\n]*,\d{{0,4}},{_NUM},"

# Formato que todo registro precisa ter para ser aceito (ver vigia/qualidade.py)
CNPJ_OU_CPF = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|[\d*]{3}\.?[\d*]{3}\.?[\d*]{3}-?[\d*]{2}|\*{4}[\d.]+\*{2}"
OBRIGATORIAS_PAGAMENTO = {
    "IdEmpenho": r"\d+",
    "Data": r"\d{2}/\d{2}/\d{4}.*",
    "ValorEmpenhado": r"-?\d+\.\d{2}",
    "CpfCnpjFornecedor": CNPJ_OU_CPF,
}
OBRIGATORIAS_CONTRATO = {
    "NumeroContrato": r".+",
    "AnoContrato": r"\d{4}",
    "ValorContratado": r"-?\d+\.\d{2}",
}

VALORES = {"ValorOrcado", "ValorAutorizado", "ValorReservado", "ValorEmpenhado", "ValorLiquidado",
           "ValorPago", "ValorContratado", "Aditivo", "ValorTotal", "Valor"}


def decimal_br(texto: str) -> str:
    """'21165,44' -> '21165.44'. Só remove pontos de milhar quando há vírgula decimal."""
    t = (texto or "").strip()
    if not t or t == "-":
        return ""
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return f"{float(t):.2f}"
    except ValueError:
        return ""


def _campos_fixos(registro: str, n_fixos: int) -> tuple[list[str], str]:
    """Lê n_fixos campos respeitando aspas; devolve os campos e o resto da linha."""
    campos, atual, aspas, i = [], [], False, 0
    while i < len(registro) and len(campos) < n_fixos:
        c = registro[i]
        if aspas:
            if c == '"':
                if i + 1 < len(registro) and registro[i + 1] == '"':
                    atual.append('"')
                    i += 1
                else:
                    aspas = False
            else:
                atual.append(c)
        elif c == '"':
            aspas = True
        elif c == ",":
            campos.append("".join(atual))
            atual = []
        else:
            atual.append(c)
        i += 1
    return campos, registro[i:]


def ler_csv_malformado(texto: str, inicio_registro: str) -> pd.DataFrame:
    """Lê CSV cujo penúltimo campo (texto livre) pode ter aspas e quebras de linha soltas.

    inicio_registro: regex que marca o começo de cada registro no início da linha.
    """
    registros = re.split(rf"\r?\n(?={inicio_registro})", texto.lstrip("﻿").strip())
    if not registros or not registros[0]:
        return pd.DataFrame()
    cabecalho = registros[0].strip().split(",")
    n_fixos = len(cabecalho) - 2
    linhas = []
    for reg in registros[1:]:
        fixos, resto = _campos_fixos(reg, n_fixos)
        corte = resto.rfind(",")
        livre, ultimo = (resto[:corte], resto[corte + 1:]) if corte >= 0 else (resto, "")
        livre = livre.strip()
        if len(livre) >= 2 and livre[0] == '"' and livre[-1] == '"':
            livre = livre[1:-1].replace('""', '"')
        linha = fixos + [""] * (n_fixos - len(fixos)) + [livre, ultimo.strip()]
        linhas.append(linha)
    df = pd.DataFrame(linhas, columns=cabecalho)
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        if col in VALORES:
            df[col] = df[col].map(decimal_br)
    return df


def _baixar_texto(s, caminho: str, params: dict, nome_bruto: str) -> str:
    r = s.get(f"{BASE}/{caminho}", params=params, timeout=300)
    r.raise_for_status()
    if "html" in r.headers.get("Content-Type", "").lower():
        raise ValueError(f"{caminho} devolveu HTML em vez de CSV (página de erro?)")
    qualidade.guardar_bruto(nome_bruto, r.content, r.url)
    return r.content.decode("windows-1252", errors="replace")


def revisao_completa(hoje: date) -> bool:
    """Uma vez por mês (dia 1) ou quando pedido, baixa também os anos fechados,
    para detectar dado antigo alterado pela prefeitura."""
    return hoje.day == 1 or os.environ.get("VIGIA_COMPLETO") == "1"


def anos_para_baixar(prefixo: str, hoje: date) -> list[int]:
    """Anos fechados que já temos não são baixados de novo (salvo na revisão mensal); os recentes, sim."""
    completo = revisao_completa(hoje)
    anos = []
    for ano in range(ANO_INICIAL, hoje.year + 1):
        recente = ano > hoje.year - ANOS_ATUALIZADOS
        if recente or completo or not (PASTA / f"{prefixo}_{ano}.csv").exists():
            anos.append(ano)
    return anos


def proteger_pessoa_fisica(df: pd.DataFrame) -> pd.DataFrame:
    """Pagamento a pessoa física (CPF mascarado pela prefeitura) sai sem nome e sem descrição.
    Entre esses pagamentos há pensão alimentícia, família acolhedora, restituições e indenizações:
    republicar nomes no git seria expor pessoas. Valor, data, área, programa e natureza ficam."""
    if df.empty or "CpfCnpjFornecedor" not in df.columns:
        return df
    pf = ~df["CpfCnpjFornecedor"].astype(str).str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}") \
        & (df["CpfCnpjFornecedor"].astype(str).str.strip() != "")
    df = df.copy()
    df.loc[pf, "NomeFornecedor"] = "PESSOA FÍSICA"
    ei = ~pf & df["NomeFornecedor"].astype(str).map(dono_no_nome)   # empresa individual com CPF ou CNPJ do dono no nome
    df.loc[ei, "NomeFornecedor"] = "EMPRESA INDIVIDUAL (nome do titular omitido)"
    if "Descricao" in df.columns:
        comuns = vocabulario(df["Descricao"])
        df["Descricao"] = df["Descricao"].astype(str).map(lambda t: descricao_publica(t, comuns))
        df.loc[pf, "Descricao"] = "(omitida: pagamento a pessoa física)"
    return df


# Segunda camada (24/11/2026): depois de tirar os nomes que dá para achar, a descrição que ainda cita pessoa
# (paciente, menor, corpo, indenização, servidor... seguido de nome próprio, ou um CPF) sai inteira. O texto
# completo continua no portal, no empenho; o valor, a data, o órgão e a natureza ficam.
DESCRICAO_OMITIDA = "(descrição omitida: cita pessoa física; o texto completo está no empenho, no portal)"
_CITA_PESSOA = re.compile(r"(?i)\b(pacientes?|menor(?:es)?|crian[cç]as?|adolescentes?|alun[oa]s?|estudantes?|"
                          r"mun[ií]cipes?|corpo|[oó]bito|falecid[oa]s?|funer|sepult|indeniza|ressarc|restitui|"
                          r"pensionista|pens[aã]o|senten[cç]a|servidor|servidora|cedid[oa]s?|cess[aã]o|sra?\b|"
                          r"senhora?|representante|procurador[a]?|benefici[aá]ri[oa]s?|requerente|autora?\b|"
                          r"exequente|favor\s+d[eoa]s?\b|herdeir|vi[uú]v[oa]|inventari|matr[ií]cula|mat\b|ocupante|"
                          r"respons[aá]vel|interessad[oa]|titular|patronais?|jeton|conselheir|membros?\b|"
                          r"honor[aá]rios|\bdra?\b\.?|advogad|passage|diferen[cç]a|impetrad|\bserv\b|"
                          r"conv[eê]nio[^-–]{0,25}\d+/\d{2,4}\s*[-–]|"   # "CONVÊNIO 9016/2020 - NOME" (cessão)
                          r"possuidor[a]?|c[oô]njuge|em\s+nome\s+d[eoa]s?|propriedade\s+d[eoa]s?|propriet[aá]ri[oa])")
_CPF_NO_TEXTO = re.compile(r"\*{2,}[.\d\s]*\d{3}[.\d\s-]*\*{0,3}|\b\d{3}\.\d{3}\.\d{3}[\s.\-–]?\d{2}\b|(?i:\bcpf\b\W{0,5}\d)")
# Siglas curtas que aparecem nas descrições (o resto das palavras curtas em maiúsculas pode ser nome: ANA, REIS)
_SIGLAS = set("""IPC INSS FGTS ARP SEME SERP RC SC MUN EPP ALIQ ME CMEI CEAP TEC EXEC OS PE CARD CIM OSC LE EMEF EDP ML
    MG UP AR PERP CAC ADRA KIT PNAE APAE GBR SUS RS CAR CRAS SUAS PNAB FNDE VANT PA DC TV RPV DUA TI STFC IPTU LEG
    ESP MED PMC PVC ISS CEF PABX MEC IP RPPS IPVV SMP COOP MF MD CIEE PMAT VIX UI SEDU SA SERV PC WEB MMV RGM RRT PG
    AFC SEI GRU NEO SMAR LL WP VX EPI LED ETA CELK CM CO MUNI XXG ACES DEA CNPJ CPF UBS UPA SAMU CEI ATA REF LTDA
    NF NFE NFS DOM DIO DOE CTPS PIS PASEP IRRF IR ICMS INPC IPCA SELIC TJES TCE MPC MPES PM PMES GOV SEGER SESA SESP
    II III IV VI VII VIII IX XI XII XIII XIV XV XVI XVII XVIII XIX XX MEI ART FLS LEI CIA ONG ECA EJA CRAS CREAS
    CAPS CAPSI CEO LTDA SPE TFD OSS IEMA""".split())
_EMPRESA = set("""LTDA EIRELI EIRELLI EPP S.A S/A CIA COMÉRCIO COMERCIO INDÚSTRIA INDUSTRIA CONSTRUÇÕES CONSTRUTORA
    SERVIÇOS SERVICOS ENGENHARIA DISTRIBUIDORA ADMINISTRADORA ASSOCIAÇÃO ASSOCIACAO INSTITUTO FUNDAÇÃO FUNDACAO
    COOPERATIVA BANCO EDITORA LOCAÇÃO LOCACAO TRANSPORTES SOLUÇÕES SOLUCOES TECNOLOGIA CONSULTORIA ASSESSORIA
    PRODUÇÕES PRODUCOES EVENTOS HOSPITAL CLÍNICA CLINICA LABORATÓRIO LABORATORIO FARMÁCIA FARMACIA EMPRESA
    MÉDICOS MEDICOS IGREJA PARÓQUIA PAROQUIA CENTRO ESCOLA COLÉGIO COLEGIO FACULDADE UNIVERSIDADE""".split())
_SEQ_MAIUSCULA = re.compile(r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+(?:\s+(?:(?:[Dd][AEOaeo][Ss]?|[Ee])\s+)?[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+)+")
_MATRICULA_QUALQUER = re.compile(r"(?i)\b(matr[ií]cula|mat)\b\.?\s*(?:n[º°o.]*)?\s*[:º°.\-]?\s*\d[\d.\-/]*")


def _sem_acento(p: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", p.upper()) if unicodedata.category(c) != "Mn")


def vocabulario(textos) -> frozenset:
    """Palavras que aparecem em minúsculas nas descrições (deste ano e dos anos já gravados): são palavras comuns,
    não nomes. Comparadas sem acento ("DECIMO" = "décimo")."""
    comuns = set()
    fontes = [textos] + [pd.read_csv(p, dtype=str, keep_default_na=False, usecols=["Descricao"])["Descricao"]
                         for p in sorted(PASTA.glob("pagamentos_*.csv")) if p.stat().st_size > 0]
    for serie in fontes:
        for t in serie:
            for w in re.findall(r"\b[a-zà-ÿ]{3,}\b", str(t)):
                comuns.add(_sem_acento(w))
    return frozenset(comuns)


def _sigla(w: str) -> bool:
    return w.isupper() and len(w) <= 4 and (w in _SIGLAS or not re.search(r"[AEIOUÁÉÍÓÚÂÊÔÃÕY]", w))


def cita_pessoa(texto: str, comuns: frozenset = frozenset()) -> bool:
    if not texto:
        return False
    if _CPF_NO_TEXTO.search(texto):
        return True
    if not _CITA_PESSOA.search(texto):
        return False
    for m in _SEQ_MAIUSCULA.finditer(texto):
        palavras = [w.strip(".,;:()") for w in m.group().split() if w.upper() not in _CONECTOR]
        if any(w.upper() in _EMPRESA for w in palavras):       # razão social de empresa, não nome de gente
            continue
        raras = [w for w in palavras if _sem_acento(w) not in comuns and w.upper() not in _NAO_E_NOME
                 and w.upper() not in _LIGA_FRASE and not _sigla(w)]
        if len(palavras) >= 2 and len(raras) >= 1:
            return True
    return False


def objeto_publico(texto: str, comuns: frozenset = frozenset()) -> str:
    """Objeto de contrato: em vez de sumir com o texto (que diz o que foi contratado), tira só o trecho com cara de
    nome de pessoa quando há palavra que anuncia pessoa ("Sr.", "servidor", "paciente"...), e qualquer CPF."""
    if not texto:
        return texto
    t = _MATRICULA_QUALQUER.sub(lambda m: m.group(1) + " (omitida)", _CPF_NO_TEXTO.sub("(CPF omitido)", texto))
    if not _CITA_PESSOA.search(t):
        return t

    def e_nome(seq: str) -> bool:
        palavras = [w.strip(".,;:()") for w in seq.split() if w.upper() not in _CONECTOR]
        # rua, hospital, órgão, cargo, evento ou empresa: não é nome de gente ("Nossa Senhora da Penha",
        # "Procuradoria Geral do Município", "menor taxa de administração")
        if len(palavras) < 2 or any(w.upper() in _EMPRESA or w.upper() in _NAO_E_NOME for w in palavras):
            return False
        return any(_sem_acento(w) not in comuns and w.upper() not in _LIGA_FRASE and not _sigla(w) for w in palavras)

    def troca(m):
        antes = t[max(0, m.start() - 25):m.start()].upper()
        if re.search(r"\b(RUA|AV|AVENIDA|PRAÇA|PRACA|HOSPITAL|ESCOLA|EMEF|CMEI|UBS|UNIDADE|POLICL[IÍ]NICA|NOSSA|INSTITUTO)\W*$", antes):
            return m.group(0)
        partes = re.split(r"(\s*[,;]\s*|\s+e\s+)", m.group(3))      # lista de nomes: "membros: Fulano, Beltrana e Ciclano"
        if not e_nome(partes[0]):
            return m.group(0)
        out = [("(nome omitido)" if (i % 2 == 0 and e_nome(p)) else p) for i, p in enumerate(partes)]
        return m.group(1) + m.group(2) + "".join(out)
    # só o nome que vem logo depois da palavra que anuncia pessoa ("do Sr. FULANO", "servidora: FULANA"),
    # para não apagar bairro, parque ou nome de evento citados no mesmo objeto
    return _APOS_GATILHO.sub(troca, t)


_APOS_GATILHO = re.compile(_CITA_PESSOA.pattern.replace("(?i)", "(?i:", 1) + ")"
                           + r"(\W{0,4}(?:(?i:d[aeo]s?|a|o|ao|aos|à|em|nome|estatut[aá]ri[oa]|efetiv[oa]|cedid[oa])\W{1,4}){0,3})"
                           + "(" + _SEQ_MAIUSCULA.pattern + r"(?:(?:\s*[,;]\s*|\s+e\s+)" + _SEQ_MAIUSCULA.pattern + "){0,10})")


def descricao_publica(texto: str, comuns: frozenset = frozenset()) -> str:
    t = _MATRICULA_QUALQUER.sub(lambda m: m.group(1) + " (omitida)", sem_servidor_na_descricao(texto))
    return DESCRICAO_OMITIDA if cita_pessoa(t.replace("(nome omitido)", ""), comuns) else t


# A descrição do empenho é texto livre da prefeitura e às vezes traz o nome de uma pessoa: servidor cedido,
# pensionista, quem recebe por sentença (24/11/2026). O nome sai depois da palavra que o anuncia; a matrícula sai
# sempre; o resto da descrição (cessão, cargo, órgão, processo) fica.
_GATILHO = (r"(?i:servidor(?:a\b|\s*\(a\)|\b)|servidores?\s+cedid[oa]s?|pensionista|benefici[aá]ri[oa]|"
            r"requerente|exequente|\bautora?\b|em\s+favor\s+de\b|\bsr\.|\bsra\.|\bsenhora?\b)")
_ANTES_DO_NOME = (r"(?:\s*\(a\))?(?:\s*,)?(?:\s+(?i:cedid[oa]|efetiv[oa]|estatut[aá]ri[oa]|comissionad[oa]|"
                  r"aposentad[oa]|municipal|estadual|federal|p[uú]blic[oa]|do\s+quadro|o|a)\b)*\s*[,:\-–]?\s*")
_PALAVRA = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+"
_NOME = rf"({_PALAVRA}(?:\s+(?:(?:[Dd][AEOaeo][Ss]?|[Ee])\s+)?{_PALAVRA}){{1,5}})"
_PESSOA = re.compile(rf"({_GATILHO}{_ANTES_DO_NOME}){_NOME}")
# Palavras de órgão, lugar ou documento: se aparecem, o trecho não é nome de gente e fica como está.
_NAO_E_NOME = set("""MUNICIPIO MUNICÍPIO MUNICIPAL MUNICIPALIDADE PREFEITURA SECRETARIA SECRETÁRIA ESTADO ESTADUAL
    GOVERNO CÂMARA CAMARA FUNDO INSTITUTO TRIBUNAL JUSTIÇA JUSTICA FEDERAL UNIÃO UNIAO CONFORME DOCUMENTAÇÃO
    DOCUMENTACAO PROCESSO LOTADO LOTADA LOTADOS CEDIDO CEDIDA CEDIDOS CEDIDAS PUBLICO PÚBLICO PUBLICA PÚBLICA
    SERVIÇOS SERVICOS SERVIÇO EMPRESA LTDA EIRELI ME EPP SA S.A EDUCAÇÃO EDUCACAO SAÚDE SAUDE ASSISTÊNCIA SOCIAL
    VILA VELHA VITÓRIA VITORIA SERRA VIANA CARIACICA ESPÍRITO ESPIRITO SANTO BRASIL CAIXA BANCO BANESTES ADMINISTRAÇÃO
    ADMINISTRACAO FOLHA PAGAMENTO REFERENTE REF RELATIVO MÊS MES JANEIRO FEVEREIRO MARÇO MARCO ABRIL MAIO JUNHO
    JULHO AGOSTO SETEMBRO OUTUBRO NOVEMBRO DEZEMBRO CONVÊNIO CONVENIO TERMO CONTRATO DESPESA DESPESAS PATRONAIS
    EXERCÍCIO EXERCICIO SEME SEMUS SEMAS SEMOB SEFIN SEGOV IPASV PMC PMVV TITULAR CARGO PROFESSOR PROFESSORA
    ESCOLA UNIDADE CENTRO HOSPITAL DIRETORIA SUPERINTENDÊNCIA DEPARTAMENTO AUTOS QUE NÃO NAO DESTA DESTE
    PROCURADORIA GERAL CONTROLADORIA OUVIDORIA GABINETE PRESIDÊNCIA PRESIDENCIA REPÚBLICA REPUBLICA PRESIDENTE PREFEITO
    PREFEITA VICE VEREADOR VEREADORA DEPUTADO DEPUTADA SENADOR GOVERNADOR GOVERNADORA SECRETÁRIO SECRETARIO PREVIDÊNCIA
    PREVIDENCIA SERVIDORES PÚBLICOS PUBLICOS CONGRESSO SEMINÁRIO SEMINARIO ENCONTRO FÓRUM FORUM NACIONAL BRASILEIRO
    BRASILEIRA CAPIXABA REGIONAL MUNICIPAIS PROCURADORES PROCURADORAS NOSSA SENHORA IGREJA RUA AVENIDA PRAÇA BAIRRO
    TAXA ADMINISTRAÇÃO PREÇO VALOR LOTE ITEM""".split())
_CONECTOR ={"DA", "DE", "DO", "DAS", "DOS", "E"}
_LIGA_FRASE = {"AO", "AOS", "A", "O", "PARA", "PELO", "PELA", "COM", "EM", "NO", "NA", "NOS", "NAS", "POR", "SOB", "ATÉ",
               "ATE", "QUE", "REF", "CPF", "LOTADO", "LOTADA", "NOMEADO", "NOMEADA", "MATRICULA", "MATRÍCULA", "CARGO"}
_MATRICULA = re.compile(r"(?i)(matr[ií]cula\s*(?:n[º°o.]*\s*)?)\d[\d.\-/]*")


def sem_servidor_na_descricao(texto: str) -> str:
    """Nome de pessoa e matrícula fora da descrição (o nome mantido por compatibilidade com quem já importava)."""
    if not texto:
        return texto

    def troca(m):
        # o nome vai até a primeira palavra que não é de nome (órgão, lugar, "para", "ao"...); o resto fica
        g = m.group(2)
        tomadas = []
        for p in g.split():
            if p.strip(".,").upper() in _NAO_E_NOME | _LIGA_FRASE:
                break
            tomadas.append(p)
        while tomadas and tomadas[-1].upper() in _CONECTOR:     # "... DA" no fim não é nome
            tomadas.pop()
        if sum(1 for p in tomadas if p.upper() not in _CONECTOR) < 2:
            return m.group(0)
        fim = 0
        for p in tomadas:
            fim = g.index(p, fim) + len(p)
        return m.group(1) + "(nome omitido)" + g[fim:]
    return _MATRICULA.sub(r"\1(omitida)", _PESSOA.sub(troca, texto))


FISCAL_OMITIDO = "(servidor designado; nome omitido)"
EI_OMITIDA = "EMPRESA INDIVIDUAL (nome do titular omitido)"
_CPF_MASCARADO_NO_NOME = re.compile(r"\*{2,}[\d.\-]{3,11}\*+")
_MEI_NO_NOME = re.compile(r"^\s*\d{2}\.?\d{3}\.?\d{3}\s+\D")


def dono_no_nome(nome: str) -> bool:
    """Razão social de empresário individual/MEI que traz o CPF (mascarado) ou o começo do CNPJ junto do nome do dono."""
    nome = str(nome or "")
    return bool(_CPF_MASCARADO_NO_NOME.search(nome) or _MEI_NO_NOME.match(nome))


def proteger_contratos(df: pd.DataFrame) -> pd.DataFrame:
    """Mesma régua dos pagamentos (24/11/2026, docs/DECISOES.md): contrato com pessoa física (aluguel de imóvel,
    plantão médico) sai sem o nome, e empresa individual cujo nome traz o CPF do dono também; o fiscal do contrato
    é servidor e sai sem o nome. Valor, objeto, datas, secretaria e número do contrato ficam: tudo confere no portal."""
    if df.empty:
        return df
    df = df.copy()
    if {"CPFCNPJ", "Fornecedor"} <= set(df.columns):
        doc = df["CPFCNPJ"].astype(str).str.strip()
        pf = ~doc.str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}") & (doc != "")
        df.loc[pf, "Fornecedor"] = "PESSOA FÍSICA"
        ei = ~pf & df["Fornecedor"].astype(str).map(dono_no_nome)
        df.loc[ei, "Fornecedor"] = EI_OMITIDA
    if "Fiscal" in df.columns:
        df.loc[df["Fiscal"].astype(str).str.strip() != "", "Fiscal"] = FISCAL_OMITIDO
    if "Objeto" in df.columns:
        comuns = vocabulario(df["Objeto"])
        df["Objeto"] = df["Objeto"].astype(str).map(lambda t: objeto_publico(t, comuns))
    return df


def _gravar_se_valido(df: pd.DataFrame, arquivo: str, *, obrigatorias: dict, coluna_total: str,
                      ano: int, hoje: date, ordenar: list[str], brutos: list[str]) -> bool:
    caminho = PASTA / arquivo
    chs = qualidade.validar_tabela(df, armazem.ler(caminho), fonte="transparencia", arquivo=arquivo,
                                   obrigatorias=obrigatorias, coluna_total=coluna_total, ano=ano,
                                   ano_fechado=ano <= hoje.year - ANOS_ATUALIZADOS, brutos=brutos)
    if not qualidade.aprovado(chs):
        log.error("%s NÃO gravado: falhou na checagem; mantida a versão anterior", arquivo)
        return False
    armazem.gravar(df, caminho, ordenar=ordenar)
    return True


def coletar_pagamentos(s, hoje: date):
    for ano in anos_para_baixar("pagamentos", hoje):
        texto = _baixar_texto(s, "despesas/csv", {"exercicio": ano, "tipoDespesa": "P"},
                              f"despesas_{ano}.csv")
        df = ler_csv_malformado(texto, INICIO_DESPESA)
        df = proteger_pessoa_fisica(df[[c for c in COLUNAS_PAGAMENTO if c in df.columns]])
        if not _gravar_se_valido(df, f"pagamentos_{ano}.csv", obrigatorias=OBRIGATORIAS_PAGAMENTO,
                                 coluna_total="ValorEmpenhado", ano=ano, hoje=hoje,
                                 ordenar=["Data", "IdEmpenho"], brutos=[f"despesas_{ano}.csv"]):
            continue
        total = pd.to_numeric(df["ValorPago"], errors="coerce").sum()
        log.info("pagamentos %s: %d empenhos, R$ %.1f mi pagos", ano, len(df), total / 1e6)


def coletar_contratos(s, hoje: date):
    """Contratos e contratos emergenciais de todas as unidades gestoras."""
    for tipo, rota in (("contratos", "contratos/csv"), ("emergenciais", "contratos-emergenciais/csv")):
        for ano in anos_para_baixar(tipo, hoje):
            partes = []
            for ug, nome in UNIDADES.items():
                texto = _baixar_texto(s, rota, {"unidadeGestoraId": ug, "exercicio": ano},
                                      f"{tipo}_{ano}_ug{ug}.csv")
                df = ler_csv_malformado(texto, INICIO_CONTRATO)
                if not df.empty:
                    partes.append(df.assign(UnidadeGestora=nome))
            if partes:
                df = proteger_contratos(pd.concat(partes, ignore_index=True))
                if not _gravar_se_valido(df, f"{tipo}_{ano}.csv", obrigatorias=OBRIGATORIAS_CONTRATO,
                                         coluna_total="ValorTotal", ano=ano, hoje=hoje,
                                         ordenar=["UnidadeGestora", "DataAssinatura"],
                                         brutos=[f"{tipo}_{ano}_ug{ug}.csv" for ug in UNIDADES]):
                    continue
                log.info("%s %s: %d", tipo, ano, len(df))


def coletar_penalizados(s):
    anos = [a["Valor"] for a in s.get(f"{BASE}/fornecedoresPenalizados/anos", timeout=60).json()]
    partes = []
    for ano in anos:
        texto = _baixar_texto(s, "fornecedoresPenalizados/csv", {"Exercicio": ano}, f"penalizados_{ano}.csv")
        df = pd.read_csv(io.StringIO(texto), dtype=str, keep_default_na=False, quoting=csv.QUOTE_MINIMAL)
        partes.append(df.assign(Exercicio=str(ano)))
    if partes:
        df = pd.concat(partes, ignore_index=True)
        armazem.gravar(df, PASTA / "penalizados.csv", chave=list(df.columns), ordenar=["Exercicio", "Fornecedor"])
        log.info("fornecedores penalizados: %d registros", len(df))


def coletar(hoje: date | None = None):
    hoje = hoje or date.today()
    s = sessao()
    s.headers["Accept"] = "*/*"
    coletar_pagamentos(s, hoje)
    coletar_contratos(s, hoje)
    coletar_penalizados(s)
