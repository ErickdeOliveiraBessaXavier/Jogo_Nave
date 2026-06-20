"""boss_fight_controller.py — Controlador isolado do ciclo de vida do boss fight.

Extrai de PlayingScene: spawn do boss, warning system (3 estágios), cleanup de
hostis com blink e timeout, explosões de morte do boss e restauração de estado.

PlayingScene não é referenciada — comunicação via callbacks e retornos explícitos.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Callable, Optional

from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.sound_config import MusicState
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..core.levels import LevelConfig
    from ..systems.entity_manager import EntityManager

logger = logging.getLogger(__name__)

# Backstop anti-softlock: tempo máximo aguardando hostis ainda NA TELA após a
# cota antes do force-kill (com blink de aviso). Normalmente a fase avança bem
# antes — assim que não há mais hostis na tela (ver progressão).
_ENEMY_CLEANUP_DURATION: float = 20.0
_BLINK_FAST_INTERVAL: float = 0.05
_BLINK_SLOW_INTERVAL: float = 0.40


class BossFightController:
    """Gerencia o ciclo completo de um boss fight.

    Responsabilidades:
    - Spawn do boss (baseado em level_config.boss_type)
    - Warning system em 3 estágios antes do boss
    - Cleanup de hostis restantes com blink e timeout
    - Explosões e limpeza de entidades na morte do boss
    - Emissão de eventos de áudio/visual via EventBus
    - Screen shake via callback (sem referência à PlayingScene)

    Comunicação com PlayingScene:
    - `screen_shake_request(duration, intensity)` → seta shake na cena
    - `background_getter()` → retorna background atual do renderer
    - `start()` / `end()` → chamados pela cena no momento certo
    - `update_warning()` → retorna True quando boss deve ser spawnado
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        event_bus: EventBus,
        screen_shake_request: Callable[[float, int], None],
        background_getter: Callable[[], Any | None],
    ) -> None:
        self._em = entity_manager
        self._bus = event_bus
        self._shake = screen_shake_request
        self._get_bg = background_getter

        # Boss fight
        self.active: bool = False
        self.boss_type: Optional[str] = None
        self.boss_music_started: bool = False

        # Pre-boss warning
        self.pre_boss_transition: bool = False
        self.warning_stage: int = 0
        self.warning_stage_timer: float = 0.0
        self.warning_timer: float = 0.0
        self.warning_sound_played: bool = False
        self.music_fade_started: bool = False

        # Enemy cleanup (hostis restantes após kill threshold)
        self.enemy_cleanup_active: bool = False
        self.enemy_cleanup_timer: float = 0.0
        self.enemy_visible: bool = True
        self.enemy_blink_timer: float = 0.0
        self.enemy_blink_interval: float = _BLINK_SLOW_INTERVAL

    def reset(self) -> None:
        """Reinicia todo o estado entre níveis."""
        self.active = False
        self.boss_type = None
        self.boss_music_started = False
        self.pre_boss_transition = False
        self.warning_stage = 0
        self.warning_stage_timer = 0.0
        self.warning_timer = 0.0
        self.warning_sound_played = False
        self.music_fade_started = False
        self.enemy_cleanup_active = False
        self.enemy_cleanup_timer = 0.0
        self.enemy_visible = True
        self.enemy_blink_timer = 0.0
        self.enemy_blink_interval = _BLINK_SLOW_INTERVAL

    def begin_cleanup(self) -> None:
        """Inicia a fase de cleanup de hostis ainda ativos no mapa."""
        self.enemy_cleanup_active = True
        self.enemy_cleanup_timer = 0.0
        logger.info("Aguardando limpeza final de hostis.")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, level_config: LevelConfig, enemy_health_multiplier: float) -> None:
        """Spawna o boss, define o estado ativo e inicia música/shake."""
        self.pre_boss_transition = False
        self.warning_sound_played = False
        self.warning_stage = 0
        self.warning_stage_timer = 0.0
        self.warning_timer = 0.0
        self.music_fade_started = False
        self.boss_music_started = False
        self.active = True
        self.enemy_visible = True
        self.enemy_blink_timer = 0.0

        self._shake(Config.BOSS_ENTRY_SHAKE_DURATION, Config.SCREEN_SHAKE_NORMAL)
        sound_manager.stop_warning()
        sound_manager.stop_all_sfx()

        if not level_config.boss_type:
            return

        self._spawn_boss(level_config, enemy_health_multiplier)
        self._cache_boss_type()
        self._set_day_night_paused(True)
        self._emit_boss_music()

    def end(
        self,
        score_multiplier_active: bool,
        score_multiplier_value: float,
    ) -> int:
        """Finaliza o boss fight e retorna o score ganho pelo jogador."""
        boss = self._em.boss
        if not boss:
            return 0

        from ..entities.giant_meteor_boss import GiantMeteorBoss
        from ..entities.mountain_serpent_boss import MountainSerpentBoss

        if isinstance(boss, MountainSerpentBoss):
            boss_center: tuple[float, float] = (boss.head_x, boss.head_y)
        else:
            boss_center = (boss.x + boss.w / 2, boss.y + boss.h / 2)

        self._shake(
            Config.SCREEN_SHAKE_BOSS_DEATH_DURATION, Config.SCREEN_SHAKE_BOSS_DEATH
        )
        self._bus.emit(
            events.BossDefeated(
                boss_type=self.boss_type or "normal", position=boss_center
            )
        )

        # Explosões em anel
        num_exp = Config.BOSS_EXPLOSION_COUNT
        radius = Config.BOSS_EXPLOSION_RADIUS
        for i in range(num_exp):
            angle = math.radians((360 / num_exp) * i)
            self._em.spawn_explosion(
                boss_center[0] + radius * math.cos(angle),
                boss_center[1] + radius * math.sin(angle),
                size=Config.BOSS_EXPLOSION_SMALL_SIZE,
            )

        # Limpar spikes
        for spike in self._em.spikes:
            if spike.state != "respawning":
                self._em.spawn_explosion(spike.center_x, spike.center_y, size=15)
        self._em.spikes.clear()

        # GiantMeteorBoss: destruir meteoros ativos
        if isinstance(boss, GiantMeteorBoss):
            for meteor in self._em.meteor_pool.active:
                self._em.spawn_explosion(
                    meteor.x + meteor.w / 2,
                    meteor.y + meteor.h / 2,
                    size=max(12, int(meteor.w // 2)),
                )
            self._em.meteor_pool.clear_active()

        # Limpar inimigos e formações
        self._explode_entities(list(self._em.enemies))
        self._em.enemies.clear()
        for formation in self._em.formations:
            self._explode_entities(list(formation.enemies))
            formation.dead = True
        self._em.formations.clear()

        # NÃO limpamos boss_lasers aqui: a cerca elétrica da Fase 3 precisa rodar sua
        # animação de SAÍDA (dissipação elegante) durante a janela pós-morte. Os feixes
        # se auto-removem ao fim do fade (dead → cleanup); a limpeza definitiva é na
        # transição de nível (`clear_for_level_transition`), evitando vazamento.

        self._em.boss = None
        self.active = False
        self.boss_type = None
        self.music_fade_started = False
        self.boss_music_started = False
        self._set_day_night_paused(False)
        self._bus.emit(events.MusicStateChange(state=MusicState.GAME, fade_ms=0))

        boss_score = Config.BOSS_DEFEAT_SCORE
        if score_multiplier_active:
            boss_score = int(boss_score * score_multiplier_value)
        return boss_score

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_warning(self, dt: float, has_active_enemies: bool) -> bool:
        """Atualiza o warning system em 3 estágios.

        Retorna True quando o boss deve ser spawnado (cena chama start()).
        """
        if not self.pre_boss_transition:
            return False

        # Estágio 0 → 1 quando a tela limpar de inimigos
        if not has_active_enemies and self.warning_stage == 0:
            self.warning_stage = 1
            self.warning_stage_timer = 0.0
            self.warning_sound_played = False

        self.warning_stage_timer += dt
        self.warning_timer = max(0.0, self.warning_timer - dt)

        if self.warning_stage == 1:
            if (
                not self.music_fade_started
                and self.warning_stage_timer >= Config.BOSS_MUSIC_FADE_OUT_START
            ):
                self._bus.emit(
                    events.MusicStateChange(
                        state=MusicState.SILENCE,
                        fade_ms=int(Config.BOSS_MUSIC_FADE_OUT_DURATION * 1000),
                    )
                )
                self.music_fade_started = True

            if self.warning_stage_timer >= Config.BOSS_PRE_WARNING_DELAY:
                self.warning_stage = 2
                self.warning_stage_timer = 0.0
                self.warning_timer = Config.BOSS_WARNING_DURATION
                self._shake(Config.BOSS_WARNING_DURATION, Config.SCREEN_SHAKE_NORMAL)
                if not self.warning_sound_played:
                    self._bus.emit(events.PlaySound(sound_name="warning"))
                    self.warning_sound_played = True

        elif self.warning_stage == 2:
            if self.warning_stage_timer >= Config.BOSS_WARNING_DURATION:
                self.warning_stage = 3
                self.warning_stage_timer = 0.0
                self.warning_timer = 0.0
                sound_manager.stop_warning()

        elif self.warning_stage == 3:
            if self.warning_stage_timer >= Config.BOSS_POST_WARNING_DELAY:
                return True  # Sinaliza à cena para chamar start()

        return False

    def update_cleanup(self, dt: float) -> None:
        """Blink e timeout de hostis restantes após o kill threshold."""
        if not self.enemy_cleanup_active:
            return

        self.enemy_cleanup_timer += dt
        time_remaining = max(0.0, _ENEMY_CLEANUP_DURATION - self.enemy_cleanup_timer)

        if 0.0 < time_remaining <= 5.0:
            blink_t = max(0.0, min(1.0, time_remaining / 5.0))
            self.enemy_blink_interval = (
                _BLINK_FAST_INTERVAL
                + (_BLINK_SLOW_INTERVAL - _BLINK_FAST_INTERVAL) * blink_t
            )
            self.enemy_blink_timer += dt
            if self.enemy_blink_timer >= self.enemy_blink_interval:
                self.enemy_blink_timer = 0.0
                self.enemy_visible = not self.enemy_visible
        elif time_remaining <= 0.0:
            self.enemy_visible = True
            self._force_kill_stage_hostiles()
            self.enemy_cleanup_active = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cache_boss_type(self) -> None:
        boss = self._em.boss
        if not boss:
            self.boss_type = None
            return

        # Cada boss declara BOSS_TYPE_NAME como class attribute.
        # Consultar via getattr elimina a cascata de isinstance.
        self.boss_type = getattr(type(boss), "BOSS_TYPE_NAME", "normal")

    def _spawn_boss(
        self, level_config: LevelConfig, enemy_health_multiplier: float
    ) -> None:
        from ..entities.cloud_archmage_boss import CloudArchmageBoss
        from ..entities.giant_meteor_boss import GiantMeteorBoss
        from ..entities.Inimigos_Tema_Cidade.metropolis_overlord_boss import (
            MetropolisOverlordBoss,
        )
        from ..entities.mountain_serpent_boss import MountainSerpentBoss
        from ..entities.stone_golem_boss import StoneGolemBoss

        boss_type = level_config.boss_type
        agg = self._em.aggressiveness_multiplier
        if boss_type == StoneGolemBoss:
            boss = StoneGolemBoss(
                Config.SCREEN_WIDTH / 2 - 50,
                50,
                difficulty_multiplier=enemy_health_multiplier,
                event_bus=self._bus,
            )
            self._em.boss = boss
        elif boss_type == MountainSerpentBoss:
            scaled_health = int(
                MountainSerpentBoss.DEFAULT_HEALTH * enemy_health_multiplier
            )
            self._em.spawn_mountain_serpent_boss(
                health=scaled_health,
                block_health_multiplier=enemy_health_multiplier,
            )
        elif boss_type == GiantMeteorBoss:
            boss = self._em.spawn_giant_meteor_boss()
            boss.health = int(boss.health * enemy_health_multiplier)
            boss.max_health = boss.health
        elif boss_type == CloudArchmageBoss:
            boss = CloudArchmageBoss(
                difficulty_multiplier=enemy_health_multiplier,
                aggressiveness_multiplier=agg,
            )
            self._em.boss = boss
        elif boss_type == MetropolisOverlordBoss:
            boss = MetropolisOverlordBoss(
                Config.SCREEN_WIDTH / 2 - MetropolisOverlordBoss.WIDTH / 2,
                60,
                difficulty_multiplier=enemy_health_multiplier,
                aggressiveness_multiplier=agg,
                event_bus=self._bus,
            )
            self._em.boss = boss
        else:
            assert boss_type is not None
            boss = boss_type(Config.SCREEN_WIDTH / 2 - 50, 50)
            boss.health = int(boss.health * enemy_health_multiplier)
            boss.max_health = boss.health
            self._em.boss = boss

        # Aggressiveness para todos os bosses (não só CloudArchmage). Cada boss
        # decide o que escalar lendo `self.aggressiveness_multiplier` nos seus
        # ticks. Bosses que ignorarem o atributo permanecem inalterados (sem
        # regressão). Atribuímos via setattr para não exigir mudança nos
        # construtores dos 5 bosses já existentes.
        active_boss = self._em.boss
        if active_boss is not None and not hasattr(
            active_boss, "aggressiveness_multiplier"
        ):
            setattr(active_boss, "aggressiveness_multiplier", agg)

    def _emit_boss_music(self) -> None:
        # Data-driven: a faixa do boss vem da pasta `audio/bosses/<BOSS_TYPE_NAME>/`.
        # Basta a chave; nenhum mapa por boss no código. Boss sem pasta cai no
        # fallback legado dentro do MusicManager.
        boss = self._em.boss
        key = getattr(boss, "BOSS_TYPE_NAME", None)
        self._bus.emit(
            events.MusicStateChange(state=MusicState.BOSS, key=key, fade_ms=0)
        )
        self.boss_music_started = True

    def _set_day_night_paused(self, paused: bool) -> None:
        bg = self._get_bg()
        if bg is not None:
            bg.set_day_night_paused(paused)

    def _explode_entities(self, entities: list[Any]) -> None:
        for entity in entities:
            cx = float(getattr(entity, "x", 0.0)) + getattr(entity, "w", 0) / 2
            cy = float(getattr(entity, "y", 0.0)) + getattr(entity, "h", 0) / 2
            self._em.spawn_explosion(cx, cy, size=15)

    def _force_kill_stage_hostiles(self) -> None:
        em = self._em
        for e in em.enemies:
            if not getattr(e, "dead", False):
                e.dead = True
        for f in em.formations:
            if not getattr(f, "dead", False):
                for e in f.get_enemies():
                    if not getattr(e, "dead", False):
                        e.dead = True
        for m in em.boulders:
            if not m.dead:
                m.dead = True
        for s in em.attack_debris:
            if not s.dead:
                s.dead = True
        for r in em.orbital_debris:
            if not r.dead and getattr(r, "causes_damage", False):
                r.dead = True
