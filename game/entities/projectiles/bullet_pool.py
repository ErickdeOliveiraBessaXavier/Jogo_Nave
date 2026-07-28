from typing import Any, List, Optional

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
        # Free-list LIFO: lookup O(1) por spawn em vez de scan O(n) no pool.
        self.free: List[Bullet] = []

        # Pré-cria balas inativas
        for _ in range(initial_size):
            bullet = Bullet(0, 0)
            bullet.active = False
            bullet.dead = True
            self.pool.append(bullet)
            self.free.append(bullet)

    def get(
        self,
        x: float,
        y: float,
        damage: int = 10,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        ship_id: str = "padrao",
        owner_ship: Optional[Any] = None,
        size_multiplier: float = 1.0,
        boss_damage_mult: float = 1.0,
        critical: bool = False,
        cryo: bool = False,
    ) -> Bullet:
        """
        Obtém uma bala do pool, reutilizando uma inativa ou criando nova.
        """
        if self.free:
            bullet = self.free.pop()
            bullet.reset(
                x=x,
                y=y,
                damage=damage,
                piercing=piercing,
                homing=homing,
                explosive=explosive,
                low_ammo=low_ammo,
                is_side_scroll=is_side_scroll,
                direction=direction,
                ship_id=ship_id,
                owner_ship=owner_ship,
                size_multiplier=size_multiplier,
                boss_damage_mult=boss_damage_mult,
                critical=critical,
                cryo=cryo,
            )
            self.active.append(bullet)
            return bullet

        # Sem balas livres: cria uma nova e registra no pool.
        bullet = Bullet(
            x=x,
            y=y,
            damage=damage,
            piercing=piercing,
            homing=homing,
            explosive=explosive,
            low_ammo=low_ammo,
            is_side_scroll=is_side_scroll,
            direction=direction,
            ship_id=ship_id,
            owner_ship=owner_ship,
            size_multiplier=size_multiplier,
            boss_damage_mult=boss_damage_mult,
            critical=critical,
            cryo=cryo,
        )
        self.pool.append(bullet)
        self.active.append(bullet)
        return bullet

    def release(self, bullet: Bullet):
        """
        Libera uma bala de volta ao pool, marcando como inativa.
        Chamado por código externo; o sweep do update() não passa por aqui.
        """
        if bullet.laser_sound_channel is not None:
            bullet.laser_sound_channel.stop()
            bullet.laser_sound_channel = None
        try:
            self.active.remove(bullet)
        except ValueError:
            return
        bullet.active = False
        bullet.dead = True
        self.free.append(bullet)

    def update(self, dt: float):
        """
        Atualiza todas as balas ativas e libera as que morreram.
        Sweep in-place: sem cópia de lista, sem release() por bala morta.
        """
        write = 0
        active = self.active
        free = self.free
        for bullet in active:
            bullet.update(dt)
            if bullet.dead:
                if bullet.laser_sound_channel is not None:
                    bullet.laser_sound_channel.stop()
                    bullet.laser_sound_channel = None
                bullet.active = False
                free.append(bullet)
            else:
                active[write] = bullet
                write += 1
        del active[write:]

    def draw(self, screen: pygame.Surface):
        for bullet in self.active:
            bullet.draw(screen)

    def clear_active(self):
        """Remove todas as balas ativas, devolvendo-as ao pool."""
        for bullet in self.active:
            if bullet.laser_sound_channel is not None:
                bullet.laser_sound_channel.stop()
                bullet.laser_sound_channel = None
            bullet.active = False
            bullet.dead = True
            self.free.append(bullet)
        self.active.clear()

    def get_active_count(self) -> int:
        return len(self.active)

    def get_pool_size(self) -> int:
        return len(self.pool)
