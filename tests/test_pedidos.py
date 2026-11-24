"""Perguntas pela Lei de Acesso: prazo, prorrogação, fim de semana e a seção do relatório."""
from datetime import date

import pandas as pd
import pytest

from vigia import pedidos as P

CAB = "pedido,protocolo,canal,orgao,assunto,enviado_em,prazo_dias,prorrogado,respondido_em,resultado,video\n"


@pytest.fixture
def arquivo(tmp_path, monkeypatch):
    caminho = tmp_path / "pedidos.csv"
    monkeypatch.setattr(P, "ARQUIVO", caminho)
    return caminho


def test_situacao_prazos():
    df = pd.DataFrame([
        {"pedido": "9", "protocolo": "A", "enviado_em": "2026-11-07", "prazo_dias": "20"},              # 27/11, sexta
        {"pedido": "6", "protocolo": "B", "enviado_em": "2026-11-07", "prazo_dias": "20", "prorrogado": "sim"},
        {"pedido": "14", "protocolo": "C", "enviado_em": "2026-11-10", "prazo_dias": "20",
         "respondido_em": "2026-11-20"},
        {"pedido": "R", "protocolo": "D", "enviado_em": "2026-11-10", "prazo_dias": "30"},              # 10/12
        {"pedido": "x", "protocolo": "E", "enviado_em": ""},                                            # sem data: fora
    ])
    s = P.situacao(df, date(2026, 11, 28)).set_index("protocolo")
    assert list(s.index) == ["A", "B", "C", "D"]
    assert s.loc["A", "prazo"] == date(2026, 11, 27) and s.loc["A", "estado"] == "vencido"
    assert s.loc["B", "prazo"] == date(2026, 12, 7) and s.loc["B", "estado"] == "no prazo"   # 27/11 + 10
    assert s.loc["C", "estado"] == "respondido"
    assert s.loc["D", "prazo"] == date(2026, 12, 10)


def test_prazo_no_fim_de_semana_vai_para_segunda():
    df = pd.DataFrame([{"pedido": "1", "protocolo": "A", "enviado_em": "2026-11-08", "prazo_dias": "20"}])
    assert P.situacao(df, date(2026, 11, 9)).loc[0, "prazo"] == date(2026, 11, 30)   # 28/11 é sábado


def test_secao_markdown(arquivo):
    arquivo.write_text(CAB
                       + "9,008830.2026-50,e-SIC,,Tapa-buraco,2026-11-07,20,,,,\n"
                       + "C3,2026111046,e-Ouv ES,Cesan,Esgoto por bairro,2026-11-10,20,,,,02\n"
                       + "14,008919.2026-72,e-SIC,,Créditos extras,2026-11-10,20,,2026-11-25,respondido,\n",
                       encoding="utf-8")
    md = P.secao_markdown(date(2026, 11, 28))
    assert "**Respondidas: 1 de 3 (33%).** No prazo: 1. Vencidas sem resposta: 1." in md
    assert "| 27/11/2026 | Pedido 9 | 008830.2026-50 | Tapa-buraco | 1 |" in md
    assert "| 30/11/2026 | C3 | 2026111046 | Esgoto por bairro |" in md


def test_secao_vazia_sem_arquivo(arquivo):
    assert P.secao_markdown(date(2026, 11, 28)) == ""


def test_arquivo_real_e_valido():
    df = pd.read_csv(P.DADOS / "pedidos" / "pedidos.csv", dtype=str, keep_default_na=False)
    assert df["protocolo"].is_unique
    assert all(P._data(d) for d in df["enviado_em"])
    assert set(df["prazo_dias"]) <= {"20", "30"}
