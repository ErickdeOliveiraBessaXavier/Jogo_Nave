"""MusicManager: lógica de música e transições do jogo.

Este módulo isola a reprodução de música, estado de transição e controle de
fade para reduzir o tamanho e a responsabilidade do `SoundManager`.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import threading
import time
from typing import TYPE_CHECKING, Dict, List, Union, cast

import pygame

from .sound_config import (BEHAVIOR_CONFIG, MUSIC_BEHAVIOR_CONFIG, SOUND_PATHS,
                           MusicState)

if TYPE_CHECKING:
    from .sound import SoundManager


MusicPaths = Dict[str, Union[str, List[str]]]


def get_resource_path(relative_path: str) -> str:
    """Resolve resource path no modo dev e executável."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


class MusicStateManager:
    def __init__(self, manager: "MusicManager"):
        self.music_manager = manager
        self.current_state: MusicState = MusicState.SILENCE
        self.previous_state: MusicState = MusicState.SILENCE

    def reset(self) -> None:
        self.current_state = MusicState.SILENCE
        self.previous_state = MusicState.SILENCE
        self.music_manager.stop_music_internal()

    def transition_to(self, new_state: MusicState, force: bool = False) -> bool:
        if not force and self._should_block_transition(new_state):
            return False

        self.previous_state = self.current_state
        self._execute_transition(new_state)
        self.current_state = new_state
        return True

    def _should_block_transition(self, new_state: MusicState) -> bool:
        if not MUSIC_BEHAVIOR_CONFIG["prevent_menu_over_game"]:
            return False

        game_music_types = [
            MusicState.GAME,
            MusicState.BOSS,
            MusicState.SPIKE_BOSS,
            MusicState.SLIME_BOSS,
            MusicState.GIANT_METEOR_BOSS,
            MusicState.MOUNTAIN_SERPENT_BOSS,
            MusicState.CLOUD_ARCHMAGE_BOSS,
            MusicState.STONE_GOLEM_BOSS,
        ]

        is_music_paused = bool(
            getattr(self.music_manager.sound_manager, "music_paused", False)
        )
        is_game_music_active = self.current_state in game_music_types or (
            is_music_paused and self.previous_state in game_music_types
        )

        return new_state == MusicState.MENU and is_game_music_active

    def _execute_transition(self, new_state: MusicState) -> None:
        if self.current_state == new_state:
            return

        if new_state == MusicState.MENU:
            self.music_manager.play_menu_music_internal()
        elif new_state == MusicState.GAME:
            self.music_manager.play_background_music_internal()
        elif new_state == MusicState.BOSS:
            self.music_manager.play_boss_music_internal()
        elif new_state == MusicState.SPIKE_BOSS:
            self.music_manager.play_spike_boss_music_internal()
        elif new_state == MusicState.SLIME_BOSS:
            self.music_manager.play_slime_boss_music_internal()
        elif new_state == MusicState.GIANT_METEOR_BOSS:
            self.music_manager.play_giant_meteor_boss_music_internal()
        elif new_state == MusicState.MOUNTAIN_SERPENT_BOSS:
            self.music_manager.play_mountain_serpent_boss_music_internal()
        elif new_state == MusicState.CLOUD_ARCHMAGE_BOSS:
            self.music_manager.play_cloud_archmage_boss_music_internal()
        elif new_state == MusicState.STONE_GOLEM_BOSS:
            self.music_manager.play_stone_golem_boss_music_internal()
        elif new_state == MusicState.SILENCE:
            self.music_manager.stop_music_internal()

    def pause_current(self) -> None:
        self.music_manager.pause_music_internal()

    def resume_current(self) -> None:
        self.music_manager.resume_music_internal()


class MusicManager:
    def __init__(self, sound_manager: "SoundManager") -> None:
        self.sound_manager = sound_manager
        self.music_state_manager = MusicStateManager(self)

    def _music_paths(self) -> MusicPaths:
        return cast(MusicPaths, SOUND_PATHS["music"])

    def play_background_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.GAME)

    def play_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.BOSS)

    def play_spike_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.SPIKE_BOSS)

    def play_slime_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.SLIME_BOSS)

    def play_giant_meteor_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.GIANT_METEOR_BOSS)

    def play_mountain_serpent_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.MOUNTAIN_SERPENT_BOSS)

    def play_cloud_archmage_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.CLOUD_ARCHMAGE_BOSS)

    def play_stone_golem_boss_music(self) -> None:
        self.music_state_manager.transition_to(MusicState.STONE_GOLEM_BOSS)

    def play_menu_music(self, force: bool = False) -> None:
        self.music_state_manager.transition_to(MusicState.MENU, force=force)

    def pause_music(self) -> None:
        self.music_state_manager.pause_current()

    def resume_music(self) -> None:
        self.music_state_manager.resume_current()

    def stop_music(self, force: bool = False) -> None:
        self.music_state_manager.transition_to(MusicState.SILENCE, force=force)

    def play_background_music_internal(self) -> None:
        background_music_list = self._music_paths()["background"]
        if isinstance(background_music_list, list) and background_music_list:
            chosen_music = random.choice(background_music_list)
            music_path = get_resource_path(
                os.path.join(str(SOUND_PATHS["base"]), chosen_music)
            )
            if (
                os.path.exists(music_path)
                and self.sound_manager.current_music != chosen_music
            ):
                self._transition_to_music(music_path, "background")

    def play_boss_music_internal(self) -> None:
        music_path = get_resource_path(
            os.path.join(str(SOUND_PATHS["base"]), str(self._music_paths()["boss"]))
        )
        if os.path.exists(music_path) and self.sound_manager.current_music != "boss":
            self._transition_to_music(music_path, "boss")

    def _play_boss_music_by_key(self, key: str) -> None:
        """Generic handler for all boss music playback."""
        music_path = get_resource_path(
            os.path.join(str(SOUND_PATHS["base"]), str(self._music_paths()[key]))
        )
        if os.path.exists(music_path) and self.sound_manager.current_music != key:
            self._transition_to_music(music_path, key)

    def play_spike_boss_music_internal(self) -> None:
        self._play_boss_music_by_key("spike_boss")

    def play_slime_boss_music_internal(self) -> None:
        self._play_boss_music_by_key("slime_boss")

    def play_giant_meteor_boss_music_internal(self) -> None:
        self._play_boss_music_by_key("giant_meteor_boss")

    def play_mountain_serpent_boss_music_internal(self) -> None:
        self._play_boss_music_by_key("mountain_serpent_boss")

    def play_cloud_archmage_boss_music_internal(self) -> None:
        self._play_boss_music_by_key("cloud_archmage_boss")

    def play_stone_golem_boss_music_internal(self) -> None:
        self._play_boss_music_by_key("stone_golem_boss")

    def play_menu_music_internal(self) -> None:
        music_path = get_resource_path(
            os.path.join(str(SOUND_PATHS["base"]), str(self._music_paths()["menu"]))
        )
        if os.path.exists(music_path) and self.sound_manager.current_music != "menu":
            self._transition_to_music(music_path, "menu")

    def pause_music_internal(self) -> None:
        if not self.sound_manager.music_paused:
            pygame.mixer.music.pause()
            self.sound_manager.music_paused = True

    def resume_music_internal(self) -> None:
        if self.sound_manager.music_paused:
            pygame.mixer.music.unpause()
            self.sound_manager.music_paused = False

    def stop_music_internal(self) -> None:
        pygame.mixer.music.stop()
        self.sound_manager.current_music = None
        self.sound_manager.music_paused = False

    def set_music_volume(self, volume: float) -> None:
        self.sound_manager.music_volume = max(0.0, min(1.0, volume))

        if self.sound_manager.current_music in [
            "boss",
            "spike_boss",
            "slime_boss",
            "giant_meteor_boss",
            "mountain_serpent_boss",
            "cloud_archmage_boss",
            "stone_golem_boss",
        ]:
            boss_volume = (
                self.sound_manager.music_volume
                * self.sound_manager.boss_music_multiplier
            )
            final_volume = min(1.0, boss_volume)
            pygame.mixer.music.set_volume(
                final_volume * self.sound_manager.master_volume
            )
        elif self.sound_manager.current_music is not None:
            pygame.mixer.music.set_volume(
                self.sound_manager.music_volume * self.sound_manager.master_volume
            )

    def load_config(
        self, music_vol: float, sfx_volume: float, shot_volume: float
    ) -> None:
        self.sound_manager.music_volume = max(0.0, min(1.0, music_vol))
        self.sound_manager.sfx_volume = max(0.0, min(1.0, sfx_volume))
        self.sound_manager.shot_volume_base = max(0.0, min(1.0, shot_volume))

        if self.sound_manager.current_music is not None:
            base_volume = self.sound_manager.music_volume
            if self.sound_manager.current_music in [
                "boss",
                "spike_boss",
                "slime_boss",
                "mountain_serpent_boss",
                "cloud_archmage_boss",
            ]:
                base_volume *= self.sound_manager.boss_music_multiplier
            pygame.mixer.music.set_volume(
                min(1.0, base_volume * self.sound_manager.master_volume)
            )

    def _transition_to_music(self, music_path: str, music_type: str) -> None:
        if (
            self.sound_manager.transition_thread
            and self.sound_manager.transition_thread.is_alive()
        ):
            pygame.mixer.music.stop()
            self.sound_manager.transition_thread.join()

        self.sound_manager.transition_thread = threading.Thread(
            target=self._smooth_transition,
            args=(music_path, music_type),
            daemon=True,
        )
        self.sound_manager.transition_thread.start()

    def _smooth_transition(self, music_path: str, music_type: str) -> None:
        with self.sound_manager.transition_lock:
            fade_duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.fadeout(int(fade_duration * 1000))
                    time.sleep(fade_duration)

                pygame.mixer.music.load(music_path)

                base_volume = self.sound_manager.music_volume
                if music_type in [
                    "boss",
                    "spike_boss",
                    "slime_boss",
                    "giant_meteor_boss",
                    "mountain_serpent_boss",
                    "cloud_archmage_boss",
                    "stone_golem_boss",
                ]:
                    base_volume *= self.sound_manager.boss_music_multiplier

                target_volume = min(1.0, base_volume * self.sound_manager.master_volume)

                pygame.mixer.music.set_volume(0)
                pygame.mixer.music.play(-1)

                fade_steps = 20
                step_duration = fade_duration / fade_steps
                for i in range(fade_steps):
                    volume = target_volume * (i + 1) / fade_steps
                    pygame.mixer.music.set_volume(volume)
                    time.sleep(step_duration)

                pygame.mixer.music.set_volume(target_volume)
                self.sound_manager.current_music = music_type
                self.sound_manager.music_paused = False
            except pygame.error as e:
                logging.error("Erro na transição de música: %s", e)

    def fade_out_music(self, duration: float | None = None) -> None:
        if duration is None:
            duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])

        pygame.mixer.music.fadeout(int(duration * 1000))
        self.sound_manager.current_music = None
        self.sound_manager.music_paused = False

    def play_warning(self) -> None:
        # Stop any previous warning playback on the dedicated channel
        # and play the warning SFX on that channel so it can be reliably stopped
        # by `stop_warning()` later.
        self.sound_manager.warning_channel.stop()
        snd = None
        # Use public accessor instead of touching protected `_sounds`
        if hasattr(self.sound_manager, "get_sound"):
            snd = self.sound_manager.get_sound("warning")
        else:
            # Fallback for older versions: access internal dict (best-effort)
            snd = getattr(self.sound_manager, "_sounds", {}).get("warning")
        if snd:
            snd.set_volume(
                self.sound_manager.sfx_volume * self.sound_manager.master_volume
            )
            # Loop the warning sound while the warning stage is active.
            # It will be stopped explicitly via `stop_warning()`.
            try:
                self.sound_manager.warning_channel.play(snd, loops=-1)
            except Exception:  # pylint: disable=broad-exception-caught
                # Fallback to a single play if channel play fails
                snd.play()

    def play_powerup(self) -> None:
        self.sound_manager.play_sound("powerup")

    def stop_warning(self) -> None:
        self.sound_manager.warning_channel.stop()
