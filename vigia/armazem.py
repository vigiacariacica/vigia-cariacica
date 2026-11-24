"""Leitura e gravação dos dados em CSV versionado no repositório.

CSV foi escolhido de propósito: qualquer cidadão abre no Excel, e o
histórico do git mostra exatamente o que mudou em cada coleta.
Toda gravação passa pelo mascaramento de CPF (vigia.texto.mascarar_cpfs).
"""
from pathlib import Path

import pandas as pd

from .texto import mascarar_cpfs


def ler(caminho: Path) -> pd.DataFrame:
    if caminho.exists() and caminho.stat().st_size > 0:
        return pd.read_csv(caminho, dtype=str, keep_default_na=False)
    return pd.DataFrame()


def gravar(df: pd.DataFrame, caminho: Path, chave: list[str] | None = None,
           ordenar: list[str] | None = None) -> pd.DataFrame:
    """Grava o DataFrame, removendo duplicados pela chave (mantém o mais recente)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df = df.astype(str)
    # LGPD: nenhum CPF inteiro vai para o git, nem dentro de nomes ou descrições.
    for col in df.columns:
        if not col.lower().startswith("valor"):
            df[col] = df[col].map(mascarar_cpfs)
    if chave:
        chave = [c for c in chave if c in df.columns]
        if chave:
            df = df.drop_duplicates(subset=chave, keep="last")
    if ordenar:
        ordenar = [c for c in ordenar if c in df.columns]
        if ordenar:
            df = df.sort_values(ordenar, kind="stable")
    df.to_csv(caminho, index=False)
    return df


def juntar(antigo: pd.DataFrame, novo: pd.DataFrame) -> pd.DataFrame:
    if antigo.empty:
        return novo
    if novo.empty:
        return antigo
    return pd.concat([antigo, novo.astype(str)], ignore_index=True)
