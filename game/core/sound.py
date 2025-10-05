import pygame
import random
import os
import sys
import threading
import time
from typing import Dict, List

from .sound_config import VOLUME_CONFIG, CHANNEL_CONFIG, BEHAVIOR_CONFIG


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path: str
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    except AttributeError:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


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
        self.boss_laser_volume: float = VOLUME_CONFIG["boss_laser"]
        
        # Controle de tiros para evitar irritação
        self.shot_channel: pygame.mixer.Channel = pygame.mixer.Channel(CHANNEL_CONFIG["shots"])
        self.warning_channel: pygame.mixer.Channel = pygame.mixer.Channel(CHANNEL_CONFIG["warning"])
        self.boss_laser_channel: pygame.mixer.Channel = pygame.mixer.Channel(CHANNEL_CONFIG["boss_laser"])
        self.boss_laser_fire_channel: pygame.mixer.Channel = pygame.mixer.Channel(CHANNEL_CONFIG["boss_laser_fire"])
        self.last_shot_time: float = 0.0
        self.shot_volume_base: float = VOLUME_CONFIG["shots"]
        
        # Estado da música
        self.current_music: str | None = None
        self.music_paused: bool = False
        self.transition_thread: threading.Thread | None = None
        self.original_music_volume: float = self.music_volume
        
        # Carregar sons
        self._load_sounds()
    
    def _load_sounds(self):
        """Carrega todos os sons do jogo usando configuração externa."""
        base_path = get_resource_path("game/assets/sounds")
        
        # Verificar se a pasta base existe
        if not os.path.exists(base_path):
            return
        
        # Carregar sons de tiro
        shot_sounds: List[pygame.mixer.Sound] = []
        shot_path_template = "sfx/shots/tiro_{}.wav"
        
        for i in range(1, 4):  # tiro_1.wav, tiro_2.wav, tiro_3.wav
            sound_path = os.path.join(base_path, shot_path_template.format(i))
            if os.path.exists(sound_path):
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    # Volume mais baixo para tiros
                    sound.set_volume(self.shot_volume_base * self.master_volume)
                    shot_sounds.append(sound)
                    self._sounds[f"shot_{i}"] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {sound_path}: {e}")
        
        self._sound_groups["shots"] = shot_sounds
        
        # Carregar sons de explosão
        explosion_sounds: List[pygame.mixer.Sound] = []
        explosions_path = os.path.join(base_path, "sfx", "explosions")
        
        if os.path.exists(explosions_path):
            # Explosões de asteroides
            for i in range(4):  # explosão_asteroides_0.wav até 3.wav
                sound_path = os.path.join(explosions_path, f"explosão_asteroides_{i}.wav")
                if os.path.exists(sound_path):
                    try:
                        sound = pygame.mixer.Sound(sound_path)
                        sound.set_volume(self.sfx_volume * self.master_volume)
                        explosion_sounds.append(sound)
                        self._sounds[f"explosion_asteroid_{i}"] = sound
                    except pygame.error as e:
                        print(f"Erro ao carregar som {sound_path}: {e}")
            
            # Outros sons de explosão
            explosion_files = {
                "explosion_alien": "explosão_naves_alienigenas.wav",
                "explosion_boss": "explisão_boss.wav", 
                "boss_damage": "som_dano_boss.wav",
                "ship_explosion": "explisão_nave.wav"
            }
            
            for sound_key, filename in explosion_files.items():
                sound_path = os.path.join(explosions_path, filename)
                if os.path.exists(sound_path):
                    try:
                        sound = pygame.mixer.Sound(sound_path)
                        sound.set_volume(self.sfx_volume * self.master_volume)
                        self._sounds[sound_key] = sound
                    except pygame.error as e:
                        print(f"Erro ao carregar som {sound_path}: {e}")
        
        self._sound_groups["explosions"] = explosion_sounds
        
        # Carregamento do som de warning
        ui_path = os.path.join(base_path, "sfx", "ui")
        if os.path.exists(ui_path):
            warning_path = os.path.join(ui_path, "warning.mp3")
            if os.path.exists(warning_path):
                try:
                    sound = pygame.mixer.Sound(warning_path)
                    sound.set_volume(self.sfx_volume * self.master_volume)
                    self._sounds["warning"] = sound
                except pygame.error as e:
                    print(f"Erro ao carregar som {warning_path}: {e}")
        
        # Sons do boss laser
        laser_path = os.path.join(base_path, "sfx", "shots")
        if os.path.exists(laser_path):
            laser_files = {
                "boss_laser_charging": "som_laser_carregando.mp3",
                "boss_laser_fire": "som_laser.mp3"
            }
            
            for sound_key, filename in laser_files.items():
                sound_path = os.path.join(laser_path, filename)
                if os.path.exists(sound_path):
                    try:
                        sound = pygame.mixer.Sound(sound_path)
                        sound.set_volume(self.boss_laser_volume * self.master_volume)
                        self._sounds[sound_key] = sound
                    except pygame.error:
                        pass  # Falha silenciosa se o arquivo não carregar

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
        if not hasattr(pygame.mixer, 'music') or not pygame.mixer.music.get_busy():
            return
            
        if duck:
            # Reduzir volume da música para 60% do normal
            duck_volume = self.original_music_volume * 0.6
            pygame.mixer.music.set_volume(duck_volume * self.master_volume)
        else:
            # Restaurar volume original da música
            pygame.mixer.music.set_volume(self.original_music_volume * self.master_volume)
    
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
    
    def get_volumes(self):
        """Mostra todos os volumes atuais."""
        print(f"📊 Volumes atuais:")
        print(f"  🔊 Geral: {self.master_volume:.1%}")
        print(f"  🎵 Efeitos: {self.sfx_volume:.1%}")
        print(f"  🎼 Música: {self.music_volume:.1%}")
        print(f"  🔫 Tiros: {self.shot_volume_base:.1%}")
    
    def _update_all_volumes(self):
        """Atualiza o volume de todos os sons carregados."""
        final_volume = self.sfx_volume * self.master_volume
        for sound in self._sounds.values():
            sound.set_volume(final_volume)
    
    def stop_all(self):
        """Para todos os sons."""
        pygame.mixer.stop()
    
    # === MÉTODOS DE MÚSICA ===
    
    def play_background_music(self):
        """Inicia a música de fundo com transição suave."""
        music_path = get_resource_path(os.path.join("game", "assets", "sounds", "music", "background.mp3"))
        if os.path.exists(music_path) and self.current_music != "background":
            self._transition_to_music(music_path, "background")
    
    def play_boss_music(self):
        """Inicia a música do boss com transição suave."""
        music_path = get_resource_path(os.path.join("game", "assets", "sounds", "music", "boss.mp3"))
        if os.path.exists(music_path) and self.current_music != "boss":
            self._transition_to_music(music_path, "boss")

    def _transition_to_music(self, music_path: str, music_type: str):
        """Realiza transição suave entre músicas."""
        # Cancela transição anterior se existir
        if self.transition_thread and self.transition_thread.is_alive():
            return
        
        # Inicia nova transição em thread separada
        self.transition_thread = threading.Thread(
            target=self._smooth_transition,
            args=(music_path, music_type),
            daemon=True
        )
        self.transition_thread.start()
    
    def _smooth_transition(self, music_path: str, music_type: str):
        """Executa a transição suave entre músicas."""
        fade_duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])
        fade_steps = 20  # Número de passos para o fade
        step_duration = fade_duration / fade_steps
        
        try:
            # Fase 1: Fade out da música atual
            if pygame.mixer.music.get_busy():
                current_volume = pygame.mixer.music.get_volume()
                
                for i in range(fade_steps):
                    volume = current_volume * (1 - (i + 1) / fade_steps)
                    pygame.mixer.music.set_volume(volume)
                    time.sleep(step_duration)
                
                pygame.mixer.music.stop()
            
            # Pequena pausa entre transições
            time.sleep(0.1)
            
            # Fase 2: Carrega e inicia nova música
            pygame.mixer.music.load(music_path)
            target_volume = self.music_volume * self.master_volume
            
            # Inicia com volume zero
            pygame.mixer.music.set_volume(0)
            pygame.mixer.music.play(-1)  # Loop infinito
            
            # Fase 3: Fade in da nova música
            for i in range(fade_steps):
                volume = target_volume * (i + 1) / fade_steps
                pygame.mixer.music.set_volume(volume)
                time.sleep(step_duration)
            
            # Garante volume final correto
            pygame.mixer.music.set_volume(target_volume)
            
            self.current_music = music_type
            self.music_paused = False
            
        except pygame.error as e:
            print(f"Erro na transição de música: {e}")
            # Fallback: carrega diretamente sem transição
            try:
                pygame.mixer.music.load(music_path)
                pygame.mixer.music.set_volume(self.music_volume * self.master_volume)
                pygame.mixer.music.play(-1)
                self.current_music = music_type
                self.music_paused = False
            except pygame.error as fallback_error:
                print(f"Erro no fallback de música: {fallback_error}")
    
    def stop_music_transitions(self):
        """Para todas as transições de música em andamento."""
        if self.transition_thread and self.transition_thread.is_alive():
            # Não podemos forçar parar uma thread, mas podemos parar a música imediatamente
            pygame.mixer.music.stop()
            self.current_music = None
    
    def pause_music(self):
        """Pausa a música atual."""
        if not self.music_paused:
            pygame.mixer.music.pause()
            self.music_paused = True
            print("⏸️ Música pausada")
    
    def resume_music(self):
        """Resume a música pausada."""
        if self.music_paused:
            pygame.mixer.music.unpause()
            self.music_paused = False
            print("▶️ Música resumida")
    
    def stop_music(self):
        """Para a música atual."""
        pygame.mixer.music.stop()
        self.current_music = None
        self.music_paused = False
        print("⏹️ Música parada")
    
    def fade_out_music(self, duration: float | None = None):
        """Faz fade out suave da música atual."""
        if duration is None:
            duration = float(BEHAVIOR_CONFIG["music"]["fade_duration"])
        
        fade_duration_ms = int(duration * 1000)  # Pygame espera milissegundos
        pygame.mixer.music.fadeout(fade_duration_ms)
        self.current_music = None
        self.music_paused = False
    
    def play_warning(self):
        """Toca o som de aviso/warning."""
        if "warning" in self._sounds:
            # Parar qualquer warning anterior
            self.warning_channel.stop()
            # Tocar no canal dedicado
            self.warning_channel.play(self._sounds["warning"])
    
    def stop_warning(self):
        """Para especificamente o som de warning."""
        self.warning_channel.stop()
    
    def stop_all_sfx(self):
        """Para todos os efeitos sonoros (não afeta a música)."""
        # Parar canais específicos
        self.warning_channel.stop()
        self.shot_channel.stop()
        self.boss_laser_channel.stop()
        self.boss_laser_fire_channel.stop()
        # Parar todos os outros sons
        for sound in self._sounds.values():
            sound.stop()


# Instância global do gerenciador de som
sound_manager = SoundManager()