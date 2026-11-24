from datetime import date

from vigia.radar import brl, prazos


def test_prazos_vence_e_vencido():
    pedidos = [
        {"pedido": "1", "protocolo": "A", "assunto": "x", "enviado_em": "2026-11-07", "prazo_dias": "20", "prorrogado": "", "respondido_em": ""},
        {"pedido": "2", "protocolo": "B", "assunto": "y", "enviado_em": "2026-11-01", "prazo_dias": "20", "prorrogado": "", "respondido_em": ""},
        {"pedido": "3", "protocolo": "C", "assunto": "z", "enviado_em": "2026-11-01", "prazo_dias": "20", "prorrogado": "", "respondido_em": "2026-11-10"},
        {"pedido": "4", "protocolo": "D", "assunto": "w", "enviado_em": "2026-11-01", "prazo_dias": "20", "prorrogado": "sim", "respondido_em": ""},
    ]
    prox, venc = prazos(pedidos, date(2026, 11, 25))
    assert [p["protocolo"] for _, p in prox] == ["A"]          # vence 27/11
    assert [p["protocolo"] for _, p in venc] == ["B"]          # venceu 21/11; D foi prorrogado até 01/12; C respondido


def test_brl():
    assert brl(1270819.7) == "R$ 1.270.819,70"
