from typing import List
import pygame
from .meteor import Meteor


class MeteorPool:
    """
    Pool Pattern para meteoros: gerencia uma coleção reutilizável de meteoros,
    evitando criar e destruir objetos repetidamente.
    """

    def __init__(self, initial_size: int = 100, is_side_scroll: bool = False):
        """
        Inicializa o pool com meteoros inativos.

        Args:
            initial_size: Quantidade inicial de meteoros no pool
            is_side_scroll: Se está em modo side-scroll
        """
        self.pool: List[Meteor] = []
        self.active: List[Meteor] = []
        self.is_side_scroll = is_side_scroll

        # Pré-cria meteoros inativos
        for _ in range(initial_size):
            meteor = Meteor()
            meteor.active = False
            meteor.dead = True
            self.pool.append(meteor)

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
                self.active.append(meteor)
                return meteor

        # Se não houver disponível, cria novo
        meteor = Meteor(size=size, x=x, y=y, vx=vx, vy=vy)
        self.pool.append(meteor)
        self.active.append(meteor)
        return meteor

    def release(self, meteor: Meteor):
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
