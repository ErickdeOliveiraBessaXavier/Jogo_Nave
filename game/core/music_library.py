"""MusicLibrary: descoberta de música orientada por pastas (data-driven).

A **presença** de um arquivo de áudio dentro de `themes/<tema>/` ou
`bosses/<boss>/` é o ÚNICO registro necessário — não há lista de arquivos no
código nem caminhos fixos. Adicionar um tema ou boss no futuro = criar a pasta
e soltar os arquivos; o jogo descobre tudo sozinho.

- Chave de tema  = `WorldTheme.value` (`mountains`, `starfield`, `city`, ...).
- Chave de boss  = `BOSS_TYPE_NAME` da classe do boss (`metropolis_overlord`...).

A varredura de disco só acontece na transição de música (evento raro), nunca
por frame; o resultado é cacheado por chave (`refresh()` invalida).
"""

from __future__ import annotations

import os
import random
import sys
from typing import Dict, List, Optional

# Extensões aceitas. Qualquer arquivo com uma destas dentro da pasta certa
# entra automaticamente na rotação.
AUDIO_EXTS = (".mp3", ".ogg", ".wav")


def get_resource_path(relative_path: str) -> str:
    """Resolve path no modo dev e no executável (PyInstaller `_MEIPASS`).

    Fora do PyInstaller, resolve contra a RAIZ DO PROJETO (derivada de
    ``__file__``), não o CWD — senão a build rodada de outro diretório (ex.:
    Downloads) não acha os assets de áudio e a música some. Ver o mesmo fix em
    `sound.get_resource_path` e no BASE_DIR das imagens.
    """
    # game/core/music_library.py → 3 dirnames = raiz do projeto (contém "game/").
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    base_path = getattr(sys, "_MEIPASS", project_root)
    return os.path.join(base_path, relative_path)


class MusicLibrary:
    """Descobre faixas por pasta, com cache por chave.

    `themes_root`/`bosses_root` são caminhos RELATIVOS à raiz do projeto
    (ex.: ``game/assets/audio/music/themes``); a resolução absoluta/PyInstaller é
    feita internamente por `get_resource_path`.
    """

    def __init__(self, themes_root: str, bosses_root: str, menu_root: str) -> None:
        self._themes_root = themes_root
        self._bosses_root = bosses_root
        self._menu_root = menu_root
        self._theme_cache: Dict[str, List[str]] = {}
        self._boss_cache: Dict[str, List[str]] = {}
        self._menu_cache: Optional[List[str]] = None

    def theme_tracks(self, key: Optional[str]) -> List[str]:
        """Faixas (paths absolutos) do tema `key`; `[]` se a pasta não existir/vazia."""
        return self._keyed(self._theme_cache, self._themes_root, key)

    def boss_tracks(self, key: Optional[str]) -> List[str]:
        """Faixas (paths absolutos) do boss `key`; `[]` se a pasta não existir/vazia."""
        return self._keyed(self._boss_cache, self._bosses_root, key)

    def menu_tracks(self) -> List[str]:
        """Faixas da pasta PLANA do menu (sem chave); `[]` se não existir/vazia."""
        if self._menu_cache is None:
            self._menu_cache = self._scan_dir(get_resource_path(self._menu_root))
        return self._menu_cache

    def refresh(self) -> None:
        """Invalida o cache (re-varre na próxima consulta). Útil em hot-reload/testes."""
        self._theme_cache.clear()
        self._boss_cache.clear()
        self._menu_cache = None

    def _keyed(
        self, cache: Dict[str, List[str]], root: str, key: Optional[str]
    ) -> List[str]:
        if not key:
            return []
        cached = cache.get(key)
        if cached is not None:
            return cached
        tracks = self._scan_dir(get_resource_path(os.path.join(root, key)))
        cache[key] = tracks
        return tracks

    @staticmethod
    def _scan_dir(folder: str) -> List[str]:
        tracks: List[str] = []
        try:
            for name in sorted(os.listdir(folder)):
                if name.lower().endswith(AUDIO_EXTS):
                    full = os.path.join(folder, name)
                    if os.path.isfile(full):
                        tracks.append(full)
        except (FileNotFoundError, NotADirectoryError, OSError):
            return []
        return tracks


class TrackRotation:
    """Rotação aleatória SEM repetição imediata sobre uma lista de faixas.

    Embaralha o ciclo; ao reembaralhar garante que a 1ª faixa do novo ciclo
    seja diferente da última tocada (a menos que só exista uma faixa). Com uma
    única faixa, devolve sempre ela.
    """

    def __init__(self, tracks: List[str]) -> None:
        self._tracks: List[str] = list(tracks)
        self._order: List[str] = []
        self._idx = 0
        self._last: Optional[str] = None
        self._reshuffle()

    def matches(self, tracks: List[str]) -> bool:
        """True se a rotação foi montada exatamente sobre `tracks` (mesma ordem)."""
        return self._tracks == list(tracks)

    def _reshuffle(self) -> None:
        self._order = list(self._tracks)
        random.shuffle(self._order)
        if len(self._order) > 1 and self._order[0] == self._last:
            # Empurra a repetida para o fim — evita tocar a mesma faixa em seguida.
            self._order.append(self._order.pop(0))
        self._idx = 0

    def next(self) -> Optional[str]:
        if not self._tracks:
            return None
        if self._idx >= len(self._order):
            self._reshuffle()
        track = self._order[self._idx]
        self._idx += 1
        self._last = track
        return track
