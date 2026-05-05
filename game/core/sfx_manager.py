"""SfxManager: carregamento e reprodução de efeitos sonoros (SFX).

Esta classe é responsável por carregar os recursos de SFX a partir de
`sound_config.SOUND_PATHS` e expor uma função utilitária para preencher os
dicionários `_sounds` e `_sound_groups` usados pelo `SoundManager`.

O objetivo é permitir uma futura separação completa entre efeitos e música
sem quebrar a API existente durante a migração.
"""

import logging
import os
from typing import Any, Dict, List, Tuple, cast

import pygame

from .sound_config import SOUND_PATHS, VOLUME_CONFIG


def load_sfx(
    base_path: str, sfx_volume: float, master_volume: float
) -> Tuple[Dict[str, pygame.mixer.Sound], Dict[str, List[pygame.mixer.Sound]]]:
    """Carrega os SFX e retorna dois dicionários: (sounds, sound_groups).

    - `sounds`: mapeia nome -> pygame.mixer.Sound
    - `sound_groups`: mapeia grupo -> list[Sound] (ex.: 'shots', 'explosions')
    """
    sounds: Dict[str, pygame.mixer.Sound] = {}
    sound_groups: Dict[str, List[pygame.mixer.Sound]] = {}

    if not os.path.exists(base_path):
        logging.warning("SfxManager: diretório de sons não encontrado: %s", base_path)
        return sounds, sound_groups

    sfx_paths = cast(Dict[str, Any], SOUND_PATHS["sfx"])

    # Shots
    shot_sounds: List[pygame.mixer.Sound] = []
    shot_template = sfx_paths.get("shots", "")
    for i in range(1, 4):
        path = os.path.join(base_path, shot_template.format(i))
        if os.path.exists(path):
            try:
                s = pygame.mixer.Sound(path)
                s.set_volume(VOLUME_CONFIG.get("shots", 0.2) * master_volume)
                shot_sounds.append(s)
                sounds[f"shot_{i}"] = s
            except pygame.error as e:
                logging.warning("SfxManager: erro ao carregar %s: %s", path, e)
    sound_groups["shots"] = shot_sounds

    # Explosions (multiple)
    explosion_sounds: List[pygame.mixer.Sound] = []
    explosion_paths = sfx_paths.get("explosions", {})
    asteroid_template = explosion_paths.get("asteroid", "")
    for i in range(4):
        path = os.path.join(base_path, asteroid_template.format(i))
        if os.path.exists(path):
            try:
                s = pygame.mixer.Sound(path)
                s.set_volume(sfx_volume * master_volume)
                explosion_sounds.append(s)
                sounds[f"explosion_asteroid_{i}"] = s
            except pygame.error as e:
                logging.warning("SfxManager: erro ao carregar %s: %s", path, e)

    other_explosions = {
        "explosion_alien": explosion_paths.get("alien"),
        "explosion_boss": explosion_paths.get("boss"),
        "boss_damage": explosion_paths.get("boss_damage"),
        "ship_explosion": explosion_paths.get("ship"),
    }
    for key, rel in other_explosions.items():
        if not rel:
            continue
        path = os.path.join(base_path, rel)
        if os.path.exists(path):
            try:
                s = pygame.mixer.Sound(path)
                s.set_volume(sfx_volume * master_volume)
                sounds[key] = s
            except pygame.error as e:
                logging.warning("SfxManager: erro ao carregar %s: %s", path, e)

    sound_groups["explosions"] = explosion_sounds

    # UI sounds
    ui = sfx_paths.get("ui", {})
    ui_map = {
        "warning": ui.get("warning"),
        "powerup": ui.get("powerup"),
        "button_hover": ui.get("button_hover"),
        "button_click": ui.get("button_click"),
        "upgrade_activate": ui.get("upgrade_activate"),
        "laser_shot": ui.get("laser_shot"),
        "black_hole": ui.get("black_hole"),
        "hit_hurt_meteor_boss": ui.get("hit_hurt_meteor_boss"),
    }
    for key, rel in ui_map.items():
        if not rel:
            continue
        path = os.path.join(base_path, rel)
        if os.path.exists(path):
            try:
                s = pygame.mixer.Sound(path)
                s.set_volume(sfx_volume * master_volume)
                sounds[key] = s
            except pygame.error as e:
                logging.warning("SfxManager: erro ao carregar %s: %s", path, e)

    # Meteor rain variants
    meteor_list: List[pygame.mixer.Sound] = []
    meteor_pattern = ui.get("meteor_rain", "")
    if meteor_pattern:
        for i in range(1, 5):
            path = os.path.join(base_path, meteor_pattern.format(i))
            if os.path.exists(path):
                try:
                    s = pygame.mixer.Sound(path)
                    s.set_volume(sfx_volume * master_volume)
                    meteor_list.append(s)
                except pygame.error as e:
                    logging.warning("SfxManager: erro ao carregar %s: %s", path, e)
    sound_groups["meteor_rain"] = meteor_list

    # Boss laser sounds
    laser_map = {
        "boss_laser_charging": sfx_paths.get("boss_laser_charging"),
        "boss_laser_fire": sfx_paths.get("boss_laser_fire"),
        "spike_boss_laser": sfx_paths.get("spike_boss_laser"),
    }
    for key, rel in laser_map.items():
        if not rel:
            continue
        path = os.path.join(base_path, rel)
        if os.path.exists(path):
            try:
                s = pygame.mixer.Sound(path)
                s.set_volume(sfx_volume * master_volume)
                sounds[key] = s
            except pygame.error as e:
                logging.warning("SfxManager: erro ao carregar %s: %s", path, e)

    return sounds, sound_groups
