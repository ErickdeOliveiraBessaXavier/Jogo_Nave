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
class ScoreGained(Event):
    """O jogador ganhou pontos (ex: coletar estrela, bônus)."""

    points: int
    position: Optional[tuple[float, float]] = None


@dataclass
class PlaySound(Event):
    """Solicita a reprodução de um efeito sonoro."""

    sound_name: str
    volume: float = 1.0


@dataclass
class MusicStateChange(Event):
    """Solicita uma mudança no estado da música (play, stop, fade)."""

    state: Any  # Ex: MusicState.BOSS_FIGHT
    fade_ms: int = 0


@dataclass
class ScreenShake(Event):
    """Solicita um efeito de tremor de tela."""

    intensity: int
    duration: float


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


@dataclass
class GameStateChange(Event):
    """Informa uma mudança no estado principal do jogo (preparando, jogando, etc)."""

    new_state: Any  # Ex: GameState.PLAYING
