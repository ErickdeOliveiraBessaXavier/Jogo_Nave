from typing import TYPE_CHECKING

import pygame

from ..effects.critical_damage import CriticalDamageFX, area_from_box

if TYPE_CHECKING:
    from ...systems.hit_result import HitResult


class BossHitMixin:
    dead: bool
    is_boss: bool = True

    # Caixa do corpo. Anotadas aqui porque o fogo de vida baixa nasce delas —
    # todo boss já as tem, mas o contrato agora é explícito.
    x: float
    y: float
    w: float
    h: float
    health: int
    max_health: int

    @property
    def rect(self) -> pygame.Rect:
        raise NotImplementedError

    def take_damage(self, _amount: int) -> None: ...

    def collision_circle(self) -> tuple[float, float, float]:
        """Fallback baseado em rect — bosses com geometria custom devem override.

        Sem isso, sistemas que iteram todos os candidates (chain_shot, AoE)
        e topam com um boss sem implementação explícita quebram silenciosamente.
        """
        r = self.rect
        return float(r.centerx), float(r.centery), float(max(r.width, r.height) / 2)

    # ── Fogo e fumaça de vida baixa ──────────────────────────────────────────
    # Está AQUI, e não copiado em cada boss, porque é assinatura da família: com
    # a barra de vida removida de vários chefes por decisão de design, o fogo
    # virou o único jeito de o jogador ler "quanto falta". Boss que não o tem não
    # fica "sem um enfeite" — fica sem indicador de vida nenhum, que foi como a
    # Tríade e o Overlord nasceram.
    #
    # O efeito em si é o `effects/critical_damage`, genérico e que não conhece
    # boss nenhum: recebe razão de vida (0..1) e área de emissão.

    @property
    def critical_fx(self) -> CriticalDamageFX:
        """Instância própria do boss, criada na primeira leitura.

        Preguiçosa e não em `__init__`: o mixin não tem construtor, e dar um a
        ele obrigaria os sete bosses existentes a chamar `super().__init__()` —
        mudança larga, sem ganho, e que quebra em silêncio quem esquecer.

        O setter existe para quem quer configuração própria
        (`self.critical_fx = CriticalDamageFX(scale=1.5)` no `__init__`, como
        Golem e Meteoro fazem): sem ele a atribuição estouraria contra a
        property.
        """
        fx = self.__dict__.get("_critical_fx")
        if fx is None:
            fx = CriticalDamageFX()
            self.__dict__["_critical_fx"] = fx
        return fx

    @critical_fx.setter
    def critical_fx(self, fx: CriticalDamageFX) -> None:
        self.__dict__["_critical_fx"] = fx

    @property
    def health_ratio(self) -> float:
        return self.health / self.max_health if self.max_health > 0 else 0.0

    def critical_fx_area(self) -> pygame.Rect:
        """Onde o fogo nasce. NÃO é hitbox — sobrescreva se o casco não for a caixa.

        Sai de `x/y/w/h` crus e não de `self.rect` de propósito: vários bosses
        devolvem um rect fora da tela enquanto não podem levar dano, e o fogo
        sumiria junto (ver `area_from_box`).
        """
        return area_from_box(self.x, self.y, self.w, self.h)

    def update_critical_fx(self, dt: float) -> None:
        """Chame no `update` do boss. `dt` cru: é dano de casco, não animação."""
        self.critical_fx.update(dt, self.health_ratio, self.critical_fx_area())

    def draw_critical_fx(
        self, surface: pygame.Surface, offset_x: float = 0.0, offset_y: float = 0.0
    ) -> None:
        """Chame no `draw` do boss, depois do corpo. Só desenha (§3)."""
        self.critical_fx.draw(surface, offset_x, offset_y)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...core.config import config as cfg
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=cfg.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead
