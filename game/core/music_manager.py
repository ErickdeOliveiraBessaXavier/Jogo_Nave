"""MusicManager: música data-driven (orientada por pastas) e transições.

Isola a reprodução de música, o estado de transição e o controle de fade do
`SoundManager`. A escolha de QUAL faixa tocar vem da **descoberta de pastas**
(`MusicLibrary`): `audio/themes/<tema>/` para a música ambiente de cada tema e
`audio/bosses/<BOSS_TYPE_NAME>/` para a música exclusiva de cada boss. Nenhuma
lista de arquivos no código; basta soltar o arquivo na pasta certa.

Rotação dentro de um tema/boss: `TrackRotation` (aleatória, sem repetição
imediata). Faixas tocam UMA vez (`loops=0`) e o fim de cada uma — sinalizado
pelo end-event do mixer, bombeado no loop principal (`app.py`) e roteado por
`advance_current()` — toca a próxima da rotação, dando rotação contínua e
suave mesmo com uma única faixa (que simplesmente repete).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import pygame

from .music_library import MusicLibrary, TrackRotation
from .sound_config import (
    AUDIO_BOSSES_ROOT,
    AUDIO_MENU_ROOT,
    AUDIO_THEMES_ROOT,
    BEHAVIOR_CONFIG,
    MUSIC_BEHAVIOR_CONFIG,
    MusicState,
)

if TYPE_CHECKING:
    from .sound import SoundManager


# Estados em que há música "de jogo" no ar (ambiente ou boss). Usado para
# bloquear que o menu sobreponha a partida e para a categoria de volume.
_GAME_MUSIC_STATES = (MusicState.GAME, MusicState.BOSS)


class MusicStateManager:
    def __init__(self, manager: "MusicManager"):
        self.music_manager = manager
        self.current_state: MusicState = MusicState.SILENCE
        self.previous_state: MusicState = MusicState.SILENCE

    def reset(self) -> None:
        self.current_state = MusicState.SILENCE
        self.previous_state = MusicState.SILENCE
        self.music_manager.stop_music_internal()

    def transition_to(
        self, new_state: MusicState, force: bool = False, key: Optional[str] = None
    ) -> bool:
        if not force and self._should_block_transition(new_state):
            return False

        self.previous_state = self.current_state
        self._execute_transition(new_state, key)
        self.current_state = new_state
        return True

    def _should_block_transition(self, new_state: MusicState) -> bool:
        if not MUSIC_BEHAVIOR_CONFIG["prevent_menu_over_game"]:
            return False

        is_music_paused = self.music_manager.sound_manager.music_paused
        is_game_music_active = self.current_state in _GAME_MUSIC_STATES or (
            is_music_paused and self.previous_state in _GAME_MUSIC_STATES
        )

        return new_state == MusicState.MENU and is_game_music_active

    def _execute_transition(
        self, new_state: MusicState, key: Optional[str] = None
    ) -> None:
        # Sem early-return por estado igual: GAME->GAME pode trocar de tema. A
        # deduplicação ("já tocando exatamente isto") é feita nos internos.
        if new_state == MusicState.MENU:
            self.music_manager.play_menu_music_internal()
        elif new_state == MusicState.GAME:
            self.music_manager.play_theme_internal(key)
        elif new_state == MusicState.BOSS:
            self.music_manager.play_boss_internal(key)
        elif new_state == MusicState.SILENCE:
            self.music_manager.stop_music_internal()

    def pause_current(self) -> None:
        self.music_manager.pause_music_internal()

    def resume_current(self) -> None:
        self.music_manager.resume_music_internal()


class MusicManager:
    # Chave do boss GENÉRICO: faixa(s) em `bosses/normal/` usada como fallback
    # quando a pasta de um boss específico está vazia. É também a música do boss
    # base (BOSS_TYPE_NAME == "normal").
    GENERIC_BOSS_KEY: str = "normal"

    def __init__(self, sound_manager: "SoundManager") -> None:
        self.sound_manager = sound_manager
        self.music_state_manager = MusicStateManager(self)
        self.library = MusicLibrary(
            AUDIO_THEMES_ROOT, AUDIO_BOSSES_ROOT, AUDIO_MENU_ROOT
        )
        # Rotações vivas por playlist (chave "theme:<x>" / "boss:<x>").
        self._rotations: Dict[str, TrackRotation] = {}
        self._current_theme_key: Optional[str] = None
        self._current_track: Optional[str] = None  # arquivo tocando agora
        self._active_rotation_key: Optional[str] = None
        self._active_music_type: Optional[str] = None  # "game" | "boss" | "menu"
        # Suprime o end-event disparado quando NÓS paramos a música para trocar
        # de faixa (senão o avanço por fim-de-faixa entraria em laço com a
        # própria transição). Limpo ao final de uma transição bem-sucedida.
        self._suppress_end = False
        # Transição de faixa PENDENTE (crossfade cooperativo na thread principal).
        # Enquanto setada, o fade-out assíncrono do SDL está em curso e a nova
        # faixa será carregada por `update(dt)` quando o contador zerar. Nenhuma
        # chamada de pygame roda fora da thread principal (pygame não é
        # thread-safe — ver `_transition_to_music`).
        self._pending_transition: Optional[Tuple[str, str, int]] = None
        self._fade_out_remaining: float = 0.0

    def _is_mixer_ready(self) -> bool:
        """Verifica se pygame.mixer foi inicializado com sucesso."""
        return (
            getattr(self.sound_manager, "audio_available", True)
            and pygame.mixer.get_init() is not None
        )

    # ── API pública (data-driven) ──────────────────────────────────────────────
    def play_theme(self, key: Optional[str] = None) -> None:
        """Toca a música ambiente do tema `key` (ou retoma o tema atual se None)."""
        self.music_state_manager.transition_to(MusicState.GAME, key=key)

    def play_boss(self, key: Optional[str] = None) -> None:
        """Toca a música exclusiva do boss `key` (== BOSS_TYPE_NAME)."""
        self.music_state_manager.transition_to(MusicState.BOSS, key=key)

    def play_menu_music(self, force: bool = False) -> None:
        self.music_state_manager.transition_to(MusicState.MENU, force=force)

    # Alias legado mantido para docs/compat; equivale a retomar o tema atual.
    def play_background_music(self) -> None:
        self.play_theme(None)

    def pause_music(self) -> None:
        self.music_state_manager.pause_current()

    def resume_music(self) -> None:
        self.music_state_manager.resume_current()

    def stop_music(self, force: bool = False) -> None:
        self.music_state_manager.transition_to(MusicState.SILENCE, force=force)

    def advance_current(self) -> None:
        """Fim de faixa → próxima da rotação ativa (rotação contínua e suave).

        Chamado pelo end-event do mixer no loop principal. Ignora o evento
        quando fomos nós que paramos a música (transição) ou quando não há
        rotação ativa (menu/silêncio)."""
        if self._suppress_end:
            return
        if self._active_rotation_key is None or self._active_music_type is None:
            return
        rot = self._rotations.get(self._active_rotation_key)
        if rot is None:
            return
        track = rot.next()
        if track:
            self._transition_to_music(track, self._active_music_type)

    # ── Internos: resolução data-driven ────────────────────────────────────────
    def play_theme_internal(self, key: Optional[str] = None) -> None:
        theme_key = key or self._current_theme_key
        self._current_theme_key = theme_key
        # Pasta do tema vazia → `_play_rotation` é no-op (mantém o que toca).
        self._play_rotation(
            f"theme:{theme_key}", self.library.theme_tracks(theme_key), "game"
        )

    def play_boss_internal(self, key: Optional[str] = None) -> None:
        tracks = self.library.boss_tracks(key)
        if tracks:
            rotation_key = f"boss:{key}"
        else:  # pasta do boss vazia → música de boss GENÉRICA (`bosses/normal/`)
            tracks = self.library.boss_tracks(self.GENERIC_BOSS_KEY)
            rotation_key = f"boss:{self.GENERIC_BOSS_KEY}"
        self._play_rotation(rotation_key, tracks, "boss")

    def play_menu_music_internal(self) -> None:
        # Data-driven: pasta plana `audio/menu/`. Faixa única → loop gapless;
        # várias → rotação. Pasta vazia → no-op (mantém o que toca).
        self._play_rotation("menu", self.library.menu_tracks(), "menu")

    def _play_rotation(
        self, rotation_key: str, tracks: List[str], music_type: str
    ) -> None:
        if not tracks:
            return
        # Já comprometidos com exatamente esta playlist? Não reinicia (re-emissão
        # do mesmo estado/tema não deve cortar a faixa). Dedupe por INTENÇÃO, não
        # por `pygame.mixer.music.get_busy()`: a reprodução roda numa thread de
        # fundo, então logo após a 1ª chamada `get_busy()` ainda é False e uma 2ª
        # chamada idêntica (ex.: game_over→MENU seguido de MainMenu.enter→MENU)
        # dispararia uma 2ª transição, parando e reiniciando a faixa (engasgo).
        # `_current_track`/`_active_rotation_key` são setados de forma síncrona e
        # zerados em stop/fade — logo, replay legítimo posterior ainda funciona.
        already_active = (
            self._active_rotation_key == rotation_key
            and self._current_track is not None
        )
        rot = self._rotations.get(rotation_key)
        if rot is None or not rot.matches(tracks):
            rot = TrackRotation(tracks)
            self._rotations[rotation_key] = rot
        self._active_rotation_key = rotation_key
        self._active_music_type = music_type
        if already_active:
            return
        track = rot.next()
        if track is not None:
            # Faixa única: loop nativo gapless (sem re-fade por repetição). Com
            # ≥2 faixas: toca uma vez (loop=0) e o end-event avança a rotação.
            loop = -1 if len(tracks) == 1 else 0
            self._transition_to_music(track, music_type, loop=loop)

    # ── Pausa / retomada / parada ──────────────────────────────────────────────
    def pause_music_internal(self) -> None:
        if not self._is_mixer_ready():
            return
        if not self.sound_manager.music_paused:
            pygame.mixer.music.pause()
            self.sound_manager.music_paused = True

    def resume_music_internal(self) -> None:
        if not self._is_mixer_ready():
            return
        if self.sound_manager.music_paused:
            pygame.mixer.music.unpause()
            self.sound_manager.music_paused = False

    def stop_music_internal(self) -> None:
        if not self._is_mixer_ready():
            return
        self._suppress_end = True  # parada explícita não deve avançar a rotação
        self._pending_transition = None  # cancela troca de faixa em andamento
        pygame.mixer.music.stop()
        self.sound_manager.current_music = None
        self.sound_manager.music_paused = False
        self._current_track = None
        self._active_rotation_key = None
        self._active_music_type = None

    # ── Volume ─────────────────────────────────────────────────────────────────
    def set_music_volume(self, volume: float) -> None:
        self.sound_manager.music_volume = max(0.0, min(1.0, volume))
        if not self._is_mixer_ready():
            return
        if self.sound_manager.current_music is not None:
            pygame.mixer.music.set_volume(self.sound_manager.music_target_volume())

    def load_config(
        self, music_vol: float, sfx_volume: float, shot_volume: float
    ) -> None:
        self.sound_manager.music_volume = max(0.0, min(1.0, music_vol))
        self.sound_manager.sfx_volume = max(0.0, min(1.0, sfx_volume))
        self.sound_manager.shot_volume_base = max(0.0, min(1.0, shot_volume))

        if self.sound_manager.current_music is not None:
            pygame.mixer.music.set_volume(self.sound_manager.music_target_volume())

    # ── Transição com fade (stream único do mixer) ─────────────────────────────
    def _transition_to_music(
        self, music_path: str, music_type: str, loop: int = 0
    ) -> None:
        """Agenda a troca de faixa com crossfade — 100% na thread principal.

        pygame/SDL NÃO é thread-safe: fazer `mixer.music.load/play/fadeout`/
        `set_volume` numa thread de fundo enquanto o loop principal renderiza
        causava *access violation* intermitente (duas threads dentro do core do
        pygame ao mesmo tempo — ver crash em `renderer.smoothscale` × worker de
        música). Aqui o fade é COOPERATIVO: dispara o fade-out assíncrono do SDL
        agora e agenda o carregamento da nova faixa para quando ele terminar,
        avançado por `update(dt)` no loop principal. O fade-in usa o `fade_ms`
        nativo do SDL (também assíncrono, no thread de áudio do próprio SDL) —
        sem `time.sleep`, sem stepping manual de volume, sem worker thread.
        """
        # Intenção committada de forma síncrona (dedup em `_play_rotation`).
        self._suppress_end = True
        self._current_track = music_path

        if not self._is_mixer_ready():
            return

        if pygame.mixer.music.get_busy() and not self.sound_manager.music_paused:
            fade_duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])
            pygame.mixer.music.fadeout(int(fade_duration * 1000))
            self._pending_transition = (music_path, music_type, loop)
            self._fade_out_remaining = fade_duration
        else:
            # Nada tocando → entra direto com fade-in nativo.
            self._pending_transition = None
            self._start_track(music_path, music_type, loop)

    def update(self, dt: float) -> None:
        """Avança a transição de música pendente (1×/frame no loop principal).

        Espera o fade-out assíncrono do SDL terminar e então carrega/inicia a
        nova faixa com fade-in nativo. Todas as chamadas de pygame ficam na
        thread principal — nenhuma corrida com o render."""
        if self._pending_transition is None:
            return
        self._fade_out_remaining -= dt
        if self._fade_out_remaining <= 0.0:
            music_path, music_type, loop = self._pending_transition
            self._pending_transition = None
            self._start_track(music_path, music_type, loop)

    def _start_track(self, music_path: str, music_type: str, loop: int) -> None:
        """Carrega e inicia a faixa com fade-in nativo do SDL (main thread)."""
        if not self._is_mixer_ready():
            return

        fade_duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])
        # No web (emscripten), o streaming de música (mixer.music) detecta o
        # formato pela EXTENSÃO — MP3 não é suportado. A build web fornece as
        # músicas em .ogg real; aqui trocamos a extensão. SFX (mixer.Sound)
        # detectam pelo conteúdo, então não precisam disso.
        import sys

        if sys.platform == "emscripten" and music_path.lower().endswith(".mp3"):
            music_path = music_path[:-4] + ".ogg"
        try:
            pygame.mixer.music.load(music_path)
            # Volume-alvo já com master, multiplicador de boss e ducking
            # persistente (fonte única: SoundManager.music_target_volume). O
            # `fade_ms` do SDL sobe de 0 até este valor.
            target_volume = self.sound_manager.music_target_volume(music_type)
            pygame.mixer.music.set_volume(target_volume)
            pygame.mixer.music.play(loop, 0.0, int(fade_duration * 1000))
            self.sound_manager.current_music = music_type
            self.sound_manager.music_paused = False
        except pygame.error as e:
            logging.error("Erro na transição de música: %s", e)
        finally:
            # Nova faixa no ar: liberar o avanço por fim-de-faixa.
            self._suppress_end = False

    def fade_out_music(self, duration: float | None = None) -> None:
        if not self._is_mixer_ready():
            return

        if duration is None:
            duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])

        self._suppress_end = True
        self._pending_transition = None  # cancela troca de faixa em andamento
        pygame.mixer.music.fadeout(int(duration * 1000))
        self.sound_manager.current_music = None
        self.sound_manager.music_paused = False
        self._current_track = None
        self._active_rotation_key = None
        self._active_music_type = None

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
