"""
Pool de explosões para reutilização de objetos.
Reduz alocação de memória e garbage collection.
"""

import random
import math
import pygame
from typing import List, Dict, Union
from ..entities.explosion import Explosion
from ..core.config import config as Config


class ExplosionPool:
    """
    Pool de objetos Explosion para reutilização.

    Mantém uma lista de explosões "disponíveis" (inativas) e "ativas".
    Quando uma explosão termina, retorna ao pool ao invés de ser destruída.
    """

    def __init__(self, initial_size: int = 50):
        """
        Inicializa o pool com explosões pré-alocadas.

        Args:
            initial_size: Número de explosões criadas antecipadamente
        """
        self.available: List[Explosion] = []
        self.active: List[Explosion] = []

        # Pré-alocar explosões
        for _ in range(initial_size):
            explosion = Explosion(0, 0, size=30)
            # Marcar como finalizada
            explosion.time = 0
            explosion.particles.clear()
            self.available.append(explosion)

    def get(self, x: float, y: float, size: int = 30, is_slime: bool = False, custom_color: tuple[int, int, int, int] | None = None) -> Explosion:
        """
        Obtém uma explosão do pool (reutiliza se possível).

        Args:
            x, y: Posição da explosão
            size: Tamanho da explosão
            is_slime: Se é uma explosão de slime
            custom_color: Cor personalizada para a explosão (opcional)

        Returns:
            Explosão configurada e pronta para uso
        """
        if self.available:
            # Reutilizar explosão existente
            explosion = self.available.pop()
        else:
            # Pool vazio, criar nova (acontece raramente)
            explosion = Explosion(0, 0, size=30, is_slime=is_slime)

        # Reconfigurar explosão completamente (simula __init__)
        explosion.x = x
        explosion.y = y
        explosion.size = size
        explosion.is_slime = is_slime
        explosion.custom_color = custom_color

        # Recalcular tempo baseado no tamanho
        explosion.time = Config.EXPLOSION_DURATION * (size / 40)

        # Recriar partículas
        count = min(20 + size // 4, 40)
        explosion.particles = []

        for _ in range(count):
            angle = random.uniform(0, 360)
            rad_angle = math.radians(angle)
            base_speed = random.uniform(150, 300) * (size / 20)

            vx = base_speed * math.cos(rad_angle)
            vy = base_speed * math.sin(rad_angle)

            px, py = x, y

            life = random.uniform(explosion.time * 0.6, explosion.time)
            explosion.particles.append([px, py, vx, vy, life])

        self.active.append(explosion)
        return explosion

    def release(self, explosion: Explosion) -> None:
        """
        Devolve uma explosão ao pool para reutilização futura.

        Args:
            explosion: Explosão a ser devolvida
        """
        if explosion in self.active:
            self.active.remove(explosion)
            # Marcar como finalizada para não ser desenhada
            explosion.time = 0
            explosion.particles.clear()
            explosion.custom_color = None  # Resetar cor personalizada
            self.available.append(explosion)

    def update(self, dt: float) -> None:
        """
        Atualiza todas as explosões ativas e libera as finalizadas.

        Args:
            dt: Delta time em segundos
        """
        # Iterar sobre cópia da lista para remoção segura
        for explosion in self.active[:]:
            explosion.update(dt)

            # Verificar se terminou
            if explosion.finished():
                self.release(explosion)

    def draw_all(self, surface: pygame.Surface) -> None:
        """
        Desenha todas as explosões ativas.

        Args:
            surface: pygame.Surface para desenhar
        """
        for explosion in self.active:
            explosion.draw(surface)

    def clear_active(self) -> None:
        """
        Limpa todas as explosões ativas, devolvendo ao pool.
        Útil para transições de fase ou game over.
        """
        for explosion in self.active[:]:
            self.release(explosion)

    # Métodos de debug/estatísticas
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Retorna estatísticas do pool para debug."""
        total = len(self.active) + len(self.available)
        return {
            "active": len(self.active),
            "available": len(self.available),
            "total": total,
            "utilization": len(self.active) / total if total > 0 else 0,
        }
