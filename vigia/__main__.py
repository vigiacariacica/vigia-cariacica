"""Vigia Cariacica: um comando para tudo.

    python -m vigia diario        o que o GitHub roda todo dia (coleta + alertas + relatório)
    python -m vigia semanal       preços das vizinhas, empresas punidas (CEIS/CNEP), emendas Pix e TSE
    python -m vigia mensal        anos fechados do portal de novo (detecta dado alterado)

Etapas avulsas:
    coletar FONTE [FONTE ...]     transparencia | emendas | obras | diarias | receitas | siconfi | tcees | tesouro |
                                  ibge | pncp | vizinhos | empresas | sancoes | transferegov | tse |
                                  licitacoes | folha | divida | estado | externos (ISP e CAUC) |
                                  fila | equipamentos (postos e escolas por bairro)
    alertas                       roda as 32 regras e exporta data/alertas.csv
    refinar                       data/refinado/: o mapa do dinheiro (origem, tipo de gasto, quem recebe)
    exportar                      banco -> CSVs de data/pncp e data/receita
    relatorio                     docs/relatorio.md e docs/qualidade.md
    painel                        saida/painel.html e saida/relatorio.xlsx
    dossie ID [ID ...] | --top N  dossiê com evidências e pedido de LAI pronto
    marcar ID STATUS ["nota"]     novo | em_analise | confirmado | denunciado | descartado
    status                        o que já foi coletado
    importar-sancoes ARQ          CSV/ZIP do CEIS ou CNEP (alternativa sem chave da CGU)
    importar-servidores ARQ       lista de servidores (LAI) para a regra R14
    ia ID                         segunda opinião por IA (opcional, só local)

Uma fonte que falhar não derruba as outras, mas o processo termina com código 1 para o GitHub
marcar a execução em vermelho e avisar por e-mail. O que deu certo é salvo mesmo assim.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

from . import armazem, config, db, log, qualidade, relatorio
from .config import CARIACICA_IBGE, DADOS

FONTES = ("transparencia", "siconfi", "tcees", "tesouro", "ibge", "pncp", "vizinhos", "empresas", "sancoes",
          "emendas", "obras", "diarias", "receitas", "transferegov", "tse",
          "licitacoes", "folha", "divida", "estado", "externos", "fila", "equipamentos")
# Fontes da revisão de 10/11/2026, cada uma em vigia/coletores/<nome>.py com uma função coletar()
SIMPLES = ("licitacoes", "folha", "divida", "estado", "externos", "fila", "equipamentos")
PORTAL_EXTRA = ("emendas", "obras", "diarias", "receitas")   # vigia/coletores/portal_extra.py


# ---------------------------------------------------------------- coleta

def _coletar_fonte(nome: str, cfg: dict, con, args) -> None:
    if nome == "transparencia":
        from .coletores import transparencia
        transparencia.coletar()
    elif nome in PORTAL_EXTRA:
        from .coletores import portal_extra
        getattr(portal_extra, f"coletar_{nome}")()
    elif nome == "siconfi":
        from .coletores import siconfi
        siconfi.coletar()
    elif nome == "tcees":
        from .coletores import tcees
        tcees.coletar()
    elif nome == "tesouro":
        from .coletores import tesouro
        tesouro.coletar()
    elif nome == "ibge":
        from .coletores import ibge
        ibge.coletar()
    elif nome == "transferegov":
        from .coletores import transferegov
        transferegov.coletar()
    elif nome in SIMPLES:
        import importlib
        importlib.import_module(f".coletores.{nome}", __package__).coletar()
    elif nome == "tse":
        from .coletores import tse
        tse.coletar(forcar=getattr(args, "forcar", False))
    elif nome in ("pncp", "vizinhos"):
        from .coletores import pncp
        from .http import Cliente
        ini, fim = config.periodo(cfg)
        if getattr(args, "desde", None):
            ini = dt.date.fromisoformat(args.desde)
        cli = Cliente(cfg, con)
        t0 = time.time()
        pncp.coletar_tudo(cli, con, cfg, ini, fim, so_vizinhos=(nome == "vizinhos"), sem_vizinhos=(nome == "pncp"))
        db.registrar_execucao(con, f"coletar_{nome}", dt.datetime.fromtimestamp(t0).isoformat(),
                              dt.datetime.now().isoformat(), {"chamadas": cli.chamadas, "cache": cli.do_cache})
        log.info(f"{nome}: {cli.chamadas} chamadas à internet, {cli.do_cache} respostas do cache, "
                 f"{(time.time() - t0) / 60:.1f} min")
    elif nome == "empresas":
        from .coletores import empresas
        from .http import Cliente
        empresas.enriquecer(Cliente(cfg, con), con, cfg)
    elif nome == "sancoes":
        from .coletores import empresas
        from .http import Cliente
        if not cfg["apis"].get("chave_transparencia"):
            log.aviso("Sem chave da CGU (segredo CHAVE_TRANSPARENCIA): sanções CEIS/CNEP não consultadas.")
            return
        empresas.sancoes_api(Cliente(cfg, con), con, cfg)
    else:
        raise ValueError(f"Fonte desconhecida: {nome}")
    con.commit()


# O portal da prefeitura às vezes bloqueia o GitHub por alguns minutos (09/11/2026: HTTP 403 em todas as
# chamadas às 7h18, tudo normal às 13h35), e a execução ficava vermelha à toa. Uma fonte rápida que falhar
# ganha uma segunda tentativa no fim da coleta. As longas, ou que já toleram falha por conta própria,
# ficam de fora.
SEM_SEGUNDA_CHANCE = {"pncp", "vizinhos", "empresas", "sancoes", "tse"}
ESPERA_SEGUNDA_CHANCE = 180  # segundos


def _registros():
    r = qualidade.REGISTRO
    return (r.checagens, r.manifesto, r.alteracoes)


def _tentar(nome, cfg, con, args):
    """Coleta uma fonte. Devolve None se deu certo; se falhou, (o que ela registrou (checagens, manifesto,
    alterações), a exceção), para a segunda tentativa poder substituir e para saber se foi a fonte que caiu."""
    marcas = [len(lista) for lista in _registros()]
    try:
        log.etapa(f"Coletando {nome}")
        _coletar_fonte(nome, cfg, con, args)
        return None
    except Exception as e:
        logging.exception("Falha ao coletar %s", nome)
        con.commit()
        return [lista[m:] for lista, m in zip(_registros(), marcas)], e


def _esquecer(registrado) -> None:
    """Tira do registro de qualidade o que a primeira tentativa anotou (a segunda anota de novo)."""
    for lista, velhos in zip(_registros(), registrado):
        ids = {id(x) for x in velhos}
        lista[:] = [x for x in lista if id(x) not in ids]


def coletar(fontes, cfg, con, args) -> int:
    falharam = {}
    for nome in fontes:
        registrado = _tentar(nome, cfg, con, args)
        if registrado is not None:
            falharam[nome] = registrado
    repetir = [n for n in falharam if n not in SEM_SEGUNDA_CHANCE]
    if repetir:
        log.aviso(f"Segunda tentativa daqui a {ESPERA_SEGUNDA_CHANCE}s: {', '.join(repetir)}")
        time.sleep(ESPERA_SEGUNDA_CHANCE)
        for nome in repetir:
            _esquecer(falharam[nome][0])
            nova = _tentar(nome, cfg, con, args)
            if nova is None:
                del falharam[nome]
                qualidade.REGISTRO.add(qualidade.Checagem(
                    nome, "-", "segunda_tentativa", True, False, "falhou na 1ª tentativa e funcionou na 2ª"))
                log.info(f"{nome}: funcionou na segunda tentativa")
            else:
                falharam[nome] = nova
    # Fonte fora do ar (bloqueio, servidor caído) só vira alarme se durar; erro nosso é alarme na hora.
    passageiras = {n: f"{type(e).__name__}: {str(e)[:150]}" for n, (reg, e) in falharam.items()
                   if qualidade.erro_passageiro(e, reg[0])}
    alarme = qualidade.avaliar_fora(passageiras, [n for n in fontes if n not in falharam])
    graves = [n for n in falharam if n not in passageiras or n in alarme]
    qualidade.REGISTRO.falhas_fonte.extend(graves)
    for nome in passageiras:
        if nome in alarme:
            log.aviso(f"{nome}: fora do ar há mais de {qualidade.PRAZO_FORA_H} h (alarme)")
            continue
        qualidade.REGISTRO.fora_passageiro.append(nome)
        log.aviso(f"{nome}: fonte fora do ar agora ({passageiras[nome]}); sem alarme por enquanto")
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning::{nome} fora do ar (passageiro, sem alarme): {passageiras[nome]}", flush=True)
    return len(graves)


# ---------------------------------------------------------------- análise

def ler_varios(padrao: str) -> pd.DataFrame:
    """Junta os arquivos anuais (ex.: pagamentos_2021.csv, pagamentos_2022.csv...)."""
    partes = [armazem.ler(p) for p in sorted((DADOS / "transparencia").glob(padrao))]
    partes = [p for p in partes if not p.empty]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def analisar(cfg, con) -> pd.DataFrame:
    from . import alertas, exportar
    log.etapa("Exportando o banco para CSV")
    exportar.exportar_tudo(con)
    log.etapa("Rodando as 32 regras de alerta")
    pagamentos = ler_varios("pagamentos_*.csv")
    contratos_mun = ler_varios("contratos_*.csv")
    # a lista oficial não tem as emergências de 2022 e 2023: completa pelo objeto dos contratos
    from .alertas.portal import completar_emergenciais
    emergenciais = completar_emergenciais(ler_varios("emergenciais_*.csv"), contratos_mun)
    a = alertas.rodar(con, cfg, pagamentos=pagamentos, contratos_mun=contratos_mun,
                      emergenciais=emergenciais,
                      penalizados=armazem.ler(DADOS / "transparencia" / "penalizados.csv"),
                      campanha=armazem.ler(DADOS / "tse" / "fornecedores_campanha.csv"))
    hoje = dt.date.today().isoformat()
    log.info(f"{len(a)} alertas ({int((a['primeira_vez'] == hoje).sum())} novos hoje): "
             + ", ".join(f"{g} {n}" for g, n in a["gravidade"].value_counts().items()))
    refinar(pagamentos)
    relatorio.gerar(a, pagamentos=pagamentos, emergenciais=emergenciais)
    from .regras import markdown
    (config.DOCS / "REGRAS.md").write_text(markdown(), encoding="utf-8")
    qualidade.conciliar_siconfi(pagamentos, armazem.ler(DADOS / "siconfi" / "dca_despesa_funcao.csv"),
                                str(CARIACICA_IBGE))
    return a


def refinar(pagamentos: pd.DataFrame) -> None:
    """Camada refinada (data/refinado/). Uma falha aqui não derruba alertas nem relatório: vira
    checagem não bloqueante em docs/qualidade.md."""
    from . import refino
    log.etapa("Refinando: o mapa do dinheiro")
    try:
        refino.rodar(pagamentos)
    except Exception as e:
        logging.exception("Falha no refino (alertas e relatório seguem)")
        qualidade.REGISTRO.add(qualidade.Checagem("refino", "data/refinado/", "refino_gerado", False, False,
                                                  f"{type(e).__name__}: {str(e)[:150]}"))


def importar_entradas(con) -> None:
    """Arquivos obtidos por LAI ou baixados à mão, colocados em data/entrada/, entram no banco a cada
    execução (assim a regra R14 e as sanções importadas valem também no GitHub):
        data/entrada/servidores.csv|.xlsx   lista de servidores (nome, cargo, lotação)
        data/entrada/sancoes/*.csv|*.zip    arquivos do CEIS/CNEP baixados do Portal da Transparência
    """
    from .coletores import empresas
    entrada = DADOS / "entrada"
    for ext in ("csv", "xlsx"):
        arq = entrada / f"servidores.{ext}"
        if arq.exists():
            empresas.importar_servidores(con, str(arq), substituir=True)
    for arq in sorted((entrada / "sancoes").glob("*")) if (entrada / "sancoes").exists() else []:
        if arq.suffix.lower() in (".csv", ".zip"):
            empresas.importar_sancoes(con, str(arq))


def painel(cfg, con) -> None:
    from . import painel as p
    try:
        html, _ = p.gerar(con, cfg)
        log.info(f"Painel: {html}")
    except Exception as e:
        logging.exception("Falha ao gerar o painel (não afeta os dados)")
        qualidade.REGISTRO.add(qualidade.Checagem("painel", "saida/painel.html", "painel_gerado", False, False,
                                                  f"{type(e).__name__}: {str(e)[:150]}"))


# ---------------------------------------------------------------- comandos

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m vigia", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="caminho do config.toml (padrão: o da raiz do repositório)")
    sub = p.add_subparsers(dest="comando")
    sub.add_parser("diario")
    sub.add_parser("semanal")
    sub.add_parser("mensal")
    sp = sub.add_parser("coletar")
    sp.add_argument("fontes", nargs="+", choices=FONTES)
    sp.add_argument("--desde", help="AAAA-MM-DD (só PNCP)")
    sp.add_argument("--forcar", action="store_true", help="refaz o TSE mesmo que o arquivo já exista")
    for nome in ("alertas", "exportar", "relatorio", "painel", "status", "refinar"):
        sub.add_parser(nome)
    sp = sub.add_parser("dossie"); sp.add_argument("ids", nargs="*"); sp.add_argument("--top", type=int)
    sp = sub.add_parser("marcar"); sp.add_argument("id"); sp.add_argument("status"); sp.add_argument("nota", nargs="?", default="")
    sp = sub.add_parser("importar-sancoes"); sp.add_argument("arquivo"); sp.add_argument("--cadastro", choices=["CEIS", "CNEP"])
    sp = sub.add_parser("importar-servidores"); sp.add_argument("arquivo"); sp.add_argument("--substituir", action="store_true")
    sp = sub.add_parser("ia"); sp.add_argument("id")
    # compatibilidade com o nome antigo
    sub.add_parser("tudo")
    args = p.parse_args(argv)
    if not args.comando:
        p.print_help()
        return 2

    cfg = config.carregar(args.config)
    con = db.conectar(cfg["_pasta_dados"])
    falhas = 0
    try:
        cmd = "diario" if args.comando == "tudo" else args.comando
        if cmd == "diario":
            falhas = coletar(["transparencia", *PORTAL_EXTRA, "licitacoes", "folha", "siconfi", "tcees", "tesouro", "ibge",
                              "divida", "estado", "externos", "fila", "pncp", "empresas"], cfg, con, args)
        elif cmd == "semanal":
            # PNCP de Cariacica de novo, revisitando compras do último ano ainda sem resultado
            cfg["coleta"]["revisitar_sem_resultado"] = True
            # "tse" (entrada da R25) fica fora enquanto a R25 está em revisão jurídica (docs/DECISOES.md, 24/11/2026)
            falhas = coletar(["pncp", "vizinhos", "empresas", "sancoes", "transferegov", "equipamentos"], cfg, con, args)
        elif cmd == "mensal":
            os.environ["VIGIA_COMPLETO"] = "1"
            falhas = coletar(["transparencia", "diarias", "receitas", "siconfi"], cfg, con, args)
        elif cmd == "coletar":
            falhas = coletar(args.fontes, cfg, con, args)

        if cmd in ("diario", "semanal", "mensal", "coletar"):
            qualidade.guarda_final()
        if cmd in ("diario", "semanal", "mensal", "alertas"):
            importar_entradas(con)
            # O banco é conferido ANTES de exportar: banco vazio ou encolhido nunca vira CSV nem alerta.
            if qualidade.checar_banco(con, Path(cfg["_pasta_dados"])):
                try:
                    analisar(cfg, con)
                except Exception as e:
                    logging.exception("Falha na análise: saídas restauradas, nada publicado pela metade")
                    qualidade.REGISTRO.falhas_fonte.append(f"análise ({type(e).__name__})")
                    falhas += 1
                    qualidade.restaurar_saidas()
                qualidade.guarda_alertas()
                qualidade.guarda_final()  # de novo: agora cobre também os CSVs exportados do banco
            else:
                logging.error("Banco encolheu: exportação, alertas e relatório NÃO foram refeitos")
        if cmd in ("diario", "semanal", "painel"):
            painel(cfg, con)
        if cmd in ("diario", "semanal", "mensal", "alertas"):
            qualidade.varrer_cpfs()       # LGPD: última barreira antes do commit
            qualidade.salvar()            # docs/qualidade.md e data/qualidade/ com todas as checagens

        if cmd == "exportar":
            from . import exportar
            exportar.exportar_tudo(con)
        elif cmd == "relatorio":
            a = armazem.ler(DADOS / "alertas.csv")
            from .alertas.portal import completar_emergenciais
            relatorio.gerar(a, pagamentos=ler_varios("pagamentos_*.csv"),
                            emergenciais=completar_emergenciais(ler_varios("emergenciais_*.csv"),
                                                                ler_varios("contratos_*.csv")))
        elif cmd == "refinar":
            refinar(ler_varios("pagamentos_*.csv"))
        elif cmd == "status":
            status(cfg, con)
        elif cmd == "dossie":
            from . import dossie
            ids = list(args.ids or [])
            if args.top:
                ids += [r[0] for r in con.execute(
                    "SELECT id FROM alertas WHERE ativo=1 AND status!='descartado' "
                    "ORDER BY pontos DESC, COALESCE(valor_excesso,0) DESC, COALESCE(valor_envolvido,0) DESC LIMIT ?",
                    (args.top,))]
            if not ids:
                print("Informe o ID do alerta (coluna id de data/alertas.csv) ou use --top 10")
                return 2
            for i in ids:
                _, html = dossie.gerar(con, cfg, i)
                log.info(f"Dossiê {i}: {html}")
        elif cmd == "marcar":
            from . import alertas
            alertas.marcar(con, args.id, args.status, args.nota)
            alertas.exportar(con)
            log.info(f"Alerta {args.id} marcado como {args.status} (registrado em data/casos.csv).")
        elif cmd == "importar-sancoes":
            from .coletores import empresas
            empresas.importar_sancoes(con, args.arquivo, args.cadastro)
        elif cmd == "importar-servidores":
            from .coletores import empresas
            empresas.importar_servidores(con, args.arquivo, substituir=args.substituir)
        elif cmd == "ia":
            from . import ia
            log.info(f"Análise salva em {ia.analisar(con, cfg, args.id)}")
    finally:
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # tudo dentro de vigia.db antes de compactar
        con.close()

    problemas = falhas + len(qualidade.REGISTRO.bloqueios)
    if problemas:
        logging.error("%d problema(s) nesta execução; ver docs/qualidade.md", problemas)
    return 1 if problemas else 0


def status(cfg, con) -> None:
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    print(f"""
Banco: {cfg['_pasta_dados']}/vigia.db
Órgãos do município: {q("SELECT COUNT(*) FROM orgaos WHERE alvo=1")}
Contratações (município): {q("SELECT COUNT(*) FROM contratacoes WHERE alvo=1")}   (vizinhos/externas): {q("SELECT COUNT(*) FROM contratacoes WHERE alvo=0")}
Itens: {q("SELECT COUNT(*) FROM itens")}   Resultados (preços): {q("SELECT COUNT(*) FROM resultados")}
Contratos: {q("SELECT COUNT(*) FROM contratos")}   Termos aditivos: {q("SELECT COUNT(*) FROM termos")}
Empresas (Receita): {q("SELECT COUNT(*) FROM fornecedores")}   Sanções: {q("SELECT COUNT(*) FROM sancoes")}   Servidores: {q("SELECT COUNT(*) FROM servidores")}
Alertas ativos: {q("SELECT COUNT(*) FROM alertas WHERE ativo=1")}
Respostas cruas guardadas (prova): {q("SELECT COUNT(*) FROM bruto")}   Última: {q("SELECT MAX(baixado_em) FROM bruto")}
Pagamentos no portal municipal: {len(list((DADOS / 'transparencia').glob('pagamentos_*.csv')))} anos
""")


if __name__ == "__main__":
    sys.exit(main())
