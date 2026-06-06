from typing import Set

import pygame


class ExplosiveEffect:
    """Efeito visual simples de explosão - círculo que expande e desaparece.

    `delay` adia a ativação (dano + desenho) por N segundos sem custo de scheduler
    externo: o efeito é criado já agendado e "acende" sozinho quando o atraso zera.
    Usado para encadear explosões (ex.: resíduos energéticos da CityMine). `color`
    tinge o círculo (default branco) para temas como o Neon City.
    """

    def __init__(
        self,
        x: float,
        y: float,
        radius: float = 60.0,
        lifetime: float = 0.4,
        damage: int = 50,
        delay: float = 0.0,
        color: tuple[int, int, int] = (255, 255, 255),
    ):
        self.x = x
        self.y = y
        self.max_radius = radius
        self.lifetime = lifetime
        self.timer = 0.0
        self.dead = False
        self.damage = damage
        self.delay = max(0.0, delay)
        self.color = color

        # Rastrear inimigos já atingidos
        self.hit_enemies: Set[int] = set()

    @property
    def damage_active(self) -> bool:
        """Retorna True se a zona de dano ainda está ativa (e já passou o delay)."""
        return not self.dead and self.delay <= 0.0 and self.timer < self.lifetime * 0.8

    @property
    def current_damage_radius(self) -> float:
        """Retorna o raio atual da zona de dano."""
        if not self.damage_active:
            return 0.0

        # Expansão rápida no início
        progress = min(1.0, self.timer / (self.lifetime * 0.3))
        ease_out = 1 - (1 - progress) ** 3
        return self.max_radius * ease_out

    def update(self, dt: float) -> None:
        if self.delay > 0.0:
            self.delay -= dt
            if self.delay > 0.0:
                return
            self.delay = 0.0  # acabou de acender; o resto do dt vira lifetime abaixo
        self.timer += dt
        if self.timer >= self.lifetime:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead or self.delay > 0.0:
            return

        # Progresso da animação (0.0 a 1.0)
        progress = min(1.0, self.timer / self.lifetime)

        # Expansão suave
        ease_out = 1 - (1 - progress) ** 3
        current_radius = int(self.max_radius * ease_out)

        if current_radius <= 0:
            return

        # Fade-out suave: começa opaco (255) e vai perdendo transparência
        alpha = int(255 * (1 - progress))

        if alpha <= 0:
            return

        # Criar surface para transparência
        surf_size = current_radius * 2 + 10
        effect_surface = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        center = (surf_size // 2, surf_size // 2)

        # Círculo preenchido (cor temática) com fade-out
        pygame.draw.circle(
            effect_surface,
            (*self.color, alpha),
            center,
            current_radius,
            0,  # Preenchido
        )

        # Desenhar na tela
        blit_x = int(self.x) - surf_size // 2
        blit_y = int(self.y) - surf_size // 2
        surface.blit(effect_surface, (blit_x, blit_y))
