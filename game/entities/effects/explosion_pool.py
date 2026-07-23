"""
Pool de explosões para reutilização de objetos.
Reduz alocação de memória e garbage collection.
"""

from typing import Dict, List, Sequence, Union

import pygame

from .explosion import Explosion, ImpactPattern


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

    def get(
        self,
        x: float,
        y: float,
        size: int = 30,
        explosion_type: Sequence[tuple[int, int, int]] | None = None,
        pattern: str = ImpactPattern.BURST,
    ) -> Explosion:
        """
        Obtém uma explosão do pool (reutiliza se possível).

        Args:
            x, y: Posição da explosão
            size: Tamanho da explosão
            explosion_type: Tipo de explosão (ExplosionType.ALIEN, ExplosionType.SLIME, etc)
            pattern: Forma do efeito (ImpactPattern.*)

        Returns:
            Explosão configurada e pronta para uso
        """
        if self.available:
            # Reutilizar explosão existente
            explosion = self.available.pop()
            explosion.reset(x, y, size, explosion_type, pattern)
        else:
            # Pool vazio, criar nova (acontece raramente)
            explosion = Explosion(x, y, size, explosion_type, pattern)

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
            explosion.explosion_type = None  # ← ATUALIZAR ESTA LINHA
            explosion.pattern = ImpactPattern.BURST
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
