"""Análise assistida por IA (opcional). Usa a API da Anthropic (Claude).

Precisa de:  pip install anthropic   e a variável de ambiente ANTHROPIC_API_KEY.
A IA recebe SÓ o dossiê (dados públicos) e devolve uma segunda opinião em linguagem simples.
Ela pode errar: trate a resposta como sugestão, nunca como conclusão.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import dossie

INSTRUCOES = """Você ajuda um cidadão a fazer controle social de contratações públicas municipais no Brasil.
Você vai receber um dossiê gerado automaticamente a partir de dados públicos (PNCP, Receita Federal, CGU).
Responda em português, de forma clara e objetiva, com estas seções:
1. O que os dados mostram de fato (sem exagero).
2. Explicações legítimas plausíveis, da mais para a menos provável.
3. O que conferir no processo e quais documentos pedir, em ordem de prioridade.
4. Avaliação: este indício merece prioridade alta, média ou baixa de investigação, e por quê.
Regras: nunca afirme que houve crime ou corrupção; fale em indícios. Aponte se os dados parecem ter
erro de lançamento. Não invente fatos que não estão no dossiê. Cite os artigos de lei apenas se tiver certeza."""


def analisar(con, cfg, id_alerta: str) -> Path:
    try:
        import anthropic
    except ImportError as e:
        raise SystemExit("Instale a biblioteca: pip install anthropic") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Defina a variável de ambiente ANTHROPIC_API_KEY com sua chave da API da Anthropic.")
    texto = dossie.montar(con, id_alerta)
    cliente = anthropic.Anthropic()
    resp = cliente.messages.create(
        model=cfg.get("ia", {}).get("modelo", "claude-sonnet-5-5"),
        max_tokens=2500,
        system=INSTRUCOES,
        messages=[{"role": "user", "content": texto}],
    )
    analise = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    pasta = Path(cfg["_pasta_dados"]).parent / "saida" / "dossies"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"analise_ia_{id_alerta}.md"
    destino.write_text(f"# Análise assistida por IA — alerta {id_alerta}\n\n"
                       f"_Segunda opinião automática. Pode conter erros._\n\n{analise}\n", encoding="utf-8")
    return destino
