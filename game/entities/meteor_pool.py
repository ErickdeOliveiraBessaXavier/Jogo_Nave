from typing import List

import pygame

from .meteor import Meteor


class MeteorPool:
    """
    Object pool for meteors: gerencia uma coleção reutilizável de meteoros,
    evitando criar e destruir objetos repetidamente.

    Tracks pool efficiency and prevents unbounded growth.
    """

    def __init__(
        self,
        initial_size: int = 100,
        max_size: int = 500,
        is_side_scroll: bool = False,
    ):
        """
        Inicializa o pool com meteoros inativos.

        Args:
            initial_size: Quantidade inicial de meteoros no pool
            max_size: Tamanho máximo permitido (evita crescimento infinito)
            is_side_scroll: Se está em modo side-scroll

        Raises:
            ValueError: If max_size < initial_size
        """
        if max_size < initial_size:
            raise ValueError("max_size must be greater than or equal to initial_size")

        self.initial_size = initial_size
        self.max_size = max_size
        self.is_side_scroll = is_side_scroll

        self.pool: List[Meteor] = []
        self.active: List[Meteor] = []

        # Statistics
        self.peak_active = 0
        self.total_created = 0
        self.reused_count = 0

        # Pré-cria meteoros inativos
        for _ in range(initial_size):
            meteor = Meteor()
            meteor.active = False
            meteor.dead = True
            self.pool.append(meteor)
            self.total_created += 1

    def get(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ) -> Meteor:
        """
        Obtém um meteoro do pool, reutilizando um inativo ou criando novo.

        Args:
            size, x, y, vx, vy: Parâmetros de configuração do meteoro

        Returns:
            Meteoro ativo e configurado
        """
        # Procura um meteoro inativo no pool
        for meteor in self.pool:
            if not meteor.active:
                meteor.reset(size=size, x=x, y=y, vx=vx, vy=vy)
                meteor.is_side_scroll = self.is_side_scroll
                self.active.append(meteor)
                self.reused_count += 1
                self._update_peak()
                return meteor

        # Se não houver disponível, tenta criar novo
        if len(self.pool) < self.max_size:
            meteor = Meteor(size=size, x=x, y=y, vx=vx, vy=vy)
            meteor.is_side_scroll = self.is_side_scroll
            self.pool.append(meteor)
            self.active.append(meteor)
            self.total_created += 1
            self._update_peak()
            return meteor
        else:
            # Pool está no máximo - reutiliza o mais antigo (fallback)
            if self.active:
                meteor = self.active.pop(0)
                meteor.reset(size=size, x=x, y=y, vx=vx, vy=vy)
                meteor.is_side_scroll = self.is_side_scroll
                self.active.append(meteor)
                self._update_peak()
                return meteor
            else:
                # Nunca deve chegar aqui
                m = Meteor(size=size, x=x, y=y, vx=vx, vy=vy)
                m.is_side_scroll = self.is_side_scroll
                return m

    def release(self, meteor: Meteor) -> None:
        """
        Libera um meteoro de volta ao pool, marcando como inativo.

        Args:
            meteor: Meteoro a ser desativado
        """
        if meteor in self.active:
            meteor.active = False
            meteor.dead = True
            self.active.remove(meteor)

    def update(self, dt: float, is_side_scroll: bool | None = None):
        """
        Atualiza todos os meteoros ativos e libera os que morreram.

        Args:
            dt: Delta time em segundos
            is_side_scroll: Se está em modo side-scroll (usa valor armazenado se None)
        """
        if is_side_scroll is not None:
            self.is_side_scroll = is_side_scroll

        for meteor in self.active[:]:  # Copia a lista para iterar com segurança
            meteor.update(dt, self.is_side_scroll)
            if meteor.dead:
                self.release(meteor)

    def draw(self, screen: pygame.Surface):
        """
        Desenha todos os meteoros ativos.

        Args:
            screen: Superfície do pygame onde desenhar
        """
        for meteor in self.active:
            meteor.draw(screen)

    def clear_active(self):
        """Remove todos os meteoros ativos, devolvendo-os ao pool."""
        for meteor in self.active[:]:
            self.release(meteor)

    def get_active_count(self) -> int:
        """Retorna a quantidade de meteoros atualmente ativos."""
        return len(self.active)

    def get_pool_size(self) -> int:
        """Retorna o tamanho total do pool (ativos + inativos)."""
        return len(self.pool)

    def _update_peak(self) -> None:
        """Track peak active count for statistics."""
        self.peak_active = max(self.peak_active, len(self.active))

    def get_stats(self) -> dict[str, int | float]:
        """
        Get pool statistics for monitoring.

        Returns:
            Dictionary with usage metrics
        """
        total = max(1, self.total_created)
        return {
            "active": len(self.active),
            "inactive": len(self.pool) - len(self.active),
            "pool_total": len(self.pool),
            "peak_active": self.peak_active,
            "max_size": self.max_size,
            "total_created": self.total_created,
            "reused": self.reused_count,
            "efficiency_percent": (self.reused_count / total) * 100,
        }
