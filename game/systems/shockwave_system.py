"""shockwave_system.py — a morte de cada inimigo vira uma explosão pequena.

Reage a `EnemyDestroyed` no EventBus (§2): o upgrade não sabe quem morreu, o
inimigo não sabe que existe upgrade, e a cena não intermedeia. O evento já
carrega a posição — era o gancho certo esperando por um consumidor.

**A onda é um `ExplosiveEffect`**, a mesma peça do tiro explosivo. Ela já traz
visual, dano em área com dedup por inimigo (`hit_enemies`) e ciclo de vida
completo, tudo percorrido pelo `explosive_effects_vs_enemies`. Criar uma
entidade paralela para desenhar outro círculo que causa dano em área seria uma
segunda implementação da mesma coisa — o que muda entre as duas é raio, dano e
cor, e isso são parâmetros.

Boss não gera onda, e não por regra deste sistema: `CollisionPhysics.apply_hit`
já não emite `EnemyDestroyed` para quem tem `is_boss`. Herdamos o filtro de
graça, e é o comportamento certo — uma onda por peça de boss morta seria dano
grátis contínuo na luta em que ele menos deveria existir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..core.upgrades_config import (
    SHOCKWAVE_COLOR,
    SHOCKWAVE_DAMAGE,
    SHOCKWAVE_LIFETIME,
    SHOCKWAVE_MAX_ACTIVE,
    SHOCKWAVE_RADIUS,
)
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..systems.entity_manager import EntityManager


class ShockwaveSystem:
    """Cria a explosão pós-morte enquanto algum jogador tem o upgrade ativo.

    Dependências pelo construtor, sem referência à cena (§9): o manager para
    materializar a onda, e um **callback** para a única pergunta que o sistema
    não sabe responder sozinho — "o upgrade está ligado?". Em coop basta um
    jogador com ele ativo: a morte é do mundo, não de quem deu o tiro.
    """

    def __init__(
        self,
        event_bus: "EventBus",
        entity_manager: "EntityManager",
        is_active: Callable[[], bool],
    ) -> None:
        self._bus = event_bus
        self._entity_manager = entity_manager
        self._is_active = is_active
        self._bus.on(events.EnemyDestroyed, self._on_enemy_destroyed)

    def _on_enemy_destroyed(self, event: events.EnemyDestroyed) -> None:
        if not self._is_active():
            return
        if not self._under_cap():
            return

        x, y = event.position
        self._entity_manager.spawn_explosive_effect(
            x,
            y,
            radius=SHOCKWAVE_RADIUS,
            damage=SHOCKWAVE_DAMAGE,
            lifetime=SHOCKWAVE_LIFETIME,
            color=SHOCKWAVE_COLOR,
        )
        self._clear_nearby_projectiles(x, y)

    def _under_cap(self) -> bool:
        """Há espaço para mais uma onda viva?

        O teto NÃO é só orçamento de frame — é o que garante que a cascata
        termina. A onda mata, cada morte emite `EnemyDestroyed`, e o handler
        acrescenta outra onda à MESMA lista que o `explosive_effects_vs_enemies`
        está percorrendo naquele instante. Sem teto, um enxame denso realimenta
        o laço dentro do próprio frame.

        Conta a lista inteira (não só as ondas): ela é compartilhada com o tiro
        explosivo, e o que se está limitando é o custo total de efeitos de área
        vivos.
        """
        return len(self._entity_manager.explosive_effects) < SHOCKWAVE_MAX_ACTIVE

    def _clear_nearby_projectiles(self, x: float, y: float) -> None:
        """Apaga os projéteis inimigos apanhados pela onda.

        É a parte que o jogador sente como alívio, e é geometria pura — não
        escreve posição de ninguém, só marca `dead` (o sweep de cada lista
        remove depois). Consulta a `enemy_projectile_grid` (§8), que já unifica
        balas de alien, da serpente, orbes de energia, orbes orbitais e neon
        bolts; feixes contínuos (lasers de boss, eye lasers) não estão nela e
        ficam de fora de propósito — "apagar" um feixe não tem significado.
        """
        grid = self._entity_manager.enemy_projectile_grid
        r = SHOCKWAVE_RADIUS
        r2 = r * r
        for proj in grid.query(x - r, y - r, r * 2, r * 2):
            if getattr(proj, "dead", False):
                continue
            rect = getattr(proj, "rect", None)
            if rect is None:
                continue
            dx = rect.centerx - x
            dy = rect.centery - y
            if dx * dx + dy * dy <= r2:
                proj.dead = True

    def cleanup(self) -> None:
        """Remove o handler do bus (§2): sem isto o sistema vaza com a cena."""
        self._bus.off(events.EnemyDestroyed, self._on_enemy_destroyed)
