"""
game_events.py - Definições de eventos de jogo tipados.

Este módulo centraliza todas as classes de eventos que podem ser emitidas
pelo EventBus. Usar dataclasses em vez de dicionários ou strings
oferece segurança de tipo, autocompletar e uma estrutura clara para
cada evento.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Event:
    """Classe base para todos os eventos do jogo."""

    pass


@dataclass
class PlayerShot(Event):
    """A nave do jogador disparou um projétil."""

    ship_type: str
    projectile_type: str
    position: tuple[float, float]
    charge_level: float = 1.0


@dataclass
class EnemyDestroyed(Event):
    """Um inimigo foi destruído."""

    enemy_type: str
    position: tuple[float, float]
    points: int


@dataclass
class BossDefeated(Event):
    """O boss do nível foi derrotado."""

    boss_type: str
    position: tuple[float, float]


@dataclass
class PowerupCollected(Event):
    """O jogador coletou um power-up."""

    powerup_type: str
    position: tuple[float, float]


@dataclass
class PlayerDamaged(Event):
    """A nave do jogador sofreu dano."""

    damage: int
    remaining_lives: int
    is_game_over: bool = False


@dataclass
class GameOver(Event):
    """O jogo terminou."""

    final_score: int
    level_reached: int


@dataclass
class LevelCleared(Event):
    """O jogador completou um nível."""

    level_number: int
    score: int
    time_taken: float


@dataclass
class PlaySound(Event):
    """Solicita a reprodução de um efeito sonoro."""

    sound_name: str
    volume: float = 1.0


@dataclass
class MusicStateChange(Event):
    """Solicita uma mudança no estado da música (play, stop, fade).

    `key` identifica QUAL faixa data-driven tocar: para GAME é a chave do tema
    (`WorldTheme.value`); para BOSS é o `BOSS_TYPE_NAME`. `None` em GAME retoma o
    tema atual; irrelevante para MENU/SILENCE.
    """

    state: Any  # MusicState (MENU | GAME | BOSS | SILENCE)
    fade_ms: int = 0
    key: str | None = None


@dataclass
class ScreenShake(Event):
    """Solicita um efeito de tremor de tela."""

    intensity: int
    duration: float


@dataclass
class ImpactFlash(Event):
    """Solicita um flash branco curtíssimo de tela (impact frame / white frames).

    `alpha` = opacidade de pico (0-255); `duration` em segundos (1-3 frames).
    Usar com moderação — só para momentos de impacto importantes.
    """

    duration: float = 0.05
    alpha: int = 180


@dataclass
class SpawnEffect(Event):
    """Solicita o spawn de um efeito visual (ex: explosão)."""

    effect_type: str
    position: tuple[float, float]
    size: int = 15


@dataclass
class SpawnFloatingScore(Event):
    """Solicita a exibição de um score flutuante."""

    x: float
    y: float
    score: int
    color: Optional[tuple[int, int, int]] = None
