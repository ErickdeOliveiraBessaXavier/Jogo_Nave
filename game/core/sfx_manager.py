"""SfxManager: carga dos efeitos sonoros por VARREDURA de pasta (data-driven).

A **presença** de um arquivo dentro de `game/assets/audio/sfx/` é o único
registro necessário: a chave do som é o NOME DO ARQUIVO sem extensão, então
`impacts/shield_activate.wav` registra `"shield_activate"`. As subpastas
(`ui/`, `weapons/`, `impacts/`, `powerups/`, `ambience/`, `bosses/<boss>/`) são
organização humana — mover um arquivo entre elas não muda a chave nem exige
tocar em código. Mesmo contrato do `MusicLibrary`, do outro lado da árvore.

Antes daqui existiam DUAS listas à mão espelhando as mesmas chaves: o dict de
caminhos em `sound_config` e um `ui_map` neste módulo, só para carregá-las.
Esquecer um dos lados dava no-op silencioso — foi assim que `button_click`
passou a ser chamado em 19 lugares sem existir arquivo no disco. O que sobrou
declarado é o CONTRATO (`SFX_REQUIRED`/`SFX_OPTIONAL`), conferido contra o disco
por `tests/test_audio_assets.py` e logado no boot.
"""

import logging
import os
import re
from typing import Dict, List, Tuple

import pygame

from .sound_config import (
    SFX_FAMILIES,
    SFX_OPTIONAL,
    SFX_REQUIRED,
    SFX_SHOT_PREFIX,
    VOLUME_CONFIG,
)

# Mesmas extensões aceitas pela música. O build web grava conteúdo OGG mantendo
# a extensão original, e o SDL detecta pelo magic byte — por isso a lista não
# precisa mudar entre desktop e web.
AUDIO_EXTS = (".mp3", ".ogg", ".wav")


def discover_sfx(sfx_root: str) -> Dict[str, str]:
    """Varre `sfx_root` recursivamente e mapeia chave -> caminho do arquivo.

    Chave = nome do arquivo sem extensão. Duas pastas com o mesmo nome de
    arquivo é ambiguidade real (uma venceria por ordem de varredura, e qual
    depende do sistema de arquivos): loga e mantém a primeira.
    """
    encontrados: Dict[str, str] = {}
    for root, _dirs, files in os.walk(sfx_root):
        for nome in sorted(files):
            chave, ext = os.path.splitext(nome)
            if ext.lower() not in AUDIO_EXTS:
                continue
            caminho = os.path.join(root, nome)
            anterior = encontrados.get(chave)
            if anterior is not None:
                logging.warning(
                    "SfxManager: chave '%s' duplicada em duas pastas (%s e %s); "
                    "mantendo a primeira — renomeie uma delas",
                    chave,
                    anterior,
                    caminho,
                )
                continue
            encontrados[chave] = caminho
    return encontrados


def _agrupar_familias(
    sounds: Dict[str, pygame.mixer.Sound],
) -> Dict[str, List[pygame.mixer.Sound]]:
    """Monta os grupos de sorteio aleatório a partir das famílias numeradas.

    `shot_{}` recolhe `shot_1`, `shot_2`, ... em ordem NUMÉRICA (e não
    lexicográfica, que colocaria `shot_10` antes de `shot_2`).
    """
    grupos: Dict[str, List[pygame.mixer.Sound]] = {}
    for grupo, molde in SFX_FAMILIES.items():
        prefixo = molde.split("{}")[0]
        padrao = re.compile(re.escape(prefixo) + r"(\d+)$")
        membros: List[Tuple[int, str]] = []
        for chave in sounds:
            m = padrao.match(chave)
            if m:
                membros.append((int(m.group(1)), chave))
        grupos[grupo] = [sounds[chave] for _, chave in sorted(membros)]
    return grupos


def load_sfx(
    sfx_root: str, sfx_volume: float, master_volume: float
) -> Tuple[Dict[str, pygame.mixer.Sound], Dict[str, List[pygame.mixer.Sound]]]:
    """Carrega os SFX e retorna dois dicionários: (sounds, sound_groups).

    - `sounds`: chave (nome do arquivo) -> pygame.mixer.Sound
    - `sound_groups`: grupo -> list[Sound] (ex.: 'shots', 'explosions')
    """
    sounds: Dict[str, pygame.mixer.Sound] = {}
    grupos: Dict[str, List[pygame.mixer.Sound]] = {}

    if not os.path.isdir(sfx_root):
        logging.warning("SfxManager: diretório de SFX não encontrado: %s", sfx_root)
        return sounds, grupos

    for chave, caminho in discover_sfx(sfx_root).items():
        try:
            som = pygame.mixer.Sound(caminho)
        except pygame.error as e:
            logging.warning("SfxManager: erro ao carregar %s: %s", caminho, e)
            continue
        # Tiros têm escala própria, mais baixa — são disparados sem parar.
        base = (
            VOLUME_CONFIG.get("shots", 0.2)
            if chave.startswith(SFX_SHOT_PREFIX)
            else sfx_volume
        )
        som.set_volume(base * master_volume)
        sounds[chave] = som

    grupos = _agrupar_familias(sounds)

    # O contrato: som que o código espera e não está no disco vira aviso ALTO no
    # boot. Sem isso a ausência é invisível (`play_sound` é no-op em chave
    # desconhecida) — exatamente o modo de falha do `button_click`.
    for chave in sorted(SFX_REQUIRED - sounds.keys()):
        logging.error(
            "SfxManager: SFX OBRIGATÓRIO ausente: '%s' — nenhum arquivo "
            "'%s.<mp3|ogg|wav>' sob %s. O som simplesmente não vai tocar.",
            chave,
            chave,
            sfx_root,
        )
    for chave in sorted(set(SFX_OPTIONAL) - sounds.keys()):
        logging.info(
            "SfxManager: SFX opcional ausente: '%s' (%s)", chave, SFX_OPTIONAL[chave]
        )

    return sounds, grupos
