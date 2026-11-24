"""Imagem de prévia de cada página (a que aparece quando o link é mandado no WhatsApp).

Os sites grandes de notícia e de dados mostram, na prévia, o achado da página (o número, não um logotipo). Aqui:
1200 × 630, papel do Vigia, bandeira no canto, um rótulo (de onde é), o número grande com o marca-texto rosa, a
legenda e a fonte. Feito com Pillow e as mesmas letras do site, sem navegador: rápido e igual toda vez (o mesmo
dado gera o mesmo arquivo, então o robô só republica a imagem que mudou).
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).parent / "estatico"
W, H = 1200, 630
PAPEL, TINTA, SUAVE, VERDE, BANDEIRA, MARCA = "#f3f6f2", "#0c2a1c", "#42594c", "#00753a", "#00923f", "#ff66b2"
MARGEM = 64


@lru_cache(maxsize=None)
def _letra(nome: str, tamanho: int) -> ImageFont.FreeTypeFont:
    """As letras do site estão em woff2; o Pillow lê TTF. Converte na memória."""
    f = TTFont(AQUI / "fontes" / nome)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, tamanho)


@lru_cache(maxsize=1)
def _bandeira() -> Image.Image:
    return Image.open(AQUI / "bandeira-300.png").convert("RGB").resize((132, 88), Image.LANCZOS)


def _quebrar(texto: str, fonte: ImageFont.FreeTypeFont, largura: int) -> list[str]:
    linhas, atual = [], ""
    for p in texto.split():
        tentativa = f"{atual} {p}".strip()
        if fonte.getlength(tentativa) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def gerar(destino: Path, rotulo: str, numero: str, legenda: str, fonte_txt: str, destaque: bool = True) -> None:
    img = Image.new("RGB", (W, H), PAPEL)
    d = ImageDraw.Draw(img)
    # cabeçalho: bandeira + nome
    img.paste(_bandeira(), (MARGEM, 52))
    d.rectangle((MARGEM - 1, 51, MARGEM + 132, 52 + 88), outline="#c7d4cb")
    d.text((MARGEM + 156, 58), "VIGIA CARIACICA", font=_letra("big-shoulders-900.woff2", 46), fill=TINTA)
    d.text((MARGEM + 158, 112), "FEITO POR MORADORES · SEM PARTIDO", font=_letra("courier-700.woff2", 19), fill=VERDE)
    # rótulo
    y = 196
    d.text((MARGEM, y), rotulo.upper()[:60], font=_letra("courier-700.woff2", 26), fill=VERDE)
    # número grande, do maior tamanho que couber
    largura = W - 2 * MARGEM
    tam = 150
    while tam > 60 and _letra("big-shoulders-900.woff2", tam).getlength(numero.upper()) > largura:
        tam -= 6
    fn = _letra("big-shoulders-900.woff2", tam)
    y += 44
    caixa = d.textbbox((MARGEM, y), numero.upper(), font=fn)
    meio = (caixa[1] + caixa[3]) // 2
    if destaque:   # marca-texto chapado na metade de baixo; nunca sobre o nome de uma pessoa
        d.rectangle((caixa[0] - 6, meio, caixa[2] + 8, caixa[3] + 8), fill=MARCA)
    d.text((MARGEM, y), numero.upper(), font=fn, fill=TINTA)
    # legenda
    fl = _letra("atkinson-700.woff2", 38)
    y = caixa[3] + 28
    for linha in _quebrar(legenda, fl, largura)[:3]:
        d.text((MARGEM, y), linha, font=fl, fill=TINTA)
        y += 48
    # rodapé: fonte e endereço
    d.rectangle((0, H - 70, W, H - 66), fill=BANDEIRA)
    fr = _letra("courier-400.woff2", 21)
    d.text((MARGEM, H - 50), f"Fonte: {fonte_txt}"[:70], font=fr, fill=SUAVE)
    site = "vigiacariacica.github.io"
    d.text((W - MARGEM - fr.getlength(site), H - 50), site, font=fr, fill=SUAVE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # poucas cores (o desenho é chapado): a imagem cai de ~50 KB para ~20 KB e continua nítida
    img.quantize(colors=64, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(destino, optimize=True)
