"""Normalização de textos, nomes, unidades e comparação de descrições de itens."""
from __future__ import annotations

import re
import unicodedata

PARADAS = set("""
a o e de da do das dos em para por com sem na no nas nos um uma uns umas ao aos à às
tipo marca modelo ref referencia referência conforme especificacao especificação
termo descricao descrição minimo mínimo maximo máximo aproximadamente aprox cerca
unidade und un unid item itens produto produtos material materiais similar ou equivalente
qualidade primeira linha cor deve devera deverá ser sera será possuir contendo contem contém
""".split())

UNIDADES = {
    "UN": {"UN", "UND", "UNID", "UNIDADE", "UNIDADES", "UNI", "UNT", "PC", "PECA", "PEÇA", "PÇ"},
    "KG": {"KG", "KILO", "QUILO", "QUILOGRAMA", "KGS"},
    "G": {"G", "GR", "GRAMA", "GRAMAS"},
    "L": {"L", "LT", "LITRO", "LITROS", "LTS"},
    "ML": {"ML", "MILILITRO", "MILILITROS"},
    "CX": {"CX", "CAIXA", "CAIXAS"},
    "PCT": {"PCT", "PACOTE", "PACOTES", "PC.", "PCTE"},
    "FD": {"FD", "FARDO", "FARDOS"},
    "M": {"M", "METRO", "METROS", "MT", "ML."},
    "M2": {"M2", "M²", "METRO QUADRADO", "METROS QUADRADOS"},
    "M3": {"M3", "M³", "METRO CUBICO", "METROS CUBICOS"},
    "RESMA": {"RESMA", "RESMAS", "RS"},
    "GL": {"GL", "GALAO", "GALÃO", "GALOES"},
    "FR": {"FR", "FRASCO", "FRASCOS"},
    "AMP": {"AMP", "AMPOLA", "AMPOLAS"},
    "CP": {"CP", "COMP", "COMPRIMIDO", "COMPRIMIDOS"},
    "SC": {"SC", "SACO", "SACOS"},
    "DZ": {"DZ", "DUZIA", "DÚZIA", "DUZIAS"},
    "ROLO": {"ROLO", "ROLOS", "RL"},
    "PAR": {"PAR", "PARES"},
    "KIT": {"KIT", "KITS"},
    "BD": {"BD", "BALDE", "BALDES"},
    "LATA": {"LATA", "LATAS", "LT."},
    "TB": {"TB", "TUBO", "TUBOS", "BISNAGA"},
    "MES": {"MES", "MÊS", "MESES", "MENSAL"},
    "HORA": {"H", "HR", "HORA", "HORAS"},
    "DIA": {"DIA", "DIAS", "DIARIA", "DIÁRIA", "DIARIAS"},
    "SERV": {"SERVICO", "SERVIÇO", "SV", "SERV"},
}
_UNID_MAPA = {v: k for k, vs in UNIDADES.items() for v in vs}


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar(s: str | None) -> str:
    if not s:
        return ""
    s = sem_acento(s).lower()
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    s = re.sub(r"(\d)\s+(ml|l|kg|g|mg|mm|cm|m|w|v|gb|mb)\b", r"\1\2", s)
    s = re.sub(r"[^a-z0-9.%]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str | None) -> set[str]:
    return {t.strip(".") for t in normalizar(s).split()
            if t.strip(".") and t.strip(".") not in PARADAS and len(t.strip(".")) > 1}


def numeros(tks: set[str]) -> frozenset[str]:
    """Tokens com número (500ml, 1kg, 40w...) precisam bater exatamente."""
    return frozenset(t for t in tks if re.search(r"\d", t))


def unidade(s: str | None) -> str:
    if not s:
        return "?"
    u = sem_acento(s).upper().strip().rstrip(".")
    u = re.sub(r"\s+", " ", u)
    if u in _UNID_MAPA:
        return _UNID_MAPA[u]
    primeiro = u.split(" ")[0].split("/")[0]
    return _UNID_MAPA.get(primeiro, u[:12])


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def nome_pessoa(s: str | None) -> str:
    """Normaliza nome de pessoa para comparação (sem acento, maiúsculo, sem 'de/da/dos')."""
    if not s:
        return ""
    s = sem_acento(s).upper()
    s = re.sub(r"[^A-Z ]+", " ", s)
    partes = [p for p in s.split() if p not in {"DE", "DA", "DO", "DAS", "DOS", "E"}]
    return " ".join(partes)


def endereco(logr, num, cep) -> str:
    base = normalizar(f"{logr or ''} {num or ''}")
    base = re.sub(r"\b(rua|r|avenida|av|rodovia|rod|travessa|tv|estrada|est)\b", "", base)
    cep = re.sub(r"\D", "", cep or "")
    base = re.sub(r"\s+", " ", base).strip()
    return f"{base}|{cep}" if (base or cep) else ""


def so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def mascarar_cpf(doc: str | None) -> str:
    d = so_digitos(doc)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    return doc or ""


def formatar_cnpj(doc: str | None) -> str:
    d = so_digitos(doc)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return mascarar_cpf(d)
    return doc or ""


def reais(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v, casas=0) -> str:
    """0.403 -> '40%'; com casas=1 -> '40,3%'"""
    return f"{v * 100:.{casas}f}%".replace(".", ",")


def fator(v) -> str:
    """2.07 -> '2,1x'"""
    return f"{v:.1f}x".replace(".", ",")


# ---------------------------------------------------------------- LGPD: CPF nunca sai inteiro
_CPF_FORMATADO = re.compile(r"(?<!\d)(\d{3})\.(\d{3})\.(\d{3})-(\d{2})(?!\d)")
_ONZE_DIGITOS = re.compile(r"(?<![\d./-])(\d{11})(?![\d/-])")


def cpf_valido(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def mascarar_cpfs(texto):
    """Mascara todo CPF válido (formatado ou 11 dígitos seguidos) dentro de um texto livre:
    '039.212.345-67' ou '03921234567' -> '***.212.345-**'. Usado em tudo que vai para o git.
    Números de 11 dígitos que não passam no dígito verificador (telefone, processo) ficam como estão."""
    if not isinstance(texto, str) or not texto:
        return texto

    def fmt(m):
        d = "".join(m.groups())
        return f"***.{d[3:6]}.{d[6:9]}-**" if cpf_valido(d) else m.group(0)

    def bare(m):
        d = m.group(1)
        return f"***.{d[3:6]}.{d[6:9]}-**" if cpf_valido(d) else d

    return _ONZE_DIGITOS.sub(bare, _CPF_FORMATADO.sub(fmt, texto))


def tem_cpf(texto: str) -> bool:
    """Há algum CPF inteiro e válido no texto? (ignora números com casas decimais: são valores)"""
    limpo = re.sub(r"(?<![\d])\d{1,13}\.\d{1,2}(?![\d])", "", texto)
    return any(cpf_valido("".join(m.groups())) for m in _CPF_FORMATADO.finditer(limpo)) or \
        any(cpf_valido(m.group(1)) for m in _ONZE_DIGITOS.finditer(limpo))
