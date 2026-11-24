import pytest

from vigia import qualidade


@pytest.fixture(autouse=True)
def _fontes_fora_isolado(tmp_path, monkeypatch):
    """Nenhum teste mexe no data/qualidade/fontes_fora.csv de verdade."""
    monkeypatch.setattr(qualidade, "FORA", tmp_path / "fontes_fora.csv")
