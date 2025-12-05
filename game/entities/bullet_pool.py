from typing import List
import pygame
from .bullet import Bullet


class BulletPool:
    """
    Pool Pattern para balas: gerencia uma coleção reutilizável de balas,
    evitando criar e destruir objetos repetidamente.
    """

    def __init__(self, initial_size: int = 50):
        """
        Inicializa o pool com balas inativas.

        Args:
            initial_size: Quantidade inicial de balas no pool
        """
        self.pool: List[Bullet] = []
        self.active: List[Bullet] = []

        # Pré-cria balas inativas
        for _ in range(initial_size):
            bullet = Bullet(0, 0)
            bullet.active = False
            bullet.dead = True
            self.pool.append(bullet)

    def get(
        self,
        x: float,
        y: float,
        damage: int = 10,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
    ) -> Bullet:
        """
        Obtém uma bala do pool, reutilizando uma inativa ou criando nova.

        Args:
            x, y: Posição inicial da bala
            damage: Dano da bala
            piercing: Se a bala é perfurante
            homing: Se a bala é teleguiada
            explosive: Se a bala é explosiva
            low_ammo: Se restam poucas cargas (efeito de piscar)

        Returns:
            Bala ativa e configurada
        """
        # Procura uma bala inativa no pool
        for bullet in self.pool:
            if not bullet.active:
                bullet.reset(x=x, y=y, damage=damage, piercing=piercing, homing=homing, explosive=explosive, low_ammo=low_ammo)
                self.active.append(bullet)
                return bullet

        # Se não houver disponível, cria nova
        bullet = Bullet(x=x, y=y, damage=damage, piercing=piercing, homing=homing, explosive=explosive, low_ammo=low_ammo)
        self.pool.append(bullet)
        self.active.append(bullet)
        return bullet

    def release(self, bullet: Bullet):
        """
        Libera uma bala de volta ao pool, marcando como inativa.

        Args:
            bullet: Bala a ser desativada
        """
        if bullet in self.active:
            bullet.active = False
            bullet.dead = True
            self.active.remove(bullet)

    def update(self, dt: float):
        """
        Atualiza todas as balas ativas e libera as que morreram.

        Args:
            dt: Delta time em segundos
        """
        for bullet in self.active[:]:  # Copia a lista para iterar com segurança
            bullet.update(dt)
            if bullet.dead:
                self.release(bullet)

    def draw(self, screen: pygame.Surface):
        """
        Desenha todas as balas ativas.

        Args:
            screen: Superfície do pygame onde desenhar
        """
        for bullet in self.active:
            bullet.draw(screen)

    def clear_active(self):
        """Remove todas as balas ativas, devolvendo-as ao pool."""
        for bullet in self.active[:]:
            self.release(bullet)

    def get_active_count(self) -> int:
        """Retorna a quantidade de balas atualmente ativas."""
        return len(self.active)

    def get_pool_size(self) -> int:
        """Retorna o tamanho total do pool (ativas + inativas)."""
        return len(self.pool)
