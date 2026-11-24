"""Mensagens simples no terminal."""
import datetime as _dt
import sys


def _agora():
    return _dt.datetime.now().strftime("%H:%M:%S")


def info(msg: str) -> None:
    print(f"[{_agora()}] {msg}", flush=True)


def aviso(msg: str) -> None:
    print(f"[{_agora()}] ATENÇÃO: {msg}", file=sys.stderr, flush=True)


def etapa(msg: str) -> None:
    print(f"\n[{_agora()}] === {msg} ===", flush=True)
