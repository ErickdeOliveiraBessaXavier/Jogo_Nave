from typing import Any, List, Optional

import pygame

from ..core import colors
from ..core.config import config as Config


class Bullet:
    def __init__(
        self,
        x: float,
        y: float,
        damage: int = Config.BULLET_BASE_DAMAGE,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        ship_id: str = "padrao",
    ):
        self.x, self.y = x, y
        self.damage = damage
        self.dead = False
        self.piercing = piercing
        self.homing = homing
        self.explosive = explosive  # Tiro explosivo
        self.low_ammo = low_ammo  # Indica poucas cargas (para efeito de piscar)
        self.active = True  # Para o Pool Pattern
        self.target: Optional[Any] = None  # Alvo atual do tiro teleguiado
        self.assigned_target_id: Optional[int] = None  # ID do alvo atribuído
        self.homing_speed = 300  # Velocidade de rastreamento (pixels/s)
        self.homing_turn_rate = 4.0  # Taxa de rotação (radianos/s)
        self.rotation_angle = 0.0  # Ângulo de rotação visual (graus)
        self.is_side_scroll = is_side_scroll  # Se está em modo side-scroll
        self.laser_sound_channel: Optional[pygame.mixer.Channel] = None
        self.vx = 0.0
        self.vy = 0.0
        self.direction = direction
        self.ship_id = ship_id

        self._configure_shape_and_velocity(direction)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def reset(
        self,
        x: float,
        y: float,
        damage: int = Config.BULLET_BASE_DAMAGE,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        ship_id: str = "padrao",
    ):
        """Reconfigura a bala para reutilização no pool."""
        self.x, self.y = x, y
        self.damage = damage
        self.dead = False
        self.piercing = piercing
        self.homing = homing
        self.explosive = explosive
        self.low_ammo = low_ammo
        self.is_side_scroll = is_side_scroll
        self.active = True
        self.target = None
        self.assigned_target_id = None
        self.rotation_angle = 0.0
        self.laser_sound_channel = None
        self.vx = 0.0
        self.vy = 0.0
        self.direction = direction
        self.ship_id = ship_id
        self._configure_shape_and_velocity(direction)

    def update(self, dt: float, enemies: Optional[List[Any]] = None) -> None:
        if self.homing and enemies:
            self._update_homing(dt, enemies)
            # Rotacionar o tiro teleguiado
            self.rotation_angle += 360.0 * dt  # Uma rotação completa por segundo
            if self.rotation_angle >= 360.0:
                self.rotation_angle -= 360.0
        else:
            if self.vx != 0.0 or self.vy != 0.0:
                self.x += self.vx * dt
                self.y += self.vy * dt
            else:
                # Movimento baseado no modo de jogo
                if self.is_side_scroll:
                    # Side-scroll: movimento para direita
                    self.x += Config.BULLET_SPEED * dt
                else:
                    # Top-down: movimento para cima
                    self.y -= Config.BULLET_SPEED * dt

        if self.y + self.h < 0 or self.y > Config.SCREEN_HEIGHT:
            self.dead = True
        if self.x < -50 or self.x > Config.SCREEN_WIDTH + 50:
            self.dead = True

    def _update_homing(self, dt: float, enemies: List[Any]) -> None:
        """Atualiza a posição do tiro teleguiado."""
        # Se não tem alvo ou alvo está morto, procura novo alvo
        if not self.target or getattr(self.target, "dead", True):
            # Tentar encontrar o alvo original atribuído primeiro
            if self.assigned_target_id is not None:
                for enemy in enemies:
                    if id(enemy) == self.assigned_target_id and not getattr(
                        enemy, "dead", True
                    ):
                        self.target = enemy
                        break

            # Se não encontrou o alvo atribuído, procura o mais próximo
            if not self.target or getattr(self.target, "dead", True):
                self.target = self._find_closest_enemy(enemies)
                # Atualizar o ID do alvo atribuído
                if self.target:
                    self.assigned_target_id = id(self.target)

        if self.target:
            # Calcular direção para o alvo
            target_x = self.target.x + getattr(self.target, "w", 0) / 2
            target_y = self.target.y + getattr(self.target, "h", 0) / 2

            dx = target_x - self.x
            dy = target_y - self.y
            distance = (dx * dx + dy * dy) ** 0.5

            if distance > 0:
                # Normalizar direção e mover
                dx /= distance
                dy /= distance

                self.x += dx * self.homing_speed * dt
                self.y += dy * self.homing_speed * dt
        else:
            # Sem alvo, move para cima normalmente
            self.y -= Config.BULLET_SPEED * dt

    def _configure_shape_and_velocity(
        self, direction: tuple[float, float] | None
    ) -> None:
        """Configura dimensões e velocidade do projétil com base na direção e nave."""
        # Dimensões baseadas na nave
        base_w, base_h = 10, 3  # Padrão
        
        if self.ship_id == "estilete":
            base_w, base_h = 14, 2
        elif self.ship_id == "ariete":
            base_w, base_h = 8, 6
        elif self.ship_id == "magneto":
            base_w, base_h = 8, 8
        elif self.ship_id == "cacador":
            base_w, base_h = 12, 4
        elif self.ship_id == "engenheiro":
            base_w, base_h = 6, 6
            
        if direction is None:
            if self.is_side_scroll:
                self.vx = Config.BULLET_SPEED
                self.vy = 0.0
                self.w, self.h = base_w, base_h
            else:
                self.vx = 0.0
                self.vy = -Config.BULLET_SPEED
                self.w, self.h = base_h, base_w
            return

        dx, dy = direction
        # Ajustar orientação baseada na direção predominante
        if abs(dx) >= abs(dy):
            self.w, self.h = base_w, base_h
        else:
            self.w, self.h = base_h, base_w
            
        self.vx = dx * Config.BULLET_SPEED
        self.vy = dy * Config.BULLET_SPEED

    def _find_closest_enemy(self, enemies: List[Any]) -> Optional[Any]:
        """Encontra o inimigo mais próximo disponível."""
        closest = None
        min_distance = float("inf")

        for enemy in enemies:
            if getattr(enemy, "dead", True):
                continue

            enemy_x = enemy.x + getattr(enemy, "w", 0) / 2
            enemy_y = enemy.y + getattr(enemy, "h", 0) / 2

            dx = enemy_x - self.x
            dy = enemy_y - self.y
            distance = (dx * dx + dy * dy) ** 0.5

            if distance < min_distance:
                min_distance = distance
                closest = enemy

        return closest

    def assign_target(self, target: Any) -> None:
        """Atribui um alvo específico ao tiro teleguiado."""
        self.target = target
        self.assigned_target_id = id(target) if target else None

    def draw(self, surface: pygame.Surface):
        if self.homing:
            self._draw_homing_bullet(surface)
        elif self.explosive:
            self._draw_explosive_bullet(surface)
        else:
            self._draw_ship_specific_bullet(surface)

    def _draw_ship_specific_bullet(self, surface: pygame.Surface):
        """Desenha o projétil básico customizado conforme a nave."""
        rect = self.rect
        center = rect.center
        
        if self.ship_id == "magneto":
            # Magneto: Tiro ovalado roxo/azul
            pygame.draw.ellipse(surface, (100, 100, 255), rect)
            pygame.draw.ellipse(surface, (200, 200, 255), rect.inflate(-4, -4))
        elif self.ship_id == "estilete":
            # Estilete: Laser fino verde
            pygame.draw.rect(surface, (0, 255, 100), rect)
            # Brilho central
            pygame.draw.line(surface, (200, 255, 200), rect.topleft, rect.bottomleft, 1)
        elif self.ship_id == "ariete":
            # Aríete: Retângulo largo laranja intenso
            pygame.draw.rect(surface, (255, 80, 0), rect)
            pygame.draw.rect(surface, (255, 150, 50), rect.inflate(-2, -2))
        elif self.ship_id == "cofre":
            # Cofre: Amarelo claro arredondado
            pygame.draw.rect(surface, (255, 220, 100), rect, border_radius=3)
        elif self.ship_id == "fantasma":
            # Fantasma: Ciano pálido translúcido
            s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(s, (180, 255, 255, 160), s.get_rect(), border_radius=2)
            surface.blit(s, rect.topleft)
        elif self.ship_id == "engenheiro":
            # Engenheiro: Azul elétrico com núcleo branco
            pygame.draw.circle(surface, (0, 150, 255), center, rect.width // 2)
            pygame.draw.circle(surface, (255, 255, 255), center, rect.width // 4)
        elif self.ship_id == "cacador":
            # Caçador: Formato em seta/V prata
            points = []
            if self.vx > 0:  # Direita
                points = [rect.topleft, (rect.right, rect.centery), rect.bottomleft]
            elif self.vx < 0:  # Esquerda
                points = [rect.topright, (rect.left, rect.centery), rect.bottomright]
            elif self.vy < 0:  # Cima
                points = [rect.bottomleft, (rect.centerx, rect.top), rect.bottomright]
            else:  # Baixo
                points = [rect.topleft, (rect.centerx, rect.bottom), rect.topright]
            pygame.draw.polygon(surface, (192, 192, 220), points)
        elif self.ship_id == "reverberador":
            # Reverberador: Magenta com anéis
            pygame.draw.rect(surface, (255, 0, 255), rect)
            for i in range(1, 3):
                ring_rect = rect.inflate(i * 4, i * 4)
                pygame.draw.rect(surface, (255, 100, 255, 100), ring_rect, 1)
        else:
            # Padrão / Outros
            color = colors.PURPLE if self.piercing else colors.YELLOW
            pygame.draw.rect(surface, color, rect)

    def _draw_homing_bullet(self, surface: pygame.Surface):
        """Desenha o tiro teleguiado como um '+' pixelizado que gira."""
        import math

        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2

        # Tamanho do '+'
        size = 6
        thickness = 2

        # Cores: brilhante no centro, mais escuro nas bordas
        color_bright = colors.GREEN
        color_dim = (0, 200, 0)

        # Converter ângulo para radianos
        angle_rad = math.radians(self.rotation_angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Definir os 4 braços do '+' (horizontal e vertical)
        # Horizontal: esquerda e direita
        # Vertical: cima e baixo

        # Desenhar braço horizontal (rotacionado)
        for i in range(-size, size + 1):
            # Posição relativa ao centro
            local_x = i
            local_y = 0

            # Rotacionar
            rotated_x = local_x * cos_a - local_y * sin_a
            rotated_y = local_x * sin_a + local_y * cos_a

            # Posição absoluta
            pixel_x = center_x + rotated_x
            pixel_y = center_y + rotated_y

            # Cor mais brilhante no centro
            color = color_bright if abs(i) < 2 else color_dim
            pygame.draw.circle(
                surface, color, (int(pixel_x), int(pixel_y)), thickness // 2
            )

        # Desenhar braço vertical (rotacionado)
        for i in range(-size, size + 1):
            # Posição relativa ao centro
            local_x = 0
            local_y = i

            # Rotacionar
            rotated_x = local_x * cos_a - local_y * sin_a
            rotated_y = local_x * sin_a + local_y * cos_a

            # Posição absoluta
            pixel_x = center_x + rotated_x
            pixel_y = center_y + rotated_y

            # Cor mais brilhante no centro
            color = color_bright if abs(i) < 2 else color_dim
            pygame.draw.circle(
                surface, color, (int(pixel_x), int(pixel_y)), thickness // 2
            )

        # Desenhar centro brilhante
        pygame.draw.circle(
            surface, (150, 255, 150), (int(center_x), int(center_y)), thickness
        )

        # Aro vermelho/laranja quando combo homing+explosive — indica que o tiro
        # vai perseguir e explodir no impacto.
        if self.explosive:
            pygame.draw.circle(
                surface, (255, 80, 0), (int(center_x), int(center_y)), 9, 1
            )

    def _draw_explosive_bullet(self, surface: pygame.Surface):
        """Desenha o tiro explosivo com visual de granada/bomba."""
        import math

        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2

        # Corpo principal - círculo laranja/vermelho
        radius = 5

        # Efeito de pulso/brilho (mais rápido se low_ammo)
        pulse_speed = 0.02 if self.low_ammo else 0.01
        pulse = abs(math.sin(pygame.time.get_ticks() * pulse_speed)) * 0.3 + 0.7

        # Se low_ammo, alternar entre laranja e vermelho para efeito de piscar
        if self.low_ammo:
            blink = int(pygame.time.get_ticks() * 0.008) % 2 == 0
            if blink:
                # Vermelho piscante
                outer_color = (200, 20, 0)
                body_color = (255, 60, 0)
                core_color = (255, 150, 50)
            else:
                # Laranja normal
                outer_color = (180, 50, 0)
                body_color = (255, 120, 0)
                core_color = (255, int(200 * pulse) + 55, 0)
        else:
            outer_color = (180, 50, 0)
            body_color = (255, 120, 0)
            core_color = (255, int(200 * pulse) + 55, 0)

        # Cor externa (vermelho escuro)
        pygame.draw.circle(
            surface, outer_color, (int(center_x), int(center_y)), radius + 1
        )

        # Corpo (laranja)
        pygame.draw.circle(surface, body_color, (int(center_x), int(center_y)), radius)

        # Núcleo brilhante (amarelo pulsante)
        pygame.draw.circle(
            surface, core_color, (int(center_x), int(center_y)), radius - 2
        )

        # Partículas/faíscas ao redor (efeito visual) - mais se low_ammo
        num_sparks = 6 if self.low_ammo else 4
        spark_radius = radius + 3
        time_offset = pygame.time.get_ticks() * 0.003

        for i in range(num_sparks):
            angle = time_offset + (i * 2 * math.pi / num_sparks)
            spark_x = center_x + math.cos(angle) * spark_radius
            spark_y = center_y + math.sin(angle) * spark_radius
            spark_color = (255, 100, 100) if self.low_ammo else (255, 255, 100)
            pygame.draw.circle(surface, spark_color, (int(spark_x), int(spark_y)), 1)
