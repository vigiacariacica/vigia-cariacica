"""Fonte fora do ar (bloqueio do portal, PNCP caído) só deixa a execução vermelha se durar.

10/11/2026: o portal da prefeitura respondeu 403 a tudo numa execução e funcionou na seguinte, 20 minutos
depois. A execução ficava vermelha e o GitHub mandava e-mail quase todo dia por algo que se resolve sozinho.
"""
from datetime import datetime, timedelta, timezone

import requests

from vigia import qualidade
from vigia.coletores import portal_extra as P
from vigia.http import AcessoNegado

T0 = datetime(2026, 11, 10, 9, 23, tzinfo=timezone.utc)


def _http(codigo):
    r = requests.Response()
    r.status_code = codigo
    return requests.HTTPError(f"{codigo} Client Error", response=r)


def _erro(detalhe):
    return qualidade.Checagem("receitas", "receitas_2026.csv", "erro_na_fonte", False, False, detalhe)


def test_o_que_e_fonte_fora_do_ar():
    assert qualidade.erro_passageiro(_http(403), [])
    assert qualidade.erro_passageiro(_http(503), [])
    assert qualidade.erro_passageiro(requests.ConnectionError("caiu"), [])
    assert qualidade.erro_passageiro(AcessoNegado("HTTP 403"), [])
    # o coletor do portal trata o erro e só avisa no fim: vale o que ele registrou
    assert qualidade.erro_passageiro(RuntimeError("receitas: falha em 2026"), [_erro("HTTP 403 <!DOCTYPE html>")])


def test_o_que_continua_alarme_na_hora():
    assert not qualidade.erro_passageiro(_http(404), [])                    # endereço mudou: precisa de código
    assert not qualidade.erro_passageiro(KeyError("coluna"), [])            # erro nosso
    assert not qualidade.erro_passageiro(RuntimeError("x"), [])             # sem prova de que a fonte caiu
    assert not qualidade.erro_passageiro(RuntimeError("x"), [_erro("HTTP 403"), _erro("ValueError: data")])


def test_alarme_so_depois_de_um_dia_e_lembrete_semanal(tmp_path):
    arq = tmp_path / "fontes_fora.csv"
    fora = {"transparencia": "HTTPError: 403"}
    assert qualidade.avaliar_fora(fora, [], arq, T0) == []                                   # 1º dia: só registra
    assert arq.exists()
    assert qualidade.avaliar_fora(fora, [], arq, T0 + timedelta(hours=5)) == []              # push no mesmo dia
    assert qualidade.avaliar_fora(fora, [], arq, T0 + timedelta(days=1)) == ["transparencia"]  # 2º dia: alarme
    assert qualidade.avaliar_fora(fora, [], arq, T0 + timedelta(days=2)) == []               # sem e-mail todo dia
    assert qualidade.avaliar_fora(fora, [], arq, T0 + timedelta(days=8)) == ["transparencia"]  # lembrete semanal


def test_fonte_que_volta_sai_da_lista(tmp_path):
    arq = tmp_path / "fontes_fora.csv"
    qualidade.avaliar_fora({"transparencia": "403"}, [], arq, T0)
    qualidade.avaliar_fora({}, ["transparencia"], arq, T0 + timedelta(hours=3))
    assert not arq.exists()
    # e se cair de novo, a contagem recomeça
    assert qualidade.avaliar_fora({"transparencia": "403"}, [], arq, T0 + timedelta(days=1)) == []


def test_sem_mudanca_nao_cria_arquivo(tmp_path):
    arq = tmp_path / "fontes_fora.csv"
    assert qualidade.avaliar_fora({}, ["transparencia", "pncp"], arq, T0) == []
    assert not arq.exists()


def test_bloqueio_do_portal_nao_deixa_execucao_vermelha_no_primeiro_dia(monkeypatch):
    from vigia import __main__ as cli
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(cli, "ESPERA_SEGUNDA_CHANCE", 0)

    def bloqueado():
        qualidade.REGISTRO.add(_erro("HTTP 403 <!DOCTYPE html>"))
        raise RuntimeError("receitas: falha em 2026")

    def quebrado():
        raise KeyError("coluna nova no CSV")

    monkeypatch.setattr(P, "coletar_receitas", bloqueado)
    monkeypatch.setattr(P, "coletar_obras", quebrado)

    class Con:
        def commit(self):
            pass

    assert cli.coletar(["receitas", "obras"], {}, Con(), None) == 1   # só o erro nosso conta
    assert qualidade.REGISTRO.falhas_fonte == ["obras"]
    assert qualidade.REGISTRO.fora_passageiro == ["receitas"]
    assert qualidade.FORA.exists()
