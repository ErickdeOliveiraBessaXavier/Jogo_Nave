from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pygame

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.sfx_manager import load_sfx
from game.core.sound import AudioController, SoundManager
from game.core.sound_config import SOUND_PATHS
from game.entities.mountain_serpent_boss import MountainSerpentBoss


class _FakeSound:
    def __init__(self, path: str) -> None:
        self.path = path
        self.volume = None
        self.play_calls = 0
        self.stop_calls = 0

    def set_volume(self, volume: float) -> None:
        self.volume = volume

    def play(self) -> None:
        self.play_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


def test_load_sfx_pulls_button_click_and_groups(monkeypatch, tmp_path: Path) -> None:
    base_path = tmp_path / "game" / "assets" / "sounds"
    (base_path / "sfx" / "ui").mkdir(parents=True)
    (base_path / "sfx" / "shots").mkdir(parents=True)
    (base_path / "sfx" / "explosions").mkdir(parents=True)

    files = [
        base_path / "sfx" / "ui" / "button_click.wav",
        base_path / "sfx" / "ui" / "sound_hover.wav",
        base_path / "sfx" / "shots" / "tiro_1.wav",
        base_path / "sfx" / "shots" / "tiro_2.wav",
        base_path / "sfx" / "shots" / "tiro_3.wav",
        base_path / "sfx" / "explosions" / "explosão_asteroides_0.wav",
    ]
    for file_path in files:
        file_path.write_bytes(b"fake")

    monkeypatch.setattr(pygame.mixer, "Sound", lambda path: _FakeSound(path))

    sounds, groups = load_sfx(str(base_path), sfx_volume=0.3, master_volume=0.8)

    assert "button_click" in sounds
    assert "button_hover" in sounds
    assert "shots" in groups
    assert len(groups["shots"]) == 3
    assert "explosions" in groups
    assert len(groups["explosions"]) == 1


def test_audio_controller_delegates_to_manager() -> None:
    class DummyManager:
        def __init__(self) -> None:
            self.called = False

        def play_warning(self) -> str:
            self.called = True
            return "ok"

    controller = AudioController(DummyManager())

    assert controller.play_warning() == "ok"
    assert controller._mgr.called is True


def test_sound_manager_shutdown_clears_state(monkeypatch) -> None:
    monkeypatch.setattr(pygame.mixer, "stop", lambda: None)
    monkeypatch.setattr(pygame.mixer, "quit", lambda: None)

    manager = SoundManager.__new__(SoundManager)
    manager.audio_available = True
    manager._sounds = {"a": _FakeSound("a")}
    manager._sound_groups = {"g": [_FakeSound("b")]}
    manager.transition_thread = None
    manager.stop_all = types.MethodType(lambda self: None, manager)
    manager.stop_music_internal = types.MethodType(lambda self: None, manager)

    manager.shutdown()

    assert manager.audio_available is False
    assert manager._sounds == {}
    assert manager._sound_groups == {}
    assert manager.transition_thread is None


def test_sound_manager_music_facade_delegates(monkeypatch) -> None:
    calls: list[bool] = []

    monkeypatch.setattr(
        sound_manager.music_manager,
        "play_menu_music",
        lambda force=False: calls.append(force),
    )

    sound_manager.play_menu_music(force=True)

    assert calls == [True]


def test_sound_config_includes_button_click() -> None:
    assert SOUND_PATHS["sfx"]["ui"]["button_click"] == "sfx/ui/button_click.wav"


def test_mountain_serpent_boss_declares_music_state() -> None:
    assert MountainSerpentBoss.MUSIC_STATE.value == "mountain_serpent_boss"
    assert SOUND_PATHS["music"]["mountain_serpent_boss"] == "music/Stone_Snake_Themel.mp3"
