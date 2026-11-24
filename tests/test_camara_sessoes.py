"""Transcrição das sessões da Câmara: horário do trecho vira horário do vídeo; data sai do título."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / 'ferramentas' / 'camara_sessoes' / 'transcrever.py'
_spec = importlib.util.spec_from_file_location('transcrever', _p)
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)


def test_horario_do_trecho_vira_horario_do_video():
    texto = "[00:05] Presidente: Abertos os trabalhos.\n[12:30] Vereador Fulano: Peço a palavra\ncontinuando a fala.\n[1:02:03] Morador(a): Obrigado."
    linhas = tr.deslocar(texto, 2400)
    assert linhas[0] == '[00:40:05] Presidente: Abertos os trabalhos.'
    assert linhas[1] == '[00:52:30] Vereador Fulano: Peço a palavra continuando a fala.'
    assert linhas[2] == '[01:42:03] Morador(a): Obrigado.'


def test_data_da_sessao_pelo_titulo():
    assert tr.data_do_titulo('Sessão Ordinária da Câmara de Vereadores de Cariacica - ES  (11/11/2026)') == '2026-11-11'
    assert tr.data_do_titulo('Audiência Pública do RREO') == ''
