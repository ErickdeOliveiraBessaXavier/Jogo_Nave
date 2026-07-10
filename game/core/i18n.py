"""Internacionalização (i18n) — política única de tradução do jogo.

Singleton mutável `i18n` (mesmo padrão de `visual_quality`/`sound_manager`):
estado de idioma aplicado no boot a partir de `UserPreferences.language`, lido
por frame pelas telas via a função livre `t(key, **kwargs)`.

Uso (one-liner por call site):

    from ..core.i18n import t
    label = t("menu.start")             # "Iniciar Jogo" / "Start Game"
    msg   = t("hud.level", n=level)     # interpolação de valores dinâmicos

Fallback em cascata: idioma atual → idioma base (`DEFAULT_LANGUAGE`) → a própria
chave. Nunca lança nem retorna None — uma chave faltando degrada, não quebra a
tela. Importar em `game/core/*`/`scenes/*`/`entities/*` não cria ciclo (core não
depende de game).
"""

from __future__ import annotations

from .translations import DEFAULT_LANGUAGE, TABLES


class I18n:
    """Resolve traduções pelo idioma atual, com fallback seguro."""

    def __init__(self) -> None:
        self._language = DEFAULT_LANGUAGE
        self._table = TABLES[DEFAULT_LANGUAGE]

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, code: str) -> None:
        """Aplica o idioma por código ('pt'/'en'); inválido → idioma base."""
        key = str(code).lower()
        self._language = key if key in TABLES else DEFAULT_LANGUAGE
        self._table = TABLES[self._language]

    def t(self, key: str, **kwargs: object) -> str:
        """Traduz `key` no idioma atual; interpola `**kwargs` via str.format."""
        text = self._table.get(key)
        if text is None:
            # Cascata: idioma base e, por fim, a própria chave (visível = pega bug).
            text = TABLES[DEFAULT_LANGUAGE].get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def has(self, key: str) -> bool:
        """True se a chave existe no idioma atual ou no base."""
        return key in self._table or key in TABLES[DEFAULT_LANGUAGE]

    def t_or(self, key: str, default: str, **kwargs: object) -> str:
        """Como `t`, mas retorna `default` se a chave não existir (dados dinâmicos
        sem tradução, ex.: mundos procedurais)."""
        if self.has(key):
            return self.t(key, **kwargs)
        return default

    def format_number(self, value: int) -> str:
        """Formata inteiro com separador de milhar do idioma (PT: '.', EN: ',')."""
        grouped = f"{int(value):,}"  # padrão com vírgula
        if self._language == "pt":
            return grouped.replace(",", ".")
        return grouped


# Singleton global (mesmo padrão de `sound_manager`/`visual_quality`).
i18n = I18n()


def t(key: str, **kwargs: object) -> str:
    """Atalho livre para `i18n.t` — o call site típico nas telas."""
    return i18n.t(key, **kwargs)


def t_or(key: str, default: str, **kwargs: object) -> str:
    """Atalho livre para `i18n.t_or` (traduz com fallback a um default externo)."""
    return i18n.t_or(key, default, **kwargs)


def fmt_num(value: int) -> str:
    """Atalho livre para `i18n.format_number` (score, contadores etc.)."""
    return i18n.format_number(value)
