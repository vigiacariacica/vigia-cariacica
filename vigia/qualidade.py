"""Qualidade dos dados: nada é gravado sem ser checado, e tudo que foi checado fica registrado.

Três camadas:
1. Antes de gravar (portal da prefeitura): esquema, campos obrigatórios e comparação com a
   versão anterior. Se a checagem bloqueante falhar, o arquivo antigo é mantido.
2. Depois de coletar (todas as fontes): nenhum CSV pode perder mais de 2% das linhas em
   relação ao último commit. Se perder, volta para a versão do commit (rede de segurança).
3. Conciliação: o total empenhado no portal tem de bater com o que a prefeitura declarou ao
   Tesouro (Siconfi) no mesmo ano.

Resultado: docs/qualidade.md (legível), data/qualidade/manifesto.csv (de onde veio cada
arquivo, quando e com qual hash) e data/qualidade/alteracoes.csv (dados antigos que a
prefeitura mudou depois de publicados).
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DADOS, DOCS, RAIZ

log = logging.getLogger("vigia.qualidade")
PASTA = DADOS / "qualidade"
BRUTOS = RAIZ / "brutos"          # respostas cruas do dia; vão como artefato do Actions, não para o git

QUEDA_MAX_LINHAS = 0.02           # perder mais que isso de um dia para o outro é suspeito
QUEDA_MAX_TOTAL = 0.02
TOLERANCIA_RETROATIVA = 0.001     # ano fechado que muda mais que 0,1% é registrado
TOLERANCIA_SICONFI = 0.02         # portal x Siconfi; diferença histórica é ~1%
MIN_VALIDOS = 0.999               # campos obrigatórios preenchidos em 99,9% das linhas


@dataclass
class Checagem:
    fonte: str
    arquivo: str
    regra: str
    ok: bool
    bloqueante: bool
    detalhe: str


@dataclass
class Registro:
    checagens: list[Checagem] = field(default_factory=list)
    manifesto: list[dict] = field(default_factory=list)
    alteracoes: list[dict] = field(default_factory=list)
    falhas_fonte: list[str] = field(default_factory=list)
    fora_passageiro: list[str] = field(default_factory=list)   # fonte fora do ar há pouco tempo (sem alarme)
    notas: list[tuple[str, str]] = field(default_factory=list)   # (regra, decisão aplicada) para conferência
    hash_anterior: dict = field(default_factory=dict)
    hash_atual: dict = field(default_factory=dict)
    conciliacao: pd.DataFrame = field(default_factory=pd.DataFrame)

    def add(self, *chs: Checagem):
        for c in chs:
            self.checagens.append(c)
            if not c.ok:
                (log.error if c.bloqueante else log.warning)("[%s] %s: %s", c.arquivo, c.regra, c.detalhe)

    @property
    def bloqueios(self) -> list[Checagem]:
        return [c for c in self.checagens if not c.ok and c.bloqueante]


REGISTRO = Registro()


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def guardar_bruto(nome: str, conteudo: bytes, url: str) -> str:
    """Guarda a resposta crua e devolve o SHA-256 dela (quem baixar o mesmo arquivo no mesmo
    momento obtém o mesmo hash)."""
    BRUTOS.mkdir(parents=True, exist_ok=True)
    (BRUTOS / nome).write_bytes(conteudo)
    sha = hashlib.sha256(conteudo).hexdigest()
    REGISTRO.manifesto.append({"arquivo_bruto": nome, "fonte": url, "baixado_em": agora(),
                               "bytes": len(conteudo), "sha256": sha})
    REGISTRO.hash_anterior[nome] = _ultimo_hash(nome)
    REGISTRO.hash_atual[nome] = sha
    return sha


def registrar_bruto(nome: str, sha: str, tamanho: int, url: str) -> str:
    """Como guardar_bruto, mas só anota o SHA-256 no manifesto, sem guardar o arquivo: para arquivos
    nacionais grandes (ex.: ZIP do TCE-ES com os 78 municípios), que qualquer pessoa baixa de novo na fonte."""
    REGISTRO.manifesto.append({"arquivo_bruto": nome, "fonte": url, "baixado_em": agora(),
                               "bytes": tamanho, "sha256": sha})
    REGISTRO.hash_anterior[nome] = _ultimo_hash(nome)
    REGISTRO.hash_atual[nome] = sha
    return sha


def _ultimo_hash(nome: str) -> str | None:
    m = PASTA / "manifesto.csv"
    if not m.exists():
        return None
    df = pd.read_csv(m, dtype=str, keep_default_na=False)
    df = df[df["arquivo_bruto"] == nome]
    return df.sort_values("baixado_em")["sha256"].iloc[-1] if not df.empty else None


def origem_da_mudanca(brutos: list[str], menos_registros: bool = False) -> str:
    """Se o arquivo cru da prefeitura é idêntico ao da última vez, a mudança veio do nosso leitor;
    se mudou, veio da prefeitura. Sem registro anterior, não dá para afirmar."""
    anteriores = [REGISTRO.hash_anterior.get(b) for b in brutos]
    if not brutos or any(h is None for h in anteriores):
        return "a verificar (sem hash anterior)"
    if all(REGISTRO.hash_atual.get(b) == h for b, h in zip(brutos, anteriores)):
        return "nosso leitor (arquivo da prefeitura idêntico)"
    if menos_registros:
        return "a verificar (arquivo publicado mudou e tem menos registros; conferir antes de afirmar)"
    return "prefeitura (arquivo publicado mudou)"


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def validar_tabela(novo: pd.DataFrame, antigo: pd.DataFrame, *, fonte: str, arquivo: str,
                   obrigatorias: dict[str, str], coluna_total: str, ano: int | None = None,
                   ano_fechado: bool = False, brutos: list[str] | None = None) -> list[Checagem]:
    """obrigatorias: coluna -> regex que todo valor deve cumprir (em 99,9% das linhas)."""
    chs: list[Checagem] = []

    def ch(regra, ok, detalhe, bloqueante=True):
        chs.append(Checagem(fonte, arquivo, regra, bool(ok), bloqueante, detalhe))

    ch("nao_vazio", len(novo) > 0, f"{len(novo)} linhas")
    if novo.empty:
        return chs
    faltando = [c for c in obrigatorias if c not in novo.columns]
    ch("colunas", not faltando, f"faltando: {faltando}" if faltando else "todas presentes")
    if faltando:
        return chs
    for col, padrao in obrigatorias.items():
        validos = novo[col].astype(str).str.fullmatch(padrao).mean()
        ruins = int((~novo[col].astype(str).str.fullmatch(padrao)).sum())
        ch(f"formato_{col}", validos >= MIN_VALIDOS, f"{ruins} linhas fora do padrão ({validos:.4%} ok)")

    if antigo.empty or coluna_total not in antigo.columns:
        ch("comparacao_anterior", True, "primeira coleta deste arquivo", bloqueante=False)
        return chs
    l_ant, l_nov = len(antigo), len(novo)
    t_ant, t_nov = _num(antigo[coluna_total]).sum(), _num(novo[coluna_total]).sum()
    var_l = (l_nov - l_ant) / l_ant if l_ant else 0
    var_t = (t_nov - t_ant) / t_ant if t_ant else 0
    if ano_fechado:
        mudou = abs(var_l) > 0 or abs(var_t) > TOLERANCIA_RETROATIVA
        grande = var_l < -QUEDA_MAX_LINHAS or abs(var_t) > QUEDA_MAX_TOTAL
        aceitar = os.environ.get("VIGIA_ACEITAR_ANO_FECHADO") == "1"
        ch("ano_fechado_inalterado", not mudou,
           f"linhas {l_ant}→{l_nov}, total R$ {_br(t_ant, 2)}→{_br(t_nov, 2)}", bloqueante=False)
        if grande and not aceitar:
            # Pode ser download cortado. Só entra depois de alguém conferir e rodar com
            # VIGIA_ACEITAR_ANO_FECHADO=1 (registrado em docs/DECISOES.md).
            ch("ano_fechado_mudanca_grande", False,
               f"mudança acima de {QUEDA_MAX_TOTAL:.0%} num ano fechado; arquivo novo não gravado até conferência")
            return chs
        if mudou:
            REGISTRO.alteracoes.append({"detectado_em": agora(), "arquivo": arquivo, "ano": ano,
                                        "linhas_antes": l_ant, "linhas_depois": l_nov,
                                        "total_antes": round(t_ant, 2), "total_depois": round(t_nov, 2),
                                        "origem": origem_da_mudanca(brutos or [], menos_registros=l_nov < l_ant)})
    else:
        ch("sem_queda_de_linhas", var_l >= -QUEDA_MAX_LINHAS, f"{l_ant}→{l_nov} ({var_l:+.2%})")
        ch("sem_queda_do_total", var_t >= -QUEDA_MAX_TOTAL, f"R$ {_br(t_ant, 2)}→{_br(t_nov, 2)} ({var_t:+.2%})")
    return chs


def aprovado(chs: list[Checagem]) -> bool:
    REGISTRO.add(*chs)
    return not any(not c.ok and c.bloqueante for c in chs)


# ---------- camada 2: rede de segurança sobre todos os CSVs ----------

def contar_registros(conteudo: bytes) -> int:
    """Registros do CSV (não linhas: um campo entre aspas pode ter quebra de linha)."""
    if not conteudo.strip():
        return 0
    return len(pd.read_csv(io.BytesIO(conteudo), dtype=str, keep_default_na=False))


def _registros_no_commit(caminho: Path) -> int | None:
    rel = caminho.relative_to(RAIZ).as_posix()
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=RAIZ, capture_output=True)
    if r.returncode != 0:
        return None
    return contar_registros(r.stdout)


def guarda_final(ignorar: tuple[str, ...] = ("alertas.csv",)) -> None:
    """Compara cada CSV com o último commit. Queda grande de linhas = restaura o do commit."""
    if not DADOS.resolve().is_relative_to(RAIZ):
        return  # dados fora do repositório (testes): não há commit para comparar
    for caminho in sorted(DADOS.rglob("*.csv")):
        if caminho.name in ignorar or caminho.parent == PASTA or caminho.parent == DADOS / "sonda":
            continue   # data/sonda/ são amostras da sonda de fontes, não dados publicados
        antes = _registros_no_commit(caminho)
        if not antes:
            continue
        depois = contar_registros(caminho.read_bytes())
        queda = (antes - depois) / antes
        rel = caminho.relative_to(RAIZ).as_posix()
        ok = queda <= QUEDA_MAX_LINHAS
        REGISTRO.add(Checagem("todas", rel, "guarda_final", ok, True, f"registros {antes}→{depois}"))
        if not ok:
            subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=RAIZ, check=False)
            log.error("%s restaurado para a versão do último commit", rel)


QUEDA_MAX_ALERTAS = 0.20


def guarda_alertas() -> None:
    """A lista pública não pode perder mais de 20% das linhas de uma vez (banco vazio, regra
    quebrada). Se perder, volta à versão do commit. Mudança de regra intencional: rode com
    VIGIA_ACEITAR_QUEDA_ALERTAS=1 e registre o motivo em docs/DECISOES.md."""
    arq = DADOS / "alertas.csv"
    if not DADOS.resolve().is_relative_to(RAIZ) or not arq.exists():
        return
    antes = _registros_no_commit(arq)
    if not antes:
        return
    depois = contar_registros(arq.read_bytes())
    queda = (antes - depois) / antes
    ok = queda <= QUEDA_MAX_ALERTAS or os.environ.get("VIGIA_ACEITAR_QUEDA_ALERTAS") == "1"
    REGISTRO.add(Checagem("alertas", "data/alertas.csv", "lista_publica_nao_encolhe", ok, True,
                          f"alertas {antes}→{depois}"))
    if not ok:
        restaurar_saidas()


SAIDAS_GERADAS = ("data/alertas.csv", "data/pncp", "data/receita", "docs/relatorio.md", "docs/REGRAS.md")


def restaurar_saidas() -> None:
    """Volta as saídas geradas pela análise para a versão do último commit (nunca publica pela metade)."""
    if not DADOS.resolve().is_relative_to(RAIZ):
        return
    for rel in SAIDAS_GERADAS:
        subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=RAIZ, check=False, capture_output=True)
    log.error("Saídas da análise restauradas para a versão do último commit")


def varrer_cpfs() -> None:
    """LGPD, última barreira: nenhum CPF inteiro em data/ ou docs/. Todo CSV já passa por
    mascarar_cpfs ao ser gravado; se algum arquivo antigo ainda tiver CPF, ele é saneado aqui
    (o registro fica em docs/qualidade.md). Só bloqueia se o saneamento não resolver."""
    from .texto import mascarar_cpfs, tem_cpf
    sujos = []
    for arq in [*DADOS.rglob("*.csv"), *DOCS.rglob("*.md")]:
        texto = arq.read_text(encoding="utf-8", errors="replace")
        if not tem_cpf(texto):
            continue
        if arq.suffix == ".csv" and arq.parent != PASTA:
            df = pd.read_csv(arq, dtype=str, keep_default_na=False)
            for col in df.columns:
                if not col.lower().startswith("valor"):
                    df[col] = df[col].map(mascarar_cpfs)
            df.to_csv(arq, index=False)
        else:
            arq.write_text(mascarar_cpfs(texto), encoding="utf-8")
        if tem_cpf(arq.read_text(encoding="utf-8", errors="replace")):
            sujos.append(arq.name)
        else:
            REGISTRO.add(Checagem("lgpd", arq.name, "cpf_saneado", True, False, "CPF antigo mascarado"))
    REGISTRO.add(Checagem("lgpd", "data/ e docs/", "nenhum_cpf_inteiro", not sujos, True,
                          f"ainda com CPF: {sujos}" if sujos else "nenhum CPF inteiro"))


# ---------- camada 2b: o banco SQLite não pode encolher ----------

TABELAS_BANCO = ("bruto", "orgaos", "contratacoes", "itens", "resultados", "contratos", "termos", "atas",
                 "fornecedores", "socios", "sancoes", "servidores", "alertas")


def checar_banco(con, banco_dir: Path) -> bool:
    """Compara a contagem de cada tabela com a do último commit (data/qualidade/banco.csv).
    Se nenhuma encolheu mais que 2%, grava o novo retrato e cria banco/OK, que autoriza o
    workflow a subir o banco para a release. Banco suspeito nunca substitui o bom."""
    atual = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABELAS_BANCO}
    arq = PASTA / "banco.csv"
    anterior: dict[str, int] = {}
    if DADOS.resolve().is_relative_to(RAIZ):
        rel = arq.relative_to(RAIZ).as_posix()
        r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=RAIZ, capture_output=True)
        if r.returncode == 0 and r.stdout.strip():
            df = pd.read_csv(io.BytesIO(r.stdout), dtype={"tabela": str, "registros": int})
            anterior = dict(zip(df["tabela"], df["registros"]))
    ok = True
    for t, n in atual.items():
        antes = anterior.get(t)
        if antes and n < antes * (1 - QUEDA_MAX_LINHAS):
            ok = False
            REGISTRO.add(Checagem("banco", f"banco/{t}", "banco_nao_encolhe", False, True, f"registros {antes}→{n}"))
    PASTA.mkdir(parents=True, exist_ok=True)
    marca = banco_dir / "OK"
    if ok:
        pd.DataFrame({"tabela": list(atual), "registros": list(atual.values())}).to_csv(arq, index=False)
        REGISTRO.add(Checagem("banco", "banco/vigia.db", "banco_nao_encolhe", True, True,
                              ", ".join(f"{t} {n}" for t, n in atual.items())))
        marca.write_text(agora())
    elif marca.exists():
        marca.unlink()
    return ok


# ---------- camada 3: conciliação entre fontes ----------

def conciliar_siconfi(pagamentos: pd.DataFrame, dca_funcao: pd.DataFrame, ibge: str) -> pd.DataFrame:
    """Empenhado no portal x empenhado declarado ao Tesouro (DCA Anexo I-E, com intraorçamentárias)."""
    if pagamentos.empty or dca_funcao.empty:
        return pd.DataFrame()
    portal = _num(pagamentos["ValorEmpenhado"]).groupby(pagamentos["Ano"]).sum()
    d = dca_funcao[(dca_funcao["cod_ibge"] == ibge) & (dca_funcao["coluna"] == "Despesas Empenhadas")
                   & (dca_funcao["conta"].isin(["Despesas Exceto Intraorçamentárias", "Despesas Intraorçamentárias"]))]
    siconfi = _num(d["valor"]).groupby(d["exercicio"]).sum()
    anos = sorted(set(portal.index) & set(siconfi.index))
    linhas = []
    for a in anos:
        dif = (portal[a] - siconfi[a]) / siconfi[a]
        ok = abs(dif) <= TOLERANCIA_SICONFI
        linhas.append({"ano": a, "portal_empenhado": round(portal[a], 2), "siconfi_empenhado": round(siconfi[a], 2),
                       "diferenca_pct": round(dif * 100, 2), "ok": ok})
        REGISTRO.add(Checagem("conciliacao", f"pagamentos_{a}.csv", "portal_x_siconfi", ok, False,
                              f"portal {_br(portal[a]/1e6)} mi x Siconfi {_br(siconfi[a]/1e6)} mi ({dif:+.2%})"))
    REGISTRO.conciliacao = pd.DataFrame(linhas)
    return REGISTRO.conciliacao


# ---------- saída ----------

def _anexar(caminho: Path, linhas: list[dict], chave: list[str]):
    if not linhas:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = pd.DataFrame(linhas).astype(str)
    if caminho.exists():
        novo = pd.concat([pd.read_csv(caminho, dtype=str, keep_default_na=False), novo], ignore_index=True)
    novo.drop_duplicates(subset=chave, keep="last").to_csv(caminho, index=False)


# ---------------------------------------------------------------- fonte fora do ar: alarme só se durar
# O portal da prefeitura bloqueia o GitHub por algumas horas de vez em quando (403 em tudo), e o PNCP e o
# portal às vezes caem (5xx). Isso não é erro nosso e se resolve sozinho: a execução ficava vermelha e mandava
# e-mail quase todo dia, e alarme que toca todo dia ninguém lê. Agora fonte fora do ar fica registrada aqui e
# em docs/qualidade.md, e só deixa a execução vermelha se continuar fora por mais de PRAZO_FORA_H horas
# (depois, um lembrete por semana). Erro no nosso código e checagem bloqueante continuam vermelhos na hora.
FORA = PASTA / "fontes_fora.csv"
PRAZO_FORA_H = 20          # duas coletas diárias seguidas fora do ar = alarme
LEMBRETE_FORA_DIAS = 7     # depois do primeiro alarme, só avisa de novo uma vez por semana
_COLUNAS_FORA = ["fonte", "fora_desde", "ultima_falha", "avisado_em", "detalhe"]
_DETALHE_PASSAGEIRO = re.compile(
    r"HTTP (403|408|425|429|5\d\d)\b|Timeout|ConnectionError|ChunkedEncodingError|RemoteDisconnected|"
    r"LimiteDeTentativas|AcessoNegado", re.IGNORECASE)


def erro_passageiro(exc: BaseException | None, checagens: list[Checagem]) -> bool:
    """A fonte caiu por motivo de fora (bloqueio, servidor fora do ar, rede), e não por erro no nosso código
    ou por dado estranho. Olha a exceção e, quando o coletor já tratou o erro e só avisou no fim, as
    checagens erro_na_fonte que ele registrou."""
    import requests

    from .http import AcessoNegado, LimiteDeTentativas
    vistos, e = set(), exc
    while e is not None and id(e) not in vistos:
        vistos.add(id(e))
        if isinstance(e, (AcessoNegado, LimiteDeTentativas, requests.ConnectionError, requests.Timeout,
                          requests.exceptions.ChunkedEncodingError)):
            return True
        if isinstance(e, requests.HTTPError):
            r = getattr(e, "response", None)
            return r is not None and (r.status_code in (403, 408, 425, 429) or r.status_code >= 500)
        e = e.__cause__ or e.__context__
    erros = [c for c in checagens if c.regra == "erro_na_fonte" and not c.ok]
    return bool(erros) and all(_DETALHE_PASSAGEIRO.search(c.detalhe or "") for c in erros)


def _ler_fora(arquivo: Path) -> dict[str, dict]:
    if not arquivo.exists():
        return {}
    d = pd.read_csv(arquivo, dtype=str, keep_default_na=False)
    return {x["fonte"]: dict(x) for x in d.to_dict("records")}


def _horas(desde: str, ate: datetime) -> float:
    return (ate - datetime.strptime(desde, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 3600


def avaliar_fora(passageiras: dict[str, str], funcionaram: list[str], arquivo: Path | None = None,
                 momento: datetime | None = None) -> list[str]:
    """Atualiza data/qualidade/fontes_fora.csv e devolve as fontes fora do ar há tempo demais, que devem
    deixar a execução vermelha. passageiras: fonte -> detalhe do erro; funcionaram: fontes que deram certo
    nesta execução (saem da lista)."""
    arquivo = arquivo or FORA
    momento = momento or datetime.now(timezone.utc)
    marca = momento.strftime("%Y-%m-%dT%H:%M:%SZ")
    fora = _ler_fora(arquivo)
    antes = {k: dict(v) for k, v in fora.items()}
    for nome in funcionaram:
        fora.pop(nome, None)
    alarme = []
    for nome, detalhe in passageiras.items():
        x = fora.setdefault(nome, {"fonte": nome, "fora_desde": marca, "avisado_em": ""})
        x["ultima_falha"], x["detalhe"] = marca, str(detalhe)[:200]
        if _horas(x["fora_desde"], momento) >= PRAZO_FORA_H and (
                not x.get("avisado_em") or _horas(x["avisado_em"], momento) >= LEMBRETE_FORA_DIAS * 24):
            x["avisado_em"] = marca
            alarme.append(nome)
    if fora != antes:
        if fora:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(list(fora.values()), columns=_COLUNAS_FORA).to_csv(arquivo, index=False)
        elif arquivo.exists():
            arquivo.unlink()
    return alarme


def salvar(conciliacao: pd.DataFrame | None = None) -> None:
    conciliacao = REGISTRO.conciliacao if conciliacao is None else conciliacao
    PASTA.mkdir(parents=True, exist_ok=True)
    _anexar(PASTA / "manifesto.csv", REGISTRO.manifesto, ["arquivo_bruto", "sha256"])  # guarda cada versão distinta
    _anexar(PASTA / "alteracoes.csv", REGISTRO.alteracoes, ["arquivo", "detectado_em"])
    pd.DataFrame([asdict(c) for c in REGISTRO.checagens],
                 columns=list(Checagem.__dataclass_fields__)).to_csv(PASTA / "checagens.csv", index=False)
    escrever_relatorio(conciliacao)


def _br(v: float, casas: int = 1) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def escrever_relatorio(conciliacao: pd.DataFrame) -> None:
    r = REGISTRO
    falhas = [c for c in r.checagens if not c.ok]
    if r.bloqueios or r.falhas_fonte:
        status = "❌ há problemas (ver abaixo)"
    elif r.fora_passageiro:
        status = f"⚠️ fonte fora do ar há pouco tempo (sem alarme; vira alarme se passar de {PRAZO_FORA_H} h)"
    else:
        status = "✅ tudo certo"
    linhas = [
        "# Qualidade dos dados", "",
        f"_Última execução: {agora()} (UTC). Gerado automaticamente; regras em `vigia/qualidade.py`._", "",
        f"**Status:** {status}", "",
        f"- Checagens feitas: {len(r.checagens)} · falharam: {len(falhas)} "
        f"(bloqueantes: {len(r.bloqueios)})",
        f"- Fontes que não responderam: {', '.join(r.falhas_fonte) or 'nenhuma'}",
        f"- Fora do ar há pouco tempo (bloqueio ou queda da fonte, sem alarme): "
        f"{', '.join(r.fora_passageiro) or 'nenhuma'} (histórico em `data/qualidade/fontes_fora.csv`)",
        f"- Arquivos crus baixados hoje: {len(r.manifesto)} (hash SHA-256 em `data/qualidade/manifesto.csv`)",
        "",
        "Quando uma checagem bloqueante falha, o arquivo novo **não** é gravado: fica a versão anterior.",
        "",
    ]
    if falhas:
        linhas += ["## Checagens que falharam", "", "| Arquivo | Regra | Bloqueante | Detalhe |", "|---|---|---|---|"]
        linhas += [f"| {c.arquivo} | {c.regra} | {'sim' if c.bloqueante else 'não'} | {c.detalhe} |" for c in falhas]
        linhas.append("")
    if not conciliacao.empty:
        linhas += ["## Conciliação: portal da prefeitura x Tesouro (Siconfi)", "",
                   "Total empenhado no ano, em R$ milhões. As duas fontes são da própria prefeitura; "
                   f"diferença acima de {TOLERANCIA_SICONFI:.0%} indica dado faltando ou erro de leitura.", "",
                   "| Ano | Portal | Siconfi | Diferença | |", "|---|---|---|---|---|"]
        for _, c in conciliacao.iterrows():
            linhas.append(f"| {c['ano']} | {_br(c['portal_empenhado']/1e6)} | {_br(c['siconfi_empenhado']/1e6)} | "
                          f"{'+' if c['diferenca_pct'] > 0 else ''}{_br(c['diferenca_pct'], 2)}% | {'✅' if c['ok'] else '⚠️'} |")
        linhas += ["", "A diferença de cerca de 1% se repete em todos os anos (classificação por área difere "
                   "entre as duas bases). Uma mudança brusca nesse padrão é o sinal de alerta.", ""]
    if r.notas:
        linhas += ["## Exclusões aplicadas pelas regras", "",
                   "Casos que uma regra deixou de fora de propósito, listados para que a exclusão possa ser conferida.",
                   "", "| Regra | Detalhe |", "|---|---|"]
        linhas += [f"| {regra} | {detalhe.replace('|', '/')} |" for regra, detalhe in r.notas]
        linhas.append("")
    alt = PASTA / "alteracoes.csv"
    if alt.exists():
        a = pd.read_csv(alt, dtype=str)
        linhas += ["## Dados antigos que mudaram depois de publicados", "",
                   "Anos já encerrados são baixados de novo uma vez por mês. A coluna Origem compara o arquivo cru "
                   "de agora com o anterior: se a prefeitura não mudou o arquivo, a mudança foi do nosso leitor. "
                   "O histórico do git guarda as duas versões.", "",
                   "| Detectado em | Arquivo | Linhas | Total (R$) | Origem |", "|---|---|---|---|---|"]
        for _, x in a.tail(30).iterrows():
            linhas.append(f"| {x['detectado_em'][:10]} | {x['arquivo']} | {x['linhas_antes']}→{x['linhas_depois']} | "
                          f"{_br(float(x['total_antes']), 2)}→{_br(float(x['total_depois']), 2)} | {x.get('origem', '')} |")
        linhas.append("")
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "qualidade.md").write_text("\n".join(linhas), encoding="utf-8")
