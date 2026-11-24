"""Mais consultas do Portal da Transparência de Cariacica: emendas, obras, diárias e receitas.

Mesma API do coletor principal (transparencia.py, https://wstransparencia.cariacica.es.gov.br/Help),
com as mesmas peças: download que guarda o arquivo cru (SHA-256 no manifesto), texto em windows-1252,
leitor de campos fixos, regra de quais anos baixar e checagem antes de gravar (vigia/qualidade.py).
Saída em data/transparencia/.

    Emendas parlamentares   emendas/anos e emendas/csv?exercicio=AAAA                    emendas_AAAA.csv
    Obras                   obras/anos e obras/csv?exercicio=AAAA                        obras_AAAA.csv
    Diárias de servidores   diarias/anos e diarias/csv?unidadeGestoraId=U&exercicio=AAAA diarias_AAAA.csv
    Receitas                receitas/csv?unidadeGestoraId=U&exercicio=AAAA               receitas_AAAA.csv
                            (e uma linha por dia de coleta em receita_acompanhamento.csv)

Defeitos da fonte conhecidos (07/11/2026). Viram aviso em docs/qualidade.md, porque são prova de que
a prefeitura precisa corrigir; nunca derrubam o resto da coleta nem apagam arquivo bom:
- emendas/anos traz 2031 e 2027 (datas de validade digitadas como ano) e não traz 2025 nem 2026;
  emendas/csv?exercicio=2025 (e 2026) responde HTTP 500 {"Message":"An error has occurred."}.
  Por isso o ano corrente e o anterior são consultados sempre, estejam ou não na lista.
- emendas: a descrição (último campo) às vezes tem quebra de linha FORA de aspas, e um leitor de CSV
  comum cria registros fantasmas. Aqui os registros são separados pelo formato do começo da linha.
- obras: ano sem obra responde só "Nome / sem dados". Isso não é uma tabela vazia válida: o arquivo
  anterior, se existir, fica como está.
- receitas: valores acumulados no ano, sem mês.

Diárias (LGPD): nome e CPF de quem recebeu nunca são gravados. A coluna IdBeneficiario é um
pseudônimo calculado com o segredo VIGIA_SAL_PSEUDONIMO; sem o segredo, fica vazia.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import io
import logging
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .. import armazem, qualidade
from ..http import sessao
from ..texto import nome_pessoa, so_digitos
from . import transparencia
from .transparencia import UNIDADES, _baixar_texto, _campos_fixos, _gravar_se_valido, anos_para_baixar, decimal_br

log = logging.getLogger("vigia.portal_extra")
FONTE = "transparencia"     # mesmo portal: as checagens aparecem junto com as do coletor principal


# ---------------------------------------------------------------- peças comuns

def _pasta() -> Path:
    return transparencia.PASTA          # lida na hora: os testes apontam para uma pasta temporária


def _sessao(tentativas: int = 6) -> requests.Session:
    """Sessão de vigia.http, mas o erro final volta como resposta (vira aviso com o código HTTP).
    Emendas usam poucas tentativas: o HTTP 500 de 2025/2026 é permanente e não pode prender a
    coleta por minutos todo dia."""
    s = sessao()
    s.headers["Accept"] = "*/*"
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=tentativas, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"], respect_retry_after_header=True, raise_on_status=False)))
    return s


def avisar(arquivo: str, regra: str, detalhe: str, fonte: str = FONTE) -> None:
    """Defeito da fonte (ou segredo faltando): aparece em docs/qualidade.md sem deixar a execução vermelha.
    ("|" quebraria a tabela do relatório.)"""
    qualidade.REGISTRO.add(qualidade.Checagem(fonte, arquivo, regra, False, False, detalhe.replace("|", "/")))


def _mantido(arquivo: str) -> str:
    return "arquivo anterior mantido" if (_pasta() / arquivo).exists() else "nada gravado"


def resumo_erro(e: Exception) -> str:
    r = getattr(e, "response", None)
    if r is None:
        return f"{type(e).__name__}: {str(e)[:150]}"
    corpo = re.sub(r"\s+", " ", r.text or "").strip()[:120]
    return f"HTTP {r.status_code}" + (f" {corpo}" if corpo else "")


def resposta_sem_dados(texto: str) -> bool:
    """A API responde "Nome" + "sem dados" (ou só o cabeçalho) quando o ano não tem registro."""
    linhas = [l.strip() for l in texto.lstrip("\ufeff").splitlines() if l.strip()]
    return len(linhas) <= 1 or (len(linhas) == 2 and linhas[1].lower() == "sem dados")


def anos_da_lista(s, rota: str) -> list[int]:
    """GET {rota}/anos -> [{"Valor": 2024, "Nome": 2024}, ...]"""
    r = s.get(f"{transparencia.BASE}/{rota}/anos", timeout=60)
    r.raise_for_status()
    anos = set()
    for item in r.json():
        try:
            anos.add(int(item["Valor"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(anos)


def gravar_checado(df: pd.DataFrame, caminho: Path, *, fonte: str, obrigatorias: dict, coluna_total,
                   ano: int | None = None, fechado: bool = False, ordenar: list[str] | None = None,
                   brutos: list[str] | None = None) -> bool:
    """A mesma checagem de transparencia._gravar_se_valido (colunas, formato e comparação com a versão
    anterior: falhou, fica o arquivo anterior), para quando a pasta ou a noção de "ano fechado" é outra.
    coluna_total: nome da coluna somada na comparação, ou função tabela -> valores (soma de colunas)."""
    antigo = armazem.ler(caminho)
    novo_c, antigo_c, coluna = df, antigo, coluna_total
    if callable(coluna_total):
        coluna = "_total_checagem"
        novo_c = df.assign(**{coluna: coluna_total(df)})
        antigo_c = antigo.assign(**{coluna: coluna_total(antigo)}) if not antigo.empty else antigo
    chs = qualidade.validar_tabela(novo_c, antigo_c, fonte=fonte, arquivo=caminho.name, obrigatorias=obrigatorias,
                                   coluna_total=coluna, ano=ano, ano_fechado=fechado, brutos=brutos)
    if not qualidade.aprovado(chs):
        log.error("%s NÃO gravado: falhou na checagem; mantida a versão anterior", caminho.name)
        return False
    armazem.gravar(df, caminho, ordenar=ordenar)
    return True


def _por_ano(anos, tarefa, nome: str) -> None:
    """Um ano com erro não impede os outros. No fim, a fonte termina com erro (execução vermelha), como
    as demais fontes, e o motivo de cada ano aparece em docs/qualidade.md."""
    erros = []
    for ano in anos:
        try:
            tarefa(ano)
        except Exception as e:  # noqa: BLE001
            log.exception("%s %s falhou", nome, ano)
            avisar(f"{nome}_{ano}.csv", "erro_na_fonte", f"{resumo_erro(e)}; {_mantido(f'{nome}_{ano}.csv')}")
            erros.append(str(ano))
    if erros:
        raise RuntimeError(f"{nome}: falha em {', '.join(erros)} (detalhes em docs/qualidade.md)")


def _ler_csv(texto: str) -> pd.DataFrame:
    """CSV bem formado do portal (campo com vírgula vem entre aspas). Formato quebrado levanta erro."""
    df = pd.read_csv(io.StringIO(texto.lstrip("\ufeff")), dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return df


def ler_csv_livre_no_fim(texto: str, inicio_registro: str) -> pd.DataFrame:
    """CSV cujo ÚLTIMO campo é texto livre, com vírgulas, aspas soltas e quebras de linha (até fora de
    aspas). É a variante de transparencia.ler_csv_malformado para quando o texto livre vem no fim, e não
    no penúltimo campo: os registros são separados pelo formato do começo da linha (inicio_registro) e
    os campos fixos são lidos da esquerda pelo mesmo leitor (_campos_fixos)."""
    texto = texto.lstrip("\ufeff").strip()
    cabecalho, _, corpo = texto.partition("\n")
    colunas = [c.strip() for c in cabecalho.strip().split(",")]
    n_fixos = len(colunas) - 1
    linhas = []
    for reg in (re.split(rf"\r?\n(?={inicio_registro})", corpo) if corpo.strip() else []):
        fixos, resto = _campos_fixos(reg, n_fixos)
        livre = resto.strip()
        if len(livre) >= 2 and livre[0] == '"' and livre[-1] == '"':
            livre = livre[1:-1].replace('""', '"')
        linhas.append(fixos + [""] * (n_fixos - len(fixos)) + [livre])
    df = pd.DataFrame(linhas, columns=colunas)
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return df


# ---------------------------------------------------------------- emendas parlamentares

COLUNAS_EMENDAS = ["numero", "partido", "sigla", "Parlamentar", "data", "destino", "beneficiario",
                   "valor", "Situacao", "descricao"]
_CAMPO = r'(?:"[^"\r\n]*"|[^,"\r\n]*)'          # campo simples, com ou sem aspas
_REAIS = r'(?:R\$\s*)?-?\d[\d.]*(?:,\d+)?'
# Começo de registro: 7 campos simples e depois o valor em reais. A descrição é o último campo.
INICIO_EMENDA = rf'(?:{_CAMPO},){{7}}(?:"\s*{_REAIS}\s*"|{_REAIS}),'
OBRIGATORIAS_EMENDAS = {"valor": r"-?\d+\.\d{2}"}


def valor_reais(texto) -> str:
    """'R$ 486.104,00' -> '486104.00'. Sem centavos, '1.051.985' -> '1051985.00'."""
    t = re.sub(r"R\$\s*", "", str(texto or "")).strip()
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", t):     # só separador de milhar
        t = t.replace(".", "")
    return decimal_br(t)


def ler_emendas(texto: str) -> pd.DataFrame:
    df = ler_csv_livre_no_fim(texto, INICIO_EMENDA)
    if list(df.columns) != COLUNAS_EMENDAS:
        raise ValueError(f"emendas: colunas diferentes das conhecidas ({list(df.columns)}); o leitor precisa ser revisto")
    df["valor"] = df["valor"].map(valor_reais)
    return df


def conferir_contagem_emendas(texto: str, df: pd.DataFrame, arquivo: str) -> None:
    """Conferência independente do leitor: cada emenda tem um valor em reais entre aspas. Se o arquivo
    tem mais valores assim do que emendas lidas, uma emenda pode ter grudado na anterior."""
    valores = len(re.findall(r',"R\$\s*-?[\d.]+,\d{2}",', texto))
    if valores > len(df):
        avisar(arquivo, "conferencia_de_registros",
               f"o arquivo tem {valores} valores em reais e o leitor achou {len(df)} emendas; conferir o arquivo cru")


def coletar_emendas(hoje: date | None = None, s=None) -> None:
    """Todos os anos da lista da prefeitura, mais o ano corrente e o anterior (a lista falha)."""
    hoje = hoje or date.today()
    s = s or _sessao(tentativas=2)
    lista = anos_da_lista(s, "emendas")
    sempre = {hoje.year, hoje.year - 1}
    fora = sorted(sempre - set(lista))
    if fora:
        avisar("emendas/anos", "ano_fora_da_lista",
               f"a lista de anos da prefeitura não traz {', '.join(map(str, fora))}; consultado(s) mesmo assim")
    gravados = 0
    for ano in sorted(set(lista) | sempre):
        arquivo = f"emendas_{ano}.csv"
        if ano > hoje.year:
            avisar(arquivo, "ano_no_futuro",
                   f"a prefeitura lista emendas no exercício {ano} (provavelmente data de validade digitada como ano)")
        try:
            texto = _baixar_texto(s, "emendas/csv", {"exercicio": ano}, arquivo)
        except (requests.RequestException, ValueError) as e:
            log.warning("emendas %s: %s", ano, resumo_erro(e))
            avisar(arquivo, "erro_na_fonte", f"emendas/csv?exercicio={ano} respondeu {resumo_erro(e)}; "
                                              f"a prefeitura precisa corrigir; {_mantido(arquivo)}")
            continue
        if resposta_sem_dados(texto):
            avisar(arquivo, "sem_dados", f"a prefeitura respondeu 'sem dados' para {ano}; {_mantido(arquivo)}")
            continue
        df = ler_emendas(texto)
        conferir_contagem_emendas(texto, df, arquivo)
        if gravar_checado(df, _pasta() / arquivo, fonte=FONTE, obrigatorias=OBRIGATORIAS_EMENDAS,
                          coluna_total="valor", ano=ano, ordenar=["data", "numero"], brutos=[arquivo]):
            gravados += 1
            log.info("emendas %s: %d emendas, R$ %.1f mi", ano, len(df),
                     pd.to_numeric(df["valor"], errors="coerce").sum() / 1e6)
    if not gravados:
        raise RuntimeError("emendas: nenhum ano respondeu com dados (detalhes em docs/qualidade.md)")


# ---------------------------------------------------------------- obras

OBRIGATORIAS_OBRAS = {"Id": r"\d+", "Nome": r".+"}
VALORES_OBRAS = ("ValorContratado", "ValorPago", "ValorEmpenhado", "ValorLiquidado")
_UM_CONTRATO = re.compile(r"\s*(\d+/\d{4})\s*-\s*(.+?)\s*")


def separar_contrato(texto) -> tuple[str, str]:
    """'083/2023 - EXATA CONSTRUTORA LTDA' -> ('083/2023', 'EXATA CONSTRUTORA LTDA'). Com mais de um
    contrato no campo, ou formato desconhecido, não separa (a coluna original sempre fica)."""
    texto = str(texto or "")
    if len(re.findall(r"\d+/\d{4}\s*-", texto)) != 1:
        return "", ""
    m = _UM_CONTRATO.fullmatch(texto)
    return (m.group(1), m.group(2)) if m else ("", "")


def ler_obras(texto: str) -> pd.DataFrame:
    df = _ler_csv(texto)
    for col in VALORES_OBRAS:
        if col in df.columns:
            df[col] = df[col].map(decimal_br)
    if "Contratos" in df.columns:
        partes = [separar_contrato(c) for c in df["Contratos"]]
        pos = list(df.columns).index("Contratos") + 1
        df.insert(pos, "NumeroContrato", [p[0] for p in partes])
        df.insert(pos + 1, "Empresa", [p[1] for p in partes])
    return df


def coletar_obras(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    s = s or _sessao()
    anos = sorted(set(anos_da_lista(s, "obras")) | {hoje.year, hoje.year - 1})

    def um_ano(ano: int) -> None:
        arquivo = f"obras_{ano}.csv"
        texto = _baixar_texto(s, "obras/csv", {"exercicio": ano}, arquivo)
        if resposta_sem_dados(texto):
            avisar(arquivo, "sem_dados", f"a prefeitura respondeu 'sem dados' para as obras de {ano}; {_mantido(arquivo)}")
            return
        df = ler_obras(texto)
        if gravar_checado(df, _pasta() / arquivo, fonte=FONTE, obrigatorias=OBRIGATORIAS_OBRAS,
                          coluna_total="ValorContratado", ano=ano, ordenar=["Id"], brutos=[arquivo]):
            log.info("obras %s: %d obras", ano, len(df))

    _por_ano(anos, um_ano, "obras")


# ---------------------------------------------------------------- diárias

SEGREDO_PSEUDONIMO = "VIGIA_SAL_PSEUDONIMO"
PESSOAIS_DIARIAS = ("CPFCNPJ", "Beneficiario")          # nunca vão para o git
VALORES_DIARIAS = ("ValorEmpenhado", "ValorLiquidacoes", "ValorPago")
OBRIGATORIAS_DIARIAS = {"Ano": r"\d{4}", "Data": r"\d{2}/\d{2}/\d{4}.*", "ValorEmpenhado": r"-?\d+\.\d{2}"}


def _cpf_visivel(doc) -> str:
    """Parte do CPF que a prefeitura já mostra (****60.007** -> 60007). Se um dia o CPF vier inteiro,
    usa os mesmos 5 dígitos, e o pseudônimo não muda."""
    d = so_digitos(doc)
    return d[4:9] if len(d) == 11 else d


def pseudonimo(doc, nome, sal: str) -> str:
    """Identificador estável de quem recebeu, sem nome nem CPF: HMAC-SHA256 com o segredo, sobre
    "parte visível do CPF|nome normalizado", 10 primeiros caracteres hexadecimais. Sem o segredo não há
    como ligar o identificador à pessoa. Sem segredo configurado, devolve vazio (nunca um sal fixo)."""
    if not sal:
        return ""
    msg = f"{_cpf_visivel(doc)}|{nome_pessoa(nome)}".encode("utf-8")
    return hmac.new(sal.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:10]


def ler_diarias(texto: str, sal: str = "") -> pd.DataFrame:
    df = _ler_csv(texto)
    for col in VALORES_DIARIAS:
        if col in df.columns:
            df[col] = df[col].map(decimal_br)
    vazio = pd.Series("", index=df.index)
    ids = [pseudonimo(d, n, sal) for d, n in zip(df.get("CPFCNPJ", vazio), df.get("Beneficiario", vazio))]
    pos = list(df.columns).index("CPFCNPJ") if "CPFCNPJ" in df.columns else len(df.columns)
    df = df.drop(columns=[c for c in PESSOAIS_DIARIAS if c in df.columns])
    df.insert(min(pos, len(df.columns)), "IdBeneficiario", ids)
    return df


def _tem_pseudonimos(caminho: Path) -> bool:
    df = armazem.ler(caminho)
    return "IdBeneficiario" in df.columns and bool((df["IdBeneficiario"].astype(str).str.strip() != "").any())


def coletar_diarias(hoje: date | None = None, s=None) -> None:
    """Anos da lista da prefeitura desde 2019, pela regra de transparencia.anos_para_baixar (ano fechado
    só é baixado de novo na revisão mensal); o ano corrente e o anterior, sempre."""
    hoje = hoje or date.today()
    s = s or _sessao()
    sal = os.environ.get(SEGREDO_PSEUDONIMO, "").strip()
    if not sal:
        avisar("diarias", "pseudonimo_sem_segredo", f"segredo {SEGREDO_PSEUDONIMO} ausente: a coluna IdBeneficiario "
                                                    "fica vazia (nome e CPF nunca são gravados)")
    lista = set(anos_da_lista(s, "diarias"))
    anos = [a for a in anos_para_baixar("diarias", hoje) if a in lista or a >= hoje.year - 1]

    def um_ano(ano: int) -> None:
        arquivo = f"diarias_{ano}.csv"
        partes, brutos = [], []
        for ug in UNIDADES:
            bruto = f"diarias_{ano}_ug{ug}.csv"
            texto = _baixar_texto(s, "diarias/csv", {"unidadeGestoraId": ug, "exercicio": ano}, bruto)
            brutos.append(bruto)
            if not resposta_sem_dados(texto):
                partes.append(ler_diarias(texto, sal))
        if not partes:
            avisar(arquivo, "sem_dados", f"a prefeitura respondeu 'sem dados' para as diárias de {ano} em todas as "
                                         f"unidades; {_mantido(arquivo)}")
            return
        if not sal and _tem_pseudonimos(_pasta() / arquivo):
            avisar(arquivo, "pseudonimo_sem_segredo", "sem o segredo, o arquivo anterior (com IdBeneficiario) foi mantido")
            return
        df = pd.concat(partes, ignore_index=True)
        if _gravar_se_valido(df, arquivo, obrigatorias=OBRIGATORIAS_DIARIAS, coluna_total="ValorEmpenhado",
                             ano=ano, hoje=hoje, ordenar=["Data", "Processo"], brutos=brutos):
            log.info("diárias %s: %d registros", ano, len(df))

    _por_ano(anos, um_ano, "diarias")


# ---------------------------------------------------------------- receitas

VALORES_RECEITAS = ("ValorPrevisto", "ValorLancado", "ValorRealizado")
OBRIGATORIAS_RECEITAS = {"Numero": r"\d+", "ValorPrevisto": r"-?\d+\.\d{2}", "ValorRealizado": r"-?\d+\.\d{2}"}
# Grupos do topo: código de 10 dígitos terminado em 9 zeros (1000000000 receitas correntes,
# 2000000000 de capital, 7/8 intraorçamentárias, 9 deduções, quando houver).
CODIGO_TOPO = r"\d0{9}"
ACOMPANHAMENTO = "receita_acompanhamento.csv"
CHAVE_ACOMPANHAMENTO = ["data_coleta", "ano", "unidade", "codigo"]


def ler_receitas(texto: str) -> pd.DataFrame:
    df = _ler_csv(texto)
    for col in VALORES_RECEITAS:
        if col in df.columns:
            df[col] = df[col].map(decimal_br)
    return df


def linhas_acompanhamento(receitas: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """Termômetro grosseiro da arrecadação: realizado x previsto proporcional ao dia do ano, para os
    grupos do topo. NÃO é o cálculo legal de excesso de arrecadação (Lei 4.320/1964, art. 43, § 3º: mês
    a mês e por fonte de recurso); serve para o histórico do git mostrar a evolução e conferir quando
    a prefeitura alega excesso para abrir crédito suplementar."""
    if receitas.empty:
        return pd.DataFrame(columns=CHAVE_ACOMPANHAMENTO)
    df = receitas[receitas["Numero"].astype(str).str.fullmatch(CODIGO_TOPO)]
    fracao = hoje.timetuple().tm_yday / (366 if calendar.isleap(hoje.year) else 365)
    previsto = pd.to_numeric(df["ValorPrevisto"], errors="coerce").fillna(0.0)
    realizado = pd.to_numeric(df["ValorRealizado"], errors="coerce").fillna(0.0)
    esperado = previsto * fracao
    dinheiro = "{:.2f}".format
    return pd.DataFrame({
        "data_coleta": hoje.isoformat(), "ano": str(hoje.year), "unidade": df["UnidadeGestora"],
        "codigo": df["Numero"], "nome": df["Nome"], "previsto": previsto.map(dinheiro),
        "realizado": realizado.map(dinheiro), "fracao_do_ano": f"{fracao:.4f}",
        "esperado_pro_rata": esperado.map(dinheiro), "diferenca": (realizado - esperado).map(dinheiro),
    })


def registrar_acompanhamento(receitas: pd.DataFrame, hoje: date) -> None:
    """Uma linha por dia de coleta, unidade e grupo. Rodar duas vezes no mesmo dia substitui a linha do
    dia (não duplica)."""
    novo = linhas_acompanhamento(receitas, hoje)
    if novo.empty:
        return
    caminho = _pasta() / ACOMPANHAMENTO
    armazem.gravar(armazem.juntar(armazem.ler(caminho), novo), caminho, chave=CHAVE_ACOMPANHAMENTO,
                   ordenar=CHAVE_ACOMPANHAMENTO)
    log.info("acompanhamento da receita: %d grupos em %s", len(novo), hoje.isoformat())


def coletar_receitas(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    s = s or _sessao()

    def um_ano(ano: int) -> None:
        arquivo = f"receitas_{ano}.csv"
        partes, brutos = [], []
        for ug, nome in UNIDADES.items():
            bruto = f"receitas_{ano}_ug{ug}.csv"
            texto = _baixar_texto(s, "receitas/csv", {"unidadeGestoraId": ug, "exercicio": ano}, bruto)
            brutos.append(bruto)
            if not resposta_sem_dados(texto):
                partes.append(ler_receitas(texto).assign(UnidadeGestora=nome))
        if not partes:
            avisar(arquivo, "sem_dados", f"a prefeitura respondeu 'sem dados' para as receitas de {ano} em todas as "
                                         f"unidades; {_mantido(arquivo)}")
            return
        df = pd.concat(partes, ignore_index=True)
        if not _gravar_se_valido(df, arquivo, obrigatorias=OBRIGATORIAS_RECEITAS, coluna_total="ValorRealizado",
                                 ano=ano, hoje=hoje, ordenar=["UnidadeGestora", "Numero"], brutos=brutos):
            return
        log.info("receitas %s: %d linhas", ano, len(df))
        if ano == hoje.year:
            registrar_acompanhamento(df, hoje)

    _por_ano(anos_para_baixar("receitas", hoje), um_ano, "receitas")
