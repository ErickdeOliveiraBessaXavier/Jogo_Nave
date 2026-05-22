import math
from typing import Any, Dict, List, Optional, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config

# Cache estático de surfaces do Fantasma — evita alocar Surface SRCALPHA por
# frame por bala. Chave: (w, h) — a bala só tem 2 orientações possíveis.
_FANTASMA_SURFACE_CACHE: Dict[Tuple[int, int], pygame.Surface] = {}


def _get_fantasma_surface(w: int, h: int) -> pygame.Surface:
    key = (w, h)
    cached = _FANTASMA_SURFACE_CACHE.get(key)
    if cached is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, (180, 255, 255, 160), s.get_rect(), border_radius=2)
        try:
            s = s.convert_alpha()
        except pygame.error:
            pass
        _FANTASMA_SURFACE_CACHE[key] = s
        return s
    return cached


# Cache estático de frames pré-rotacionados do tiro teleguiado.
# 24 frames = 15° por frame; suficiente para 360°/s a 60fps.
# Cada frame é uma surface pequena (~20x20). Total ~10 KB de memória.
_HOMING_NUM_FRAMES: int = 24
_HOMING_FRAMES: List[pygame.Surface] = []
_HOMING_FRAMES_EXPLOSIVE: List[pygame.Surface] = []


def _build_homing_base_surface(with_explosive_ring: bool) -> pygame.Surface:
    """Constrói a sprite base do '+' (sem rotação). Tamanho 20x20 garante
    que cabe rotacionado em qualquer ângulo sem cortes."""
    size = 6
    surf_size = 20
    center = surf_size // 2
    surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)

    color_bright = colors.GREEN
    color_dim = (0, 200, 0)

    # Braços do '+'
    for i in range(-size, size + 1):
        color = color_bright if abs(i) < 2 else color_dim
        surf.set_at((center + i, center), color)
        surf.set_at((center, center + i), color)

    # Centro super brilhante (radius 2 cobre o miolo)
    pygame.draw.circle(surf, (150, 255, 150), (center, center), 2)

    # Aro do combo homing+explosive
    if with_explosive_ring:
        pygame.draw.circle(surf, (255, 80, 0), (center, center), 9, 1)

    return surf


def _ensure_homing_frames() -> None:
    """Renderiza N frames rotacionados sob demanda (idempotente). Chamado
    no primeiro draw para garantir que o display esteja inicializado."""
    if _HOMING_FRAMES:
        return
    base_plain = _build_homing_base_surface(with_explosive_ring=False)
    base_expl = _build_homing_base_surface(with_explosive_ring=True)
    step = 360.0 / _HOMING_NUM_FRAMES
    for i in range(_HOMING_NUM_FRAMES):
        angle = i * step
        for src, dst in (
            (base_plain, _HOMING_FRAMES),
            (base_expl, _HOMING_FRAMES_EXPLOSIVE),
        ):
            frame = pygame.transform.rotate(src, -angle)
            try:
                frame = frame.convert_alpha()
            except pygame.error:
                pass
            dst.append(frame)


# Cache estático do corpo do tiro explosivo (outer + body sem o core pulsante).
# Chaves: 'normal' e 'low_blink_on'. O core e os sparks ficam dinâmicos.
_EXPLOSIVE_BODY_CACHE: Dict[str, pygame.Surface] = {}


def _build_explosive_body_surface(low_ammo_blink_on: bool) -> pygame.Surface:
    radius = 5
    surf_size = (radius + 1) * 2 + 2
    center = surf_size // 2
    surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
    if low_ammo_blink_on:
        outer_color = (200, 20, 0)
        body_color = (255, 60, 0)
    else:
        outer_color = (180, 50, 0)
        body_color = (255, 120, 0)
    pygame.draw.circle(surf, outer_color, (center, center), radius + 1)
    pygame.draw.circle(surf, body_color, (center, center), radius)
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    return surf


def _get_explosive_body(low_ammo_blink_on: bool) -> pygame.Surface:
    key = "low_blink_on" if low_ammo_blink_on else "normal"
    cached = _EXPLOSIVE_BODY_CACHE.get(key)
    if cached is None:
        cached = _build_explosive_body_surface(low_ammo_blink_on)
        _EXPLOSIVE_BODY_CACHE[key] = cached
    return cached


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

        # Rect persistente — atualizado in-place em vez de alocar por acesso.
        self._rect = pygame.Rect(int(x), int(y), 1, 1)

        self._configure_shape_and_velocity(direction)
        self._sync_rect()

    @property
    def rect(self) -> pygame.Rect:
        self._sync_rect()
        return self._rect

    def _sync_rect(self) -> None:
        self._rect.update(int(self.x), int(self.y), self.w, self.h)

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
        self._sync_rect()

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
            # Fantasma: Ciano pálido translúcido — surface pré-renderizada (cache estático).
            surface.blit(_get_fantasma_surface(rect.width, rect.height), rect.topleft)
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
        """Desenha o tiro teleguiado como um '+' pixelizado que gira.
        Usa frames pré-rotacionados — 1 blit em vez de 26 draw.circle."""
        _ensure_homing_frames()
        frames = _HOMING_FRAMES_EXPLOSIVE if self.explosive else _HOMING_FRAMES
        idx = int(self.rotation_angle * _HOMING_NUM_FRAMES / 360.0) % _HOMING_NUM_FRAMES
        frame = frames[idx]
        fw, fh = frame.get_size()
        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2
        surface.blit(frame, (int(center_x - fw / 2), int(center_y - fh / 2)))

    def _draw_explosive_bullet(self, surface: pygame.Surface):
        """Desenha o tiro explosivo com visual de granada/bomba.
        Outer+body vêm de cache estático; só core e sparks ficam dinâmicos."""
        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2
        cx_int = int(center_x)
        cy_int = int(center_y)
        radius = 5

        ticks = pygame.time.get_ticks()  # 1 chamada em vez de 3

        pulse_speed = 0.02 if self.low_ammo else 0.01
        pulse = abs(math.sin(ticks * pulse_speed)) * 0.3 + 0.7

        if self.low_ammo:
            blink_on = (int(ticks * 0.008) % 2) == 0
            if blink_on:
                core_color = (255, 150, 50)
            else:
                core_color = (255, int(200 * pulse) + 55, 0)
            body_surf = _get_explosive_body(blink_on)
        else:
            core_color = (255, int(200 * pulse) + 55, 0)
            body_surf = _get_explosive_body(False)

        # 1 blit em vez de 2 draw.circle (outer + body).
        bw, bh = body_surf.get_size()
        surface.blit(body_surf, (cx_int - bw // 2, cy_int - bh // 2))

        # Núcleo pulsante (dinâmico — fica fora do cache).
        pygame.draw.circle(surface, core_color, (cx_int, cy_int), radius - 2)

        # Sparks: posição dinâmica, mantém draw.circle.
        num_sparks = 6 if self.low_ammo else 4
        spark_radius = radius + 3
        time_offset = ticks * 0.003
        spark_color = (255, 100, 100) if self.low_ammo else (255, 255, 100)
        angle_step = 2 * math.pi / num_sparks
        cos = math.cos
        sin = math.sin
        for i in range(num_sparks):
            angle = time_offset + i * angle_step
            spark_x = center_x + cos(angle) * spark_radius
            spark_y = center_y + sin(angle) * spark_radius
            pygame.draw.circle(surface, spark_color, (int(spark_x), int(spark_y)), 1)
