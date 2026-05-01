import os
import random
import sys
import threading
from functools import wraps
from typing import Any, Callable, Dict, List, TypeVar, Union

import pygame
import logging

from .sound_config import (
    CHANNEL_CONFIG,
    SOUND_PATHS,
    VOLUME_CONFIG,
)
from .music_manager import MusicManager
from .sfx_manager import load_sfx

MusicPaths = Dict[str, Union[str, List[str]]]

F = TypeVar("F", bound=Callable[..., Any])


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path: str
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def require_audio(func: F) -> F:
    """Decorador que verifica se o áudio está disponível antes de executar."""

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not getattr(self, "audio_available", True):
            return None
        try:
            return func(self, *args, **kwargs)
        except pygame.error:
            # Se ocorrer um erro de pygame, desabilitar áudio
            if hasattr(self, "audio_available"):
                self.audio_available = False
            return None

    return wrapper  # type: ignore


class SoundManager:
    """Gerenciador de sons do jogo."""

    def __init__(self):
        self.audio_available = True

        # Inicializar o mixer do pygame com tratamento de erro
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error as e:
            logging.warning(f"Não foi possível inicializar o sistema de áudio: {e}")
            logging.warning("O jogo continuará sem som.")
            self.audio_available = False
            # Inicializar variáveis mínimas necessárias
            self._sounds: Dict[str, pygame.mixer.Sound] = {}
            self._sound_groups: Dict[str, List[pygame.mixer.Sound]] = {}
            self.master_volume: float = VOLUME_CONFIG["master"]
            self.sfx_volume: float = VOLUME_CONFIG["sfx"]
            self.music_volume: float = VOLUME_CONFIG["music"]
            self.boss_music_multiplier: float = VOLUME_CONFIG["boss_music"]
            self.last_shot_time: float = 0.0
            self.shot_volume_base: float = VOLUME_CONFIG["shots"]
            self.current_music: str | None = None
            self.music_paused: bool = False
            self.transition_thread: threading.Thread | None = None
            self.transition_lock = threading.Lock()
            self.original_music_volume: float = self.music_volume
            self.music_manager = MusicManager(self)
            self.music_state_manager = self.music_manager.music_state_manager
            return

        # Configurar número de canais
        pygame.mixer.set_num_channels(CHANNEL_CONFIG["max_channels"])

        # Dicionários para armazenar sons carregados
        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        self._sound_groups: Dict[str, List[pygame.mixer.Sound]] = {}

        # Configurações de volume usando configuração externa
        self.master_volume: float = VOLUME_CONFIG["master"]
        self.sfx_volume: float = VOLUME_CONFIG["sfx"]
        self.music_volume: float = VOLUME_CONFIG["music"]
        self.boss_music_multiplier: float = VOLUME_CONFIG["boss_music"]

        # Controle de tiros para evitar irritação
        self.shot_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["shots"]
        )
        self.warning_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["warning"]
        )
        self.boss_laser_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["boss_laser"]
        )
        self.boss_laser_fire_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["boss_laser_fire"]
        )
        self.last_shot_time: float = 0.0
        self.shot_volume_base: float = VOLUME_CONFIG["shots"]

        # Estado da música
        self.current_music: str | None = None
        self.music_paused: bool = False
        self.transition_thread: threading.Thread | None = None
        self.transition_lock = threading.Lock()
        self.original_music_volume: float = self.music_volume
        self.music_manager = MusicManager(self)

        # Carregar sons
        self._load_sounds()

        # Gerenciador de estado da música
        self.music_state_manager = self.music_manager.music_state_manager

    @require_audio
    def _load_sounds(self):
        """Carrega todos os sons do jogo delegando para `sfx_manager.load_sfx()`.

        Mantemos compatibilidade populando `self._sounds` e `self._sound_groups`.
        """
        base_path = get_resource_path(str(SOUND_PATHS["base"]))
        sounds, groups = load_sfx(base_path, self.sfx_volume, self.master_volume)
        self._sounds = sounds
        self._sound_groups = groups

    @require_audio
    def play_shot(self):
        """Toca um som de tiro com técnicas anti-irritação."""
        if "shots" not in self._sound_groups or not self._sound_groups["shots"]:
            return

        current_time = pygame.time.get_ticks() / 1000.0
        time_since_last = current_time - self.last_shot_time

        # Se já há um som de tiro tocando muito recentemente, pula
        if self.shot_channel.get_busy() and time_since_last < 0.05:  # 50ms
            return

        # Selecionar som aleatório
        sound = random.choice(self._sound_groups["shots"])

        # Variação dinâmica de volume baseada na frequência
        if time_since_last < 0.3:  # Se atirou recentemente (300ms)
            # Volume diminui quanto mais rápido atirar
            volume_factor = max(0.4, min(1.0, time_since_last / 0.3))
        else:
            volume_factor = 1.0

        # Aplicar volume final
        final_volume = self.shot_volume_base * self.master_volume * volume_factor
        sound.set_volume(final_volume)

        # Tocar no canal dedicado (interrompe tiro anterior se necessário)
        self.shot_channel.play(sound)

        self.last_shot_time = current_time

    @require_audio
    def play_laser_shot(self):
        """Toca som do laser do upgrade LASER_SHOT."""
        if "laser_shot" in self._sounds:
            self._sounds["laser_shot"].play()

    @require_audio
    def play_explosion_asteroid(self):
        """Toca um som de explosão de asteroide aleatório."""
        if "explosions" in self._sound_groups and self._sound_groups["explosions"]:
            sound = random.choice(self._sound_groups["explosions"])
            sound.play()

    @require_audio
    def play_meteor_rain(self):
        """Toca um som de chuva de meteoros aleatório (AIR_STRIKE)."""
        if "meteor_rain" in self._sound_groups and self._sound_groups["meteor_rain"]:
            sound = random.choice(self._sound_groups["meteor_rain"])
            sound.play()

    @require_audio
    def play_explosion_alien(self):
        """Toca som de explosão de nave alienígena."""
        if "explosion_alien" in self._sounds:
            self._sounds["explosion_alien"].play()

    @require_audio
    def play_explosion_boss(self):
        """Toca som de explosão do boss."""
        if "explosion_boss" in self._sounds:
            self._sounds["explosion_boss"].play()

    @require_audio
    def play_boss_damage(self):
        """Toca som de dano no boss."""
        if "boss_damage" in self._sounds:
            self._sounds["boss_damage"].play()

    @require_audio
    def play_boss_warning(self):
        """Toca um som de aviso específico do boss (fallback para `warning`)."""
        if "boss_warning" in self._sounds:
            self._sounds["boss_warning"].play()
        else:
            # Fallback para o som genérico de warning
            self.play_warning()

    @require_audio
    def play_boss_frenzy(self):
        """Toca som/efeito associado ao estado de 'frenzy' do boss.

        Implementação leve: tenta tocar `boss_frenzy`, caso contrário reutiliza
        `play_boss_damage()` como efeito audível.
        """
        if "boss_frenzy" in self._sounds:
            self._sounds["boss_frenzy"].play()
        else:
            # Fallback: toque um som de dano ao boss para sinalizar intensa atividade
            self.play_boss_damage()

    @require_audio
    def play_boss_laser_charging(self):
        """Toca som de carregamento do laser do boss com controle de volume inteligente."""
        if "boss_laser_charging" in self._sounds:
            # Configurar volume balanceado do som do laser
            sound = self._sounds["boss_laser_charging"]
            sound.set_volume(self.sfx_volume * self.master_volume)

            # Tocar no canal dedicado
            self.boss_laser_channel.play(sound)

    @require_audio
    def stop_boss_laser_charging(self):
        """Para o som de carregamento do laser do boss."""
        self.boss_laser_channel.stop()

    @require_audio
    def play_boss_laser_fire(self):
        """Toca som de disparo do laser do boss com volume balanceado e controle."""
        if "boss_laser_fire" in self._sounds:
            # Volume ligeiramente mais alto para o disparo (momento de impacto)
            sound = self._sounds["boss_laser_fire"]
            fire_volume = min(1.0, self.sfx_volume * 1.2)  # 20% mais alto
            sound.set_volume(fire_volume * self.master_volume)
            # Tocar no canal dedicado para controle
            self.boss_laser_fire_channel.play(sound)

    @require_audio
    def play_spike_boss_laser(self):
        """Toca som de disparo do laser do Spike Boss."""
        if "spike_boss_laser" in self._sounds:
            sound = self._sounds["spike_boss_laser"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def stop_boss_laser_fire(self):
        """Para o som de disparo do laser do boss."""
        self.boss_laser_fire_channel.stop()

    @require_audio
    def _duck_music(self, duck: bool):
        """Controla o volume da música (ducking) para dar espaço aos efeitos do boss."""
        if not hasattr(pygame.mixer, "music") or not pygame.mixer.music.get_busy():
            return

        if duck:
            # Reduzir volume da música para 60% do normal
            base_volume = self.music_volume
            if self.current_music in ["boss", "spike_boss", "slime_boss"]:
                base_volume *= self.boss_music_multiplier

            duck_volume = base_volume * 0.6
            final_volume = min(1.0, duck_volume * self.master_volume)
            pygame.mixer.music.set_volume(final_volume)
        else:
            # Restaurar volume original da música
            base_volume = self.music_volume
            if self.current_music in ["boss", "spike_boss", "slime_boss"]:
                base_volume *= self.boss_music_multiplier

            final_volume = min(1.0, base_volume * self.master_volume)
            pygame.mixer.music.set_volume(final_volume)

    @require_audio
    def play_ship_explosion(self):
        """Toca som de explosão da nave do jogador."""
        if "ship_explosion" in self._sounds:
            self._sounds["ship_explosion"].play()

    @require_audio
    def play_upgrade_activate(self):
        """Toca som de ativação de aprimoramento."""
        if "upgrade_activate" in self._sounds:
            self._sounds["upgrade_activate"].play()

    @require_audio
    def play_upgrade_denied(self):
        """Toca som de negação de aprimoramento (reutiliza hover para MVP)."""
        if "button_hover" in self._sounds:
            self._sounds["button_hover"].play()

    @require_audio
    def play_black_hole(self):
        """Toca o som do buraco negro."""
        if "black_hole" in self._sounds:
            sound = self._sounds["black_hole"]
            sound.set_volume(self.sfx_volume * self.master_volume * 1.2)
            sound.play()

    @require_audio
    def play_meteor_boss_crack(self):
        """Toca o som de rachadura do boss meteoro."""
        if "hit_hurt_meteor_boss" in self._sounds:
            sound = self._sounds["hit_hurt_meteor_boss"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def play_sound(self, sound_name: str):
        """Toca um som específico pelo nome."""
        if sound_name in self._sounds:
            self._sounds[sound_name].play()

    def set_master_volume(self, volume: float):
        """Define o volume mestre (0.0 a 1.0)."""
        self.master_volume = max(0.0, min(1.0, volume))
        self._update_all_volumes()

    def set_sfx_volume(self, volume: float):
        """Define o volume dos efeitos sonoros (0.0 a 1.0)."""
        self.sfx_volume = max(0.0, min(1.0, volume))
        self._update_all_volumes()

    def set_shot_volume(self, volume: float):
        """Define o volume específico dos tiros (0.0 a 1.0)."""
        self.shot_volume_base = max(0.0, min(1.0, volume))

    def get_volumes(self):
        """Mostra todos os volumes atuais."""
        logging.info("Volumes atuais:")
        logging.info("  Geral: %.1f%%", self.master_volume * 100)
        logging.info("  Efeitos: %.1f%%", self.sfx_volume * 100)
        logging.info("  Música: %.1f%%", self.music_volume * 100)
        logging.info("  Tiros: %.1f%%", self.shot_volume_base * 100)

    @require_audio
    def _update_all_volumes(self):
        """Atualiza o volume de todos os sons carregados."""
        final_volume = self.sfx_volume * self.master_volume
        for sound in self._sounds.values():
            sound.set_volume(final_volume)

    @require_audio
    def stop_all(self):
        """Para todos os sons."""
        pygame.mixer.stop()

    @require_audio
    def play_background_music(self):
        self.music_manager.play_background_music()

    @require_audio
    def play_boss_music(self):
        self.music_manager.play_boss_music()

    @require_audio
    def play_spike_boss_music(self):
        self.music_manager.play_spike_boss_music()

    @require_audio
    def play_slime_boss_music(self):
        self.music_manager.play_slime_boss_music()

    @require_audio
    def play_giant_meteor_boss_music(self):
        self.music_manager.play_giant_meteor_boss_music()

    @require_audio
    def play_mountain_serpent_boss_music(self):
        self.music_manager.play_mountain_serpent_boss_music()

    @require_audio
    def play_menu_music(self, force: bool = False):
        self.music_manager.play_menu_music(force=force)

    @require_audio
    def pause_music(self):
        self.music_manager.pause_music()

    @require_audio
    def resume_music(self):
        self.music_manager.resume_music()

    @require_audio
    def stop_music(self, force: bool = False):
        self.music_manager.stop_music(force=force)

    @require_audio
    def set_music_volume(self, volume: float):
        self.music_manager.set_music_volume(volume)

    @require_audio
    def load_config(self, music_vol: float, sfx_volume: float, shot_volume: float):
        self.music_manager.load_config(music_vol, sfx_volume, shot_volume)

    @require_audio
    def fade_out_music(self, duration: float | None = None):
        self.music_manager.fade_out_music(duration)

    @require_audio
    def play_warning(self):
        self.music_manager.play_warning()

    @require_audio
    def play_powerup(self):
        self.music_manager.play_powerup()

    @require_audio
    def stop_warning(self):
        self.music_manager.stop_warning()

    @require_audio
    def stop_all_sfx(self):
        """Para todos os efeitos sonoros (não afeta a música)."""
        self.warning_channel.stop()
        self.shot_channel.stop()
        self.boss_laser_channel.stop()
        self.boss_laser_fire_channel.stop()
        for sound in self._sounds.values():
            sound.stop()

    def shutdown(self, wait: float = 1.0) -> None:
        """Limpa recursos de áudio e encerra worker threads de transição.

        Deve ser chamado pelo `app.quit()` para garantir que `pygame.mixer`
        seja encerrado corretamente. `wait` é timeout em segundos para join.
        """
        # Mark audio as unavailable to short-circuit further play calls
        self.audio_available = False

        try:
            # Stop all sounds and music
            try:
                self.stop_all()
            except Exception:
                pass
            try:
                self.music_manager.stop_music_internal()
            except Exception:
                pass

            # Join transition thread if running
            if self.transition_thread and self.transition_thread.is_alive():
                self.transition_thread.join(timeout=wait)

            # Quit the mixer
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        finally:
            # best-effort cleanup of resources
            self._sounds.clear()
            self._sound_groups.clear()
            self.transition_thread = None


# Instância global do gerenciador de som
class AudioController:
    """Fachada de alto nível para o sistema de áudio.

    Implementada como um wrapper em volta de `SoundManager` para permitir
    refatorações internas futuras (separação Sfx/Music) sem quebrar a API
    pública usada pelo restante do códigobase.
    """

    def __init__(self, manager: SoundManager | None = None) -> None:
        self._mgr = manager or SoundManager()

    def __getattr__(self, name: str):
        # Delegar chamadas desconhecidas para o SoundManager subjacente
        return getattr(self._mgr, name)

    def shutdown(self, wait: float = 1.0) -> None:
        # Expor shutdown na fachada
        try:
            self._mgr.shutdown(wait=wait)
        except Exception:
            logging.exception("Erro ao encerrar o AudioController")


# Instância global do gerenciador de som (fachada)
sound_manager = AudioController()
