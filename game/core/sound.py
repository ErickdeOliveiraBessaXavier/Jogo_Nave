import pygame
import random
import os
import sys
import threading
import time
from typing import Dict, List, cast, Any, Union

from .sound_config import (
    VOLUME_CONFIG,
    CHANNEL_CONFIG,
    BEHAVIOR_CONFIG,
    SOUND_PATHS,
    MusicState,
    MUSIC_BEHAVIOR_CONFIG,
)

MusicPaths = Dict[str, Union[str, List[str]]]


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path: str
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class MusicStateManager:
    def __init__(self, sound_manager: "SoundManager"):
        self.sound_manager = sound_manager
        self.current_state: MusicState = MusicState.SILENCE
        self.previous_state: MusicState = MusicState.SILENCE

    def reset(self):
        """Resets the music state manager to its initial silent state."""
        self.current_state = MusicState.SILENCE
        self.previous_state = MusicState.SILENCE
        self.sound_manager.stop_music_internal() # Ensure music is stopped

    def transition_to(self, new_state: MusicState, force: bool = False) -> bool:
        if not force:
            if self._should_block_transition(new_state):
                return False
        self.previous_state = self.current_state
        self._execute_transition(new_state)
        self.current_state = new_state
        return True

    def _should_block_transition(self, new_state: MusicState) -> bool:
        if not MUSIC_BEHAVIOR_CONFIG["prevent_menu_over_game"]:
            return False
        game_music_types = [MusicState.GAME, MusicState.BOSS, MusicState.SPIKE_BOSS]

        is_game_music_active = self.current_state in game_music_types or (
            self.sound_manager.music_paused
            and self.previous_state in game_music_types
        )

        if new_state == MusicState.MENU and is_game_music_active:
            return True
        return False

    def _execute_transition(self, new_state: MusicState):
        # For all other transitions, play the appropriate music.
        if self.current_state != new_state:
            if new_state == MusicState.MENU:
                self.sound_manager.play_menu_music_internal()
            elif new_state == MusicState.GAME:
                self.sound_manager.play_background_music_internal()
            elif new_state == MusicState.BOSS:
                self.sound_manager.play_boss_music_internal()
            elif new_state == MusicState.SPIKE_BOSS:
                self.sound_manager.play_spike_boss_music_internal()
            elif new_state == MusicState.SILENCE:
                self.sound_manager.stop_music_internal()

    def pause_current(self):
        self.sound_manager.pause_music_internal()

    def resume_current(self):
        self.sound_manager.resume_music_internal()


class SoundManager:
    """Gerenciador de sons do jogo."""

    def __init__(self):
        # Inicializar o mixer do pygame
        pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
        pygame.mixer.init()

        # Configurar número de canais
        pygame.mixer.set_num_channels(CHANNEL_CONFIG["max_channels"])

        # Dicionários para armazenar sons carregados
        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        self._sound_groups: Dict[str, List[pygame.mixer.Sound]] = {}

        # Configurações de volume usando configuração externa
        self.master_volume: float = VOLUME_CONFIG["master"]
        self.sfx_volume: float = VOLUME_CONFIG["sfx"]
        self.music_volume: float = VOLUME_CONFIG["music"]
        self.boss_music_volume: float = VOLUME_CONFIG["boss_music"]
        self.boss_laser_volume: float = VOLUME_CONFIG["boss_laser"]
        self.powerup_volume: float = VOLUME_CONFIG["powerup"]

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

        # Carregar sons
        self._load_sounds()

        # Gerenciador de estado da música
        self.music_state_manager = MusicStateManager(self)

    def _load_sounds(self):
        """Carrega todos os sons do jogo usando as configurações de SOUND_PATHS."""
        base_path = get_resource_path(str(SOUND_PATHS["base"]))

        if not os.path.exists(base_path):
            print(f"Diretório de sons não encontrado: {base_path}")
            return

        sfx_paths = cast(Dict[str, Any], SOUND_PATHS["sfx"])

        # Carregar sons de tiro
        shot_sounds: List[pygame.mixer.Sound] = []
        shot_path_template = sfx_paths["shots"]
        for i in range(1, 4):
            sound_path = os.path.join(base_path, shot_path_template.format(i))
            if os.path.exists(sound_path):
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    sound.set_volume(self.shot_volume_base * self.master_volume)
                    shot_sounds.append(sound)
                    self._sounds[f"shot_{i}"] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {sound_path}: {e}")
        self._sound_groups["shots"] = shot_sounds

        # Carregar sons de explosão
        explosion_sounds: List[pygame.mixer.Sound] = []
        explosion_paths = sfx_paths["explosions"]

        # Explosões de asteroides
        asteroid_template = explosion_paths["asteroid"]
        for i in range(4):
            sound_path = os.path.join(base_path, asteroid_template.format(i))
            if os.path.exists(sound_path):
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    sound.set_volume(self.sfx_volume * self.master_volume)
                    explosion_sounds.append(sound)
                    self._sounds[f"explosion_asteroid_{i}"] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {sound_path}: {e}")

        # Outras explosões
        other_explosions = {
            "explosion_alien": explosion_paths["alien"],
            "explosion_boss": explosion_paths["boss"],
            "boss_damage": explosion_paths["boss_damage"],
            "ship_explosion": explosion_paths["ship"],
        }
        for key, path in other_explosions.items():
            sound_path = os.path.join(base_path, path)
            if os.path.exists(sound_path):
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    sound.set_volume(self.sfx_volume * self.master_volume)
                    self._sounds[key] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {sound_path}: {e}")

        self._sound_groups["explosions"] = explosion_sounds

        # Carregar som de ui
        ui_sounds = {
            "warning": sfx_paths["ui"]["warning"],
            "powerup": sfx_paths["ui"]["powerup"],
            "button_hover": sfx_paths["ui"]["button_hover"],
        }
        for key, path in ui_sounds.items():
            sound_path = os.path.join(base_path, path)
            if os.path.exists(sound_path):
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    sound.set_volume(self.sfx_volume * self.master_volume)
                    self._sounds[key] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {sound_path}: {e}")

        # Carregar sons do laser do boss
        laser_sounds = {
            "boss_laser_charging": sfx_paths["boss_laser_charging"],
            "boss_laser_fire": sfx_paths["boss_laser_fire"],
        }
        for key, path in laser_sounds.items():
            sound_path = os.path.join(base_path, path)
            if os.path.exists(sound_path):
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    sound.set_volume(self.boss_laser_volume * self.master_volume)
                    self._sounds[key] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {sound_path}: {e}")

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

    def play_explosion_asteroid(self):
        """Toca um som de explosão de asteroide aleatório."""
        if "explosions" in self._sound_groups and self._sound_groups["explosions"]:
            sound = random.choice(self._sound_groups["explosions"])
            sound.play()

    def play_explosion_alien(self):
        """Toca som de explosão de nave alienígena."""
        if "explosion_alien" in self._sounds:
            self._sounds["explosion_alien"].play()

    def play_explosion_boss(self):
        """Toca som de explosão do boss."""
        if "explosion_boss" in self._sounds:
            self._sounds["explosion_boss"].play()

    def play_boss_damage(self):
        """Toca som de dano no boss."""
        if "boss_damage" in self._sounds:
            self._sounds["boss_damage"].play()

    def play_boss_laser_charging(self):
        """Toca som de carregamento do laser do boss com controle de volume inteligente."""
        if "boss_laser_charging" in self._sounds:
            # Aplicar ducking na música (reduzir volume)
            self._duck_music(True)

            # Configurar volume balanceado do som do laser
            sound = self._sounds["boss_laser_charging"]
            sound.set_volume(self.boss_laser_volume * self.master_volume)

            # Tocar no canal dedicado
            self.boss_laser_channel.play(sound)

    def stop_boss_laser_charging(self):
        """Para o som de carregamento do laser do boss e restaura música."""
        self.boss_laser_channel.stop()
        # Restaurar volume original da música
        self._duck_music(False)

    def play_boss_laser_fire(self):
        """Toca som de disparo do laser do boss com volume balanceado e controle."""
        if "boss_laser_fire" in self._sounds:
            # Volume ligeiramente mais alto para o disparo (momento de impacto)
            sound = self._sounds["boss_laser_fire"]
            fire_volume = min(1.0, self.boss_laser_volume * 1.2)  # 20% mais alto
            sound.set_volume(fire_volume * self.master_volume)
            # Tocar no canal dedicado para controle
            self.boss_laser_fire_channel.play(sound)

    def stop_boss_laser_fire(self):
        """Para o som de disparo do laser do boss."""
        self.boss_laser_fire_channel.stop()

    def _duck_music(self, duck: bool):
        """Controla o volume da música (ducking) para dar espaço aos efeitos do boss."""
        if not hasattr(pygame.mixer, "music") or not pygame.mixer.music.get_busy():
            return

        current_music_base_volume = self.original_music_volume
        if self.current_music == "boss":
            current_music_base_volume = self.boss_music_volume

        if duck:
            # Reduzir volume da música para 60% do normal
            duck_volume = current_music_base_volume * 0.6
            pygame.mixer.music.set_volume(duck_volume * self.master_volume)
        else:
            # Restaurar volume original da música
            pygame.mixer.music.set_volume(
                current_music_base_volume * self.master_volume
            )

    def play_ship_explosion(self):
        """Toca som de explosão da nave do jogador."""
        if "ship_explosion" in self._sounds:
            self._sounds["ship_explosion"].play()

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

    def set_boss_music_volume(self, volume: float):
        """Define o volume da música do boss (0.0 a 1.0)."""
        self.boss_music_volume = max(0.0, min(1.0, volume))
        if self.current_music == "boss":
            pygame.mixer.music.set_volume(self.boss_music_volume * self.master_volume)

    def set_music_volume(self, volume: float):
        """Define o volume da música de fundo (0.0 a 1.0)."""
        self.music_volume = max(0.0, min(1.0, volume))
        if self.current_music == "background":
            pygame.mixer.music.set_volume(self.music_volume * self.master_volume)

    def get_volumes(self):
        """Mostra todos os volumes atuais."""
        print(f"📊 Volumes atuais:")
        print(f"  🔊 Geral: {self.master_volume:.1%}")
        print(f"  🎵 Efeitos: {self.sfx_volume:.1%}")
        print(f"  🎼 Música: {self.music_volume:.1%}")
        print(f"  🎼 Música Boss: {self.boss_music_volume:.1%}")
        print(f"  🔫 Tiros: {self.shot_volume_base:.1%}")

    def _update_all_volumes(self):
        """Atualiza o volume de todos os sons carregados."""
        final_volume = self.sfx_volume * self.master_volume
        for sound in self._sounds.values():
            sound.set_volume(final_volume)

    def stop_all(self):
        """Para todos os sons."""
        pygame.mixer.stop()

    # === MÉTODOS DE MÚSICA (CONTROLADOS PELO STATE MANAGER) ===

    def play_background_music(self):
        self.music_state_manager.transition_to(MusicState.GAME)

    def play_boss_music(self):
        self.music_state_manager.transition_to(MusicState.BOSS)

    def play_spike_boss_music(self):
        self.music_state_manager.transition_to(MusicState.SPIKE_BOSS)

    def play_menu_music(self, force: bool = False):
        self.music_state_manager.transition_to(MusicState.MENU, force=force)

    def pause_music(self):
        print("--- Initiating music pause ---")
        self.music_state_manager.pause_current()

    def resume_music(self):
        self.music_state_manager.resume_current()

    def stop_music(self, force: bool = False):
        self.music_state_manager.transition_to(MusicState.SILENCE, force=True)

    # === MÉTODOS INTERNOS DE MÚSICA (CHAMADOS PELO STATE MANAGER) ===

    def play_background_music_internal(self):
        music_paths_config = cast(MusicPaths, SOUND_PATHS["music"])
        background_music_list = music_paths_config["background"]
        if isinstance(background_music_list, list) and background_music_list:
            chosen_music = random.choice(background_music_list)
            music_path = get_resource_path(
                os.path.join(str(SOUND_PATHS["base"]), chosen_music)
            )
            if os.path.exists(music_path) and self.current_music != chosen_music:
                self._transition_to_music(music_path, "background")

    def play_boss_music_internal(self):
        music_paths = cast(MusicPaths, SOUND_PATHS["music"])
        music_path = get_resource_path(
            os.path.join(str(SOUND_PATHS["base"]), str(music_paths["boss"]))
        )
        if os.path.exists(music_path) and self.current_music != "boss":
            self._transition_to_music(music_path, "boss")

    def play_spike_boss_music_internal(self):
        music_paths = cast(MusicPaths, SOUND_PATHS["music"])
        music_path = get_resource_path(
            os.path.join(str(SOUND_PATHS["base"]), str(music_paths["spike_boss"]))
        )
        if os.path.exists(music_path) and self.current_music != "spike_boss":
            self._transition_to_music(music_path, "spike_boss")

    def play_menu_music_internal(self):
        music_paths = cast(MusicPaths, SOUND_PATHS["music"])
        music_path = get_resource_path(
            os.path.join(str(SOUND_PATHS["base"]), str(music_paths["menu"]))
        )
        if os.path.exists(music_path) and self.current_music != "menu":
            self._transition_to_music(music_path, "menu")

    def pause_music_internal(self):
        if not self.music_paused:
            pygame.mixer.music.pause()
            self.music_paused = True

    def resume_music_internal(self):
        if self.music_paused:
            pygame.mixer.music.unpause()
            self.music_paused = False

    def stop_music_internal(self):
        pygame.mixer.music.stop()
        self.current_music = None
        self.music_paused = False

    def _transition_to_music(self, music_path: str, music_type: str):
        """Realiza transição suave entre músicas."""
        if self.transition_thread and self.transition_thread.is_alive():
            pygame.mixer.music.stop()
            self.transition_thread.join()

        self.transition_thread = threading.Thread(
            target=self._smooth_transition, args=(music_path, music_type), daemon=True
        )
        self.transition_thread.start()

    def _smooth_transition(self, music_path: str, music_type: str):
        """Executa a transição suave entre músicas."""
        with self.transition_lock:
            fade_duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.fadeout(int(fade_duration * 1000))
                    time.sleep(fade_duration)

                pygame.mixer.music.load(music_path)
                if music_type == "boss":
                    target_volume = self.boss_music_volume * self.master_volume
                else:
                    target_volume = self.music_volume * self.master_volume

                pygame.mixer.music.set_volume(0)
                pygame.mixer.music.play(-1)

                fade_steps = 20
                step_duration = fade_duration / fade_steps
                for i in range(fade_steps):
                    volume = target_volume * (i + 1) / fade_steps
                    pygame.mixer.music.set_volume(volume)
                    time.sleep(step_duration)

                pygame.mixer.music.set_volume(target_volume)
                self.current_music = music_type
                self.music_paused = False
            except pygame.error as e:
                print(f"Erro na transição de música: {e}")

    def fade_out_music(self, duration: float | None = None):
        """Faz fade out suave da música atual."""
        if duration is None:
            duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])

        fade_duration_ms = int(duration * 1000)
        pygame.mixer.music.fadeout(fade_duration_ms)
        self.current_music = None
        self.music_paused = False

    def play_warning(self):
        """Toca o som de aviso/warning."""
        if "warning" in self._sounds:
            self.warning_channel.stop()
            self.warning_channel.play(self._sounds["warning"])

    def play_powerup(self):
        """Toca o som de power-up."""
        if "powerup" in self._sounds:
            sound = self._sounds["powerup"]
            sound.set_volume(self.powerup_volume * self.master_volume)
            sound.play()

    def stop_warning(self):
        """Para especificamente o som de warning."""
        self.warning_channel.stop()

    def stop_all_sfx(self):
        """Para todos os efeitos sonoros (não afeta a música)."""
        self.warning_channel.stop()
        self.shot_channel.stop()
        self.boss_laser_channel.stop()
        self.boss_laser_fire_channel.stop()
        for sound in self._sounds.values():
            sound.stop()


# Instância global do gerenciador de som
sound_manager = SoundManager()
