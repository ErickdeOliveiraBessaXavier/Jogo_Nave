import logging
import os
import random
import sys
import threading
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import pygame

from .music_manager import MusicManager
from .sfx_manager import load_sfx
from .sound_config import CHANNEL_CONFIG, SOUND_PATHS, VOLUME_CONFIG

MusicPaths = Dict[str, Union[str, List[str]]]

F = TypeVar("F", bound=Callable[..., Any])

# Evento postado pelo mixer quando uma faixa de música termina. Bombeado no loop
# principal (`app.py`) → `sound_manager.advance_current()` para rotação suave.
# `USEREVENT + 1` é livre (nenhum outro USEREVENT em uso no projeto).
MUSIC_END_EVENT = pygame.USEREVENT + 1


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller.

    Fora do PyInstaller, resolve contra a RAIZ DO PROJETO (derivada de
    ``__file__``), NÃO o CWD. `os.path.abspath(".")` quebrava a build
    distribuída rodada de outro diretório (ex.: Downloads): os assets de áudio
    (caminhos relativos "game/assets/...") não resolviam e sons/música sumiam
    silenciosamente. Mesmo motivo do BASE_DIR usado nas imagens.
    """
    # game/core/sound.py → 3 dirnames = raiz do projeto (contém "game/").
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    base_path = getattr(sys, "_MEIPASS", project_root)
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
        import sys as _sys

        try:
            if not pygame.mixer.get_init():
                # Web (WASM): o áudio é renderizado por software no navegador e
                # um buffer pequeno faz o callback sofrer underrun → estalos. Um
                # buffer maior (1024 quadros ≈ 23ms de latência, aceitável num
                # shmup) elimina o crackle; freq/format fixos casam o OGG e evitam
                # resample. No desktop mantemos o init padrão (sem regressão).
                if _sys.platform == "emscripten":
                    pygame.mixer.pre_init(
                        frequency=44100, size=-16, channels=2, buffer=1024
                    )
                pygame.mixer.init()
        except pygame.error as e:
            logging.warning("Não foi possível inicializar o sistema de áudio: %s", e)
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
            # Fator de ducking da música (1.0 = sem duck). Persistente: honrado em
            # todo cálculo de volume, sobrevive ao avanço de rotação.
            self.music_duck_factor: float = 1.0
            self.music_manager = MusicManager(self)
            self.music_state_manager = self.music_manager.music_state_manager
            return

        # Configurar número de canais. No web, menos canais = menos mixagem por
        # callback de áudio (que disputa CPU com o loop no software do WASM).
        # Mantém os 8 dedicados (0–7) + 5 livres p/ one-shots — suficiente.
        max_channels = CHANNEL_CONFIG["max_channels"]
        if _sys.platform == "emscripten":
            max_channels = max(CHANNEL_CONFIG["reserved"] + 5, 12)
        pygame.mixer.set_num_channels(max_channels)

        # Reserva os canais dedicados (0..reserved-1): `Sound.play()` (one-shots)
        # só será auto-alocado nos canais livres restantes. Sem isto, um one-shot
        # (ex.: explosão da nave) podia cair num canal dedicado e ser cortado por
        # `stop_looping_sfx()` na troca de cena.
        pygame.mixer.set_reserved(CHANNEL_CONFIG["reserved"])

        # Notifica o fim de cada faixa de música → avanço da rotação (app.py).
        pygame.mixer.music.set_endevent(MUSIC_END_EVENT)

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
        self.golem_mine_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["golem_mine"]
        )
        self.golem_orb_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["golem_orb"]
        )
        self.metropolis_laser_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["metropolis_laser"]
        )
        self.time_stop_channel: pygame.mixer.Channel = pygame.mixer.Channel(
            CHANNEL_CONFIG["time_stop"]
        )
        self.last_shot_time: float = 0.0
        self.shot_volume_base: float = VOLUME_CONFIG["shots"]
        # Throttle do "escudo destruído": vários escudos podem quebrar no mesmo
        # frame (dano em área) — colapsa em um único cue para não sobrepor.
        self.last_shield_break_time: float = 0.0

        # Estado da música
        self.current_music: str | None = None
        self.music_paused: bool = False
        self.transition_thread: threading.Thread | None = None
        self.transition_lock = threading.Lock()
        self.original_music_volume: float = self.music_volume
        # Ducking da música POR FONTE (nome → fator). Persistente: honrado em
        # todo cálculo de volume, sobrevive ao avanço de rotação. O fator
        # efetivo é o PRODUTO das fontes ativas — ver `music_duck_factor`.
        self._music_ducks: dict[str, float] = {}
        self.music_manager = MusicManager(self)

        # Carregar sons
        self._load_sounds()

        # Abre o dispositivo de áudio do SO imediatamente, evitando o stutter
        # na primeira chamada real a play() (Windows inicializa o stream tarde).
        self._warm_up_audio()

        # Gerenciador de estado da música
        self.music_state_manager = self.music_manager.music_state_manager

    @require_audio
    def _warm_up_audio(self) -> None:
        """Força a abertura do dispositivo de áudio do SO jogando um frame silencioso.

        No Windows, SDL/DirectSound só inicializa o stream físico na primeira
        chamada a Sound.play(). Sem isso, o primeiro som real do jogo causa um
        stutter de 20–50 ms enquanto o hardware acorda.
        """
        if not self._sounds:
            return
        sound = next(iter(self._sounds.values()))
        saved = sound.get_volume()
        sound.set_volume(0.0)
        ch = sound.play()
        if ch:
            ch.stop()
        sound.set_volume(saved)

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
    def play_shield_activate(self):
        """Toca o som de escudo concedido (uma vez por pulso do SapperDrone)."""
        if "shield_activate" in self._sounds:
            self._sounds["shield_activate"].play()

    @require_audio
    def play_shield_break(self):
        """Toca o som de escudo destruído, com throttle p/ não sobrepor quando
        vários escudos quebram no mesmo instante (dano em área)."""
        if "shield_break" not in self._sounds:
            return
        now = pygame.time.get_ticks() / 1000.0
        if now - self.last_shield_break_time < 0.07:  # 70ms
            return
        self.last_shield_break_time = now
        self._sounds["shield_break"].play()

    @require_audio
    def play_time_stop_in(self):
        """Mundo desacelerando — início do congelamento da parada do tempo."""
        self._play_time_stop_cue("time_stop_in")

    @require_audio
    def play_time_stop_out(self):
        """Mundo acelerando de volta — início da rampa de recuperação."""
        self._play_time_stop_cue("time_stop_out")

    def _play_time_stop_cue(self, key: str) -> None:
        """Toca um cue da parada do tempo no canal dedicado.

        Canal próprio, e não `Sound.play()`, por dois motivos: os dois cues são
        mutuamente exclusivos (tocar um corta o outro, sem sobreposição) e o
        efeito pode ser CANCELADO no meio — troca de fase ou game over chamam
        `stop_time_stop_sfx()` para o som não vazar para a tela seguinte.
        """
        sound = self._sounds.get(key)
        if sound is None:
            return
        sound.set_volume(self.sfx_volume * self.master_volume)
        self.time_stop_channel.play(sound)

    @require_audio
    def stop_time_stop_sfx(self):
        """Corta o cue da parada do tempo (efeito cancelado antes de terminar)."""
        self.time_stop_channel.stop()

    @require_audio
    def play_gem_birth(self):
        """Toca o som de nascimento da gema do IceGolem (círculo de energia)."""
        if "gem_birth" in self._sounds:
            self._sounds["gem_birth"].play()

    @require_audio
    def play_gem_death(self):
        """Toca o som de colapso/morte da gema do IceGolem (energia desabando)."""
        if "gem_death" in self._sounds:
            self._sounds["gem_death"].play()

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
    def play_boss_laser_fire(self, return_channel: bool = False):
        """Toca som de disparo do laser do boss com volume balanceado e controle.

        Args:
            return_channel: Se True, retorna o channel dedicado após tocar,
                para que o caller possa interromper o som quando quiser.
        """
        if "boss_laser_fire" in self._sounds:
            # Volume ligeiramente mais alto para o disparo (momento de impacto)
            sound = self._sounds["boss_laser_fire"]
            fire_volume = min(1.0, self.sfx_volume * 1.2)  # 20% mais alto
            sound.set_volume(fire_volume * self.master_volume)
            # Sempre usa o canal dedicado do laser para evitar conflito com
            # canais usados por tiros comuns.
            self.boss_laser_fire_channel.play(sound)
            if return_channel:
                return self.boss_laser_fire_channel

    @require_audio
    def play_golem_mine_timer(self):
        """Toca um tick da mina do Golem no canal dedicado (interrompe tick anterior)."""
        if "golem_mine_timer" in self._sounds:
            sound = self._sounds["golem_mine_timer"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            self.golem_mine_channel.play(sound)

    @require_audio
    def stop_golem_mine_timer(self):
        """Para o som de tick da mina do Golem."""
        self.golem_mine_channel.stop()

    @require_audio
    def play_golem_orb_purple(self):
        """Toca o som de rajada do orbe roxo do Golem."""
        if "golem_orb_purple" in self._sounds:
            sound = self._sounds["golem_orb_purple"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            self.golem_orb_channel.play(sound)

    @require_audio
    def play_golem_eruption(self):
        """Toca o som de erupção do solo do Golem (emergência e submersão)."""
        if "golem_eruption" in self._sounds:
            sound = self._sounds["golem_eruption"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

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
    def play_metropolis_laser_loop(self):
        """Toca o loop do laser do Metropolis Overlord no canal dedicado."""
        if "metropolis_overlord_laser" in self._sounds:
            # Se já está tocando ou pausado (canal ocupado), não reinicia para evitar stutters
            if self.metropolis_laser_channel.get_busy():
                return

            logging.info("SoundManager: Iniciando loop do laser Metropolis Overlord")
            sound = self._sounds["metropolis_overlord_laser"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            # Toca em loop infinito (-1)
            self.metropolis_laser_channel.play(sound, loops=-1)
        else:
            logging.warning(
                "SoundManager: som 'metropolis_overlord_laser' não encontrado!"
            )

    @require_audio
    def stop_metropolis_laser_loop(self):
        """Para o loop do laser do Metropolis Overlord."""
        self.metropolis_laser_channel.stop()

    @require_audio
    def play_metropolis_lightning_charge(self):
        """Toca o som de antecipação (carga) da descarga atmosférica da sentinela."""
        if "metropolis_lightning_charge" in self._sounds:
            sound = self._sounds["metropolis_lightning_charge"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def play_metropolis_lightning_strike(self):
        """Toca o som do raio caindo (impacto) da descarga atmosférica da sentinela."""
        if "metropolis_lightning_strike" in self._sounds:
            sound = self._sounds["metropolis_lightning_strike"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def play_metropolis_energy_zone(self):
        """Toca o som da zona de sobrecarga elétrica (sentinela "emp")."""
        if "metropolis_energy_zone" in self._sounds:
            sound = self._sounds["metropolis_energy_zone"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def play_metropolis_electric_grid(self):
        """Toca o som da grade holográfica energizada (sentinela "laser")."""
        if "metropolis_electric_grid" in self._sounds:
            sound = self._sounds["metropolis_electric_grid"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def play_metropolis_triple_shot(self):
        """Toca o som do trio de drones energéticos (sentinela "neon")."""
        if "metropolis_triple_shot" in self._sounds:
            sound = self._sounds["metropolis_triple_shot"]
            sound.set_volume(self.sfx_volume * self.master_volume)
            sound.play()

    @require_audio
    def pause_metropolis_laser_loop(self):
        """Pausa o loop do laser do Metropolis Overlord."""
        self.metropolis_laser_channel.pause()

    @require_audio
    def resume_metropolis_laser_loop(self):
        """Retoma o loop do laser do Metropolis Overlord."""
        self.metropolis_laser_channel.unpause()

    def music_target_volume(self, music_type: str | None = None) -> float:
        """Volume-alvo da música (0.0–1.0) já com master, multiplicador de boss e
        o fator de ducking persistente aplicados. Fonte única de verdade do volume
        da música — usado pela transição, set_music_volume, load_config e duck.

        `music_type` None usa `self.current_music` (categoria atual no ar)."""
        kind = music_type if music_type is not None else self.current_music
        base = self.music_volume
        if kind == "boss":
            base *= self.boss_music_multiplier
        return min(1.0, base * self.master_volume) * self.music_duck_factor

    @property
    def music_duck_factor(self) -> float:
        """Fator de ducking efetivo: o PRODUTO de todas as fontes ativas.

        Era um float único, e isso fazia as fontes se atropelarem: o Game Over
        abaixa a música e a restaura com `duck_music(False)`, que escrevia 1.0
        no campo compartilhado. Morrer durante uma parada do tempo devolvia o
        volume cheio no meio do efeito, e o efeito, ao terminar, apagava o duck
        do Game Over. Com o produto, cada fonte só mexe na própria chave e as
        duas compõem — quem sair por último não desfaz o duck de quem ficou.
        """
        fator = 1.0
        for f in self._music_ducks.values():
            fator *= f
        return max(0.0, min(1.0, fator))

    @require_audio
    def duck_music(
        self, active: bool, factor: float = 0.5, source: str = "default"
    ) -> None:
        """Liga/desliga o ducking da música (abaixa o volume sem cortar nada).

        Persistente: honrado em todo recálculo de volume, então sobrevive ao
        avanço de rotação (fim de faixa) durante a tela de Game Over.
        `active=False` remove a contribuição DESTA fonte, sem tocar nas outras.
        """
        self.set_music_duck(source, factor if active else 1.0)

    def set_music_duck(self, source: str, factor: float) -> None:
        """Define o ducking de UMA fonte. `factor >= 1.0` remove a fonte.

        Sem `@require_audio`: é chamado por frame pelo envelope da parada do
        tempo, e precisa manter o estado coerente mesmo com o áudio indisponível
        (headless/CI) — o guard de mixer fica só na aplicação do volume.
        """
        anterior = self.music_duck_factor
        if factor >= 1.0:
            self._music_ducks.pop(source, None)
        else:
            self._music_ducks[source] = max(0.0, factor)

        if self.music_duck_factor == anterior:
            return
        # §18: mudar o número não muda o som — tem que reaplicar ao stream.
        if pygame.mixer.get_init() is not None and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(self.music_target_volume())

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
        """Toca som de negação de aprimoramento (poder em cooldown).

        `button_hover` era um placeholder de MVP: um blip de menu não lê como
        recusa no meio da luta. `Usar_Depois.wav` já existia nos assets sem
        nunca ter sido registrado — cai aqui, e o hover fica de reserva.
        """
        if "upgrade_denied" in self._sounds:
            self._sounds["upgrade_denied"].play()
        elif "button_hover" in self._sounds:
            self._sounds["button_hover"].play()

    @require_audio
    def play_black_hole(self):
        """Toca o som do buraco negro e RETORNA o Channel.

        O chamador (BlackHole) guarda o canal e o para quando o vórtice morre —
        senão o clipe (longo) sobrevive ao efeito e fica tocando depois que os
        vórtices somem. Retorna None se o som não existe."""
        if "black_hole" in self._sounds:
            sound = self._sounds["black_hole"]
            sound.set_volume(self.sfx_volume * self.master_volume * 1.2)
            return sound.play()
        return None

    def stop_black_hole(self, channel: Any) -> None:
        """Para o som do buraco negro no `channel` — SÓ se ele ainda estiver
        tocando ESTE som (o pygame pode ter reusado o canal para outro som; parar
        cegamente cortaria o som errado)."""
        if channel is None or "black_hole" not in self._sounds:
            return
        try:
            if channel.get_busy() and channel.get_sound() is self._sounds["black_hole"]:
                channel.stop()
        except pygame.error:
            pass

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

    @require_audio
    def get_sound(self, sound_name: str) -> Optional[pygame.mixer.Sound]:
        """Retorna o objeto `pygame.mixer.Sound` carregado ou `None` se não existir.

        Use este método em vez de acessar internamente `._sounds` para evitar
        avisos sobre uso de atributos protegidos.
        """
        return self._sounds.get(sound_name)

    def loaded_sound_names(self) -> List[str]:
        """Nomes dos SFX carregados. Par público de `get_sound` (§1), para quem
        precisa varrer todos — os testes de volume conferem o estado real de
        cada `Sound`, e ler `_sounds` de fora borraria a fronteira."""
        return list(self._sounds.keys())

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
        """Reaplica os volumes atuais a todos os sons JÁ carregados.

        Ponto único de "os números mudaram, sincronize os objetos" — chamado
        pelos setters e por `load_config`. Sem ele os campos e o que o jogador
        ouve andam separados (ver `load_config`).

        Os tiros ficam de fora do volume geral de SFX: eles têm escala própria
        (`shot_volume_base`, mais baixa por serem disparados sem parar), que é a
        mesma que `load_sfx` grava na carga. Tratá-los junto zeraria essa
        distinção aqui e ela só voltaria no próximo `play_shot`.
        """
        final_volume = self.sfx_volume * self.master_volume
        shot_volume = self.shot_volume_base * self.master_volume
        shots = set(id(s) for s in self._sound_groups.get("shots", ()))
        for sound in self._sounds.values():
            sound.set_volume(shot_volume if id(sound) in shots else final_volume)

    @require_audio
    def stop_all(self):
        """Para todos os sons."""
        pygame.mixer.stop()

    @require_audio
    def play_theme(self, key: str | None = None):
        """Música ambiente data-driven do tema `key` (pasta audio/themes/<key>/)."""
        self.music_manager.play_theme(key)

    @require_audio
    def play_boss(self, key: str | None = None):
        """Música exclusiva data-driven do boss `key` (pasta audio/bosses/<key>/)."""
        self.music_manager.play_boss(key)

    @require_audio
    def advance_current(self):
        """Avança a rotação da playlist ativa (chamado no fim de cada faixa)."""
        self.music_manager.advance_current()

    @require_audio
    def update_music(self, dt: float):
        """Avança transições de música pendentes (1×/frame, na thread principal).

        O crossfade é cooperativo (sem worker thread): pygame não é thread-safe,
        então o carregamento/início da nova faixa acontece aqui, no loop
        principal, quando o fade-out assíncrono do SDL termina."""
        self.music_manager.update(dt)

    # Alias legado mantido para docs/compat: retoma o tema ambiente atual.
    @require_audio
    def play_background_music(self):
        self.music_manager.play_background_music()

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
        """Aplica os volumes das preferências — números E sons já carregados.

        O `_update_all_volumes()` no fim é obrigatório e era o que faltava. Os
        `Sound` do pygame guardam o volume DENTRO do objeto, gravado por
        `load_sfx()` no momento da carga; mudar só os campos
        `self.sfx_volume`/`master_volume` não alcança um som já carregado.

        E a carga sempre acontece ANTES: o `sound_manager` é um singleton
        construído no import de `game.core.sound`, quando as preferências do
        jogador ainda nem foram lidas — então os SFX nascem com o volume PADRÃO
        embutido. Sem reaplicar aqui, todo boot tocava os efeitos no volume de
        fábrica enquanto a tela de configurações exibia, corretamente, o valor
        salvo. Só mexer no slider (que chama `set_sfx_volume` →
        `_update_all_volumes`) consertava, até o próximo boot.
        """
        self.music_manager.load_config(music_vol, sfx_volume, shot_volume)
        self._update_all_volumes()

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
    def stop_looping_sfx(self):
        """Para só os SFX em canais dedicados (loops/sustentados): warning, tiros,
        lasers de boss, mina/orbe do Golem, loop do Metropolis e os cues da
        parada do tempo.

        NÃO interrompe one-shots (explosões, raio) — esses se encerram sozinhos e
        devem soar até o fim. Usado ao SAIR da cena de jogo: senão a morte fica
        muda (a explosão da nave e o som do raio são cortados pela troca de cena)."""
        self.warning_channel.stop()
        self.shot_channel.stop()
        self.boss_laser_channel.stop()
        self.boss_laser_fire_channel.stop()
        self.golem_mine_channel.stop()
        self.golem_orb_channel.stop()
        self.metropolis_laser_channel.stop()
        self.time_stop_channel.stop()

    @require_audio
    def stop_all_sfx(self):
        """Para os SFX sustentados/looping da partida (não afeta a música).

        Categoria-escopo: NÃO varre o dict inteiro de sons parando one-shots — com
        os canais dedicados reservados, one-shots (explosão da nave, ranking, raio)
        vivem nos canais livres e devem soar até o fim ("tudo pode persistir").
        Equivale a `stop_looping_sfx()`; nome mantido para os call sites existentes.
        """
        self.stop_looping_sfx()

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
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            try:
                self.music_manager.stop_music_internal()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

            # Join transition thread if running
            if self.transition_thread and self.transition_thread.is_alive():
                self.transition_thread.join(timeout=wait)

            # Quit the mixer
            try:
                pygame.mixer.quit()
            except Exception:  # pylint: disable=broad-exception-caught
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
        except Exception:  # pylint: disable=broad-exception-caught
            logging.exception("Erro ao encerrar o AudioController")


class _LazyAudioController:
    """Proxy que faz lazy initialization do AudioController.

    Permite que sound_manager seja importado ANTES de pygame.init() ser chamado,
    mas a instância real só é criada na primeira USE (quando pygame.mixer está
    pronto). Sem isto, pygame.mixer.get_init() falha no import time.
    """

    _instance: AudioController | None = None

    def __getattr__(self, name: str) -> Any:
        """Intercepta acesso a atributos, criando a instância se necessário."""
        if self._instance is None:
            self._instance = AudioController()
        return getattr(self._instance, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Intercepta atribuição."""
        if name == "_instance":
            object.__setattr__(self, name, value)
        else:
            if self._instance is None:
                self._instance = AudioController()
            setattr(self._instance, name, value)


# Instância global do gerenciador de som (proxy com lazy init)
sound_manager = _LazyAudioController()
