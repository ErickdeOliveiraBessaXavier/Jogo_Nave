"""Tabelas de tradução por idioma + metadados do seletor.

Fonte única dos idiomas suportados. Adicionar um idioma = criar `xx.py` com o
dict, importar aqui e registrar em `TABLES` + `LANGUAGES`.
"""

from __future__ import annotations

from .en import EN
from .pt import PT

# Idioma base / fallback quando uma chave falta ou o código é inválido.
DEFAULT_LANGUAGE = "pt"

# (código, rótulo nativo) — ordem exibida no seletor de idioma.
LANGUAGES: list[tuple[str, str]] = [
    ("pt", "Português"),
    ("en", "English"),
]

TABLES: dict[str, dict[str, str]] = {
    "pt": PT,
    "en": EN,
}
