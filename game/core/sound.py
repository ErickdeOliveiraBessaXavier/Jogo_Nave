import pygame
import random
import os
from typing import Dict, List

from .sound_config import VOLUME_CONFIG, CHANNEL_CONFIG


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
        self.master_volume = VOLUME_CONFIG["master"]
        self.sfx_volume = VOLUME_CONFIG["sfx"]
        self.music_volume = VOLUME_CONFIG["music"]
        
        # Controle de tiros para evitar irritação
        self.shot_channel = pygame.mixer.Channel(CHANNEL_CONFIG["shots"])
        self.warning_channel = pygame.mixer.Channel(CHANNEL_CONFIG["warning"])
        self.last_shot_time = 0.0
        self.shot_volume_base = VOLUME_CONFIG["shots"]
        
        # Estado da música
        self.current_music = None
        self.music_paused = False
        
        # Carregar sons
        self._load_sounds()
    
    def _load_sounds(self):
        """Carrega todos os sons do jogo usando configuração externa."""
        base_path = "game/assets/sounds"
        
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
        
        # Explosão de naves alienígenas
        alien_explosion_path = os.path.join(explosions_path, "explosão_naves_alienigenas.wav")
        if os.path.exists(alien_explosion_path):
            try:
                sound = pygame.mixer.Sound(alien_explosion_path)
                sound.set_volume(self.sfx_volume * self.master_volume)
                self._sounds["explosion_alien"] = sound
            except pygame.error as e:
                print(f"Erro ao carregar som {alien_explosion_path}: {e}")
        
        # Explosão do boss
        boss_explosion_path = os.path.join(explosions_path, "explisão_boss.wav")
        if os.path.exists(boss_explosion_path):
            try:
                sound = pygame.mixer.Sound(boss_explosion_path)
                sound.set_volume(self.sfx_volume * self.master_volume)
                self._sounds["explosion_boss"] = sound
            except pygame.error as e:
                print(f"Erro ao carregar som {boss_explosion_path}: {e}")
        
        # Som de dano do boss
        boss_damage_path = os.path.join(explosions_path, "som_dano_boss.wav")
        if os.path.exists(boss_damage_path):
            try:
                sound = pygame.mixer.Sound(boss_damage_path)
                sound.set_volume(self.sfx_volume * self.master_volume)
                self._sounds["boss_damage"] = sound
            except pygame.error as e:
                print(f"Erro ao carregar som {boss_damage_path}: {e}")
        
        # Explosão da nave do jogador
        ship_explosion_path = os.path.join(explosions_path, "explisão_nave.wav")
        if os.path.exists(ship_explosion_path):
            try:
                sound = pygame.mixer.Sound(ship_explosion_path)
                sound.set_volume(self.sfx_volume * self.master_volume)
                self._sounds["ship_explosion"] = sound
            except pygame.error as e:
                print(f"Erro ao carregar som {ship_explosion_path}: {e}")
        
        # Carregamento do som de warning
        warning_path = os.path.join(base_path, "sfx", "ui", "warning.mp3")
        if os.path.exists(warning_path):
            try:
                sound = pygame.mixer.Sound(warning_path)
                sound.set_volume(self.sfx_volume * self.master_volume)
                self._sounds["warning"] = sound
            except pygame.error as e:
                print(f"Erro ao carregar som {warning_path}: {e}")
        
        self._sound_groups["explosions"] = explosion_sounds
        
        print(f"Sons carregados: {len(self._sounds)} sons individuais")
        print(f"Grupos de sons: {list(self._sound_groups.keys())}")
        print(f"🎵 Sistema de som inicializado com nova estrutura organizada")
        print(f"📁 Estrutura: music/ | sfx/shots/ | sfx/explosions/ | sfx/ui/")
    
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
        print(f"🔊 Volume geral ajustado para {self.master_volume:.1%}")
    
    def set_sfx_volume(self, volume: float):
        """Define o volume dos efeitos sonoros (0.0 a 1.0)."""
        self.sfx_volume = max(0.0, min(1.0, volume))
        self._update_all_volumes()
        print(f"🎵 Volume dos efeitos ajustado para {self.sfx_volume:.1%}")
    
    def set_shot_volume(self, volume: float):
        """Define o volume específico dos tiros (0.0 a 1.0)."""
        self.shot_volume_base = max(0.0, min(1.0, volume))
        print(f"🔫 Volume dos tiros ajustado para {self.shot_volume_base:.1%}")
    
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
        """Inicia a música de fundo do jogo."""
        music_path = os.path.join("game", "assets", "sounds", "music", "background.mp3")
        if os.path.exists(music_path) and self.current_music != "background":
            try:
                pygame.mixer.music.load(music_path)
                pygame.mixer.music.set_volume(self.music_volume * self.master_volume)
                pygame.mixer.music.play(-1)  # Loop infinito
                self.current_music = "background"
                self.music_paused = False
                print("🎵 Música de fundo iniciada")
            except pygame.error as e:
                print(f"Erro ao carregar música de fundo: {e}")
    
    def play_boss_music(self):
        """Inicia a música do boss."""
        music_path = os.path.join("game", "assets", "sounds", "music", "boss.mp3")
        if os.path.exists(music_path) and self.current_music != "boss":
            try:
                pygame.mixer.music.load(music_path)
                pygame.mixer.music.set_volume(self.music_volume * self.master_volume)
                pygame.mixer.music.play(-1)  # Loop infinito
                self.current_music = "boss"
                self.music_paused = False
                print("🎵 Música do boss iniciada")
            except pygame.error as e:
                print(f"Erro ao carregar música do boss: {e}")
    
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
    
    def play_warning(self):
        """Toca o som de aviso/warning."""
        if "warning" in self._sounds:
            # Parar qualquer warning anterior
            self.warning_channel.stop()
            # Tocar no canal dedicado
            self.warning_channel.play(self._sounds["warning"])
            print("⚠️ Som de warning tocado")
    
    def stop_all_sfx(self):
        """Para todos os efeitos sonoros (não afeta a música)."""
        # Parar canais específicos
        self.warning_channel.stop()
        self.shot_channel.stop()
        # Parar todos os outros sons
        for sound in self._sounds.values():
            sound.stop()
        print("🔇 Todos os efeitos sonoros parados")
    
    def set_music_volume(self, volume: float):
        """Define o volume da música (0.0 a 1.0)."""
        self.music_volume = max(0.0, min(1.0, volume))
        pygame.mixer.music.set_volume(self.music_volume * self.master_volume)
        print(f"🎼 Volume da música ajustado para {self.music_volume:.1%}")


# Instância global do gerenciador de som
sound_manager = SoundManager()