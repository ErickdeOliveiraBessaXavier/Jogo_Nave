import math
from typing import Any, Dict, List, Optional, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.player_tint import player_shot_color
from ..core.upgrades_config import (
    GIANT_SHOT_SPEED_MULTIPLIER,
    GIANT_SHOT_SQUARENESS,
)

# Velocidade de rastreamento do tiro teleguiado (px/s), antes do Giant Shot.
_HOMING_BASE_SPEED: float = 300.0


# NOTA SOBRE OS CACHES DESTE MÓDULO
# Todo cache de surface aqui é chaveado também por `player_index`, porque o P2
# desenha o mesmo tiro com a matiz desviada (ver `player_shot_color`). Sem a
# chave, o primeiro jogador a desenhar venceria e os dois atirariam igual. São
# só duas cópias por chave — o custo de memória é irrelevante e o de tempo é
# zero depois do primeiro frame.


# Cache estático de surfaces do Fantasma — evita alocar Surface SRCALPHA por
# frame por bala. Chave: (w, h, player_index) — a bala só tem 2 orientações.
_FANTASMA_SURFACE_CACHE: Dict[Tuple[int, int, int], pygame.Surface] = {}


def _get_fantasma_surface(w: int, h: int, player_index: int) -> pygame.Surface:
    key = (w, h, player_index)
    cached = _FANTASMA_SURFACE_CACHE.get(key)
    if cached is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            s,
            player_shot_color((180, 255, 255, 160), player_index),
            s.get_rect(),
            border_radius=2,
        )
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
# Chave: (player_index, explosive).
_HOMING_NUM_FRAMES: int = 24
_HOMING_FRAMES: Dict[Tuple[int, bool], List[pygame.Surface]] = {}


def _build_homing_base_surface(
    with_explosive_ring: bool, player_index: int
) -> pygame.Surface:
    """Constrói a sprite base do '+' (sem rotação). Tamanho 20x20 garante
    que cabe rotacionado em qualquer ângulo sem cortes."""
    size = 6
    surf_size = 20
    center = surf_size // 2
    surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)

    color_bright = player_shot_color(colors.GREEN, player_index)
    color_dim = player_shot_color((0, 200, 0), player_index)

    # Braços do '+'
    for i in range(-size, size + 1):
        color = color_bright if abs(i) < 2 else color_dim
        surf.set_at((center + i, center), color)
        surf.set_at((center, center + i), color)

    # Centro super brilhante (radius 2 cobre o miolo)
    pygame.draw.circle(
        surf, player_shot_color((150, 255, 150), player_index), (center, center), 2
    )

    # Aro do combo homing+explosive
    if with_explosive_ring:
        pygame.draw.circle(
            surf, player_shot_color((255, 80, 0), player_index), (center, center), 9, 1
        )

    return surf


def _get_homing_frames(player_index: int, explosive: bool) -> List[pygame.Surface]:
    """Frames rotacionados do teleguiado, memoizados por (jogador, explosivo).

    Renderizados sob demanda no primeiro draw — não no import — para garantir
    que o display já esteja inicializado quando o convert_alpha rodar.
    """
    key = (player_index, explosive)
    frames = _HOMING_FRAMES.get(key)
    if frames is not None:
        return frames

    base = _build_homing_base_surface(explosive, player_index)
    step = 360.0 / _HOMING_NUM_FRAMES
    frames = []
    for i in range(_HOMING_NUM_FRAMES):
        frame = pygame.transform.rotate(base, -i * step)
        try:
            frame = frame.convert_alpha()
        except pygame.error:
            pass
        frames.append(frame)
    _HOMING_FRAMES[key] = frames
    return frames


# Giro do tiro do Berserk ("Estrela Espiral") no próprio eixo, em graus/s. As
# rajadas já giram EM VOLTA da nave (o padrão espiral, em shooting_system); isto
# gira cada projétil em torno do próprio centro. Mais rápido que o teleguiado
# (360°/s) porque a bala do Berserk vive pouco: num giro por segundo, ela
# morreria antes de completar meia volta.
_BERSERK_SPIN_SPEED: float = 540.0

# Frames pré-rotacionados do tiro do Berserk, por tamanho. Rotacionar a cada
# frame de cada bala seria alocação e transform por projétil por frame — e o
# Berserk cospe 4 balas por disparo. Chave: (w, h, player_index) — o tamanho
# muda com o tamanho-base e com o Giant Shot, daí o dict em vez da lista fixa
# do teleguiado.
_BERSERK_NUM_FRAMES: int = 24
_BERSERK_FRAMES: Dict[Tuple[int, int, int], List[pygame.Surface]] = {}


def _get_berserk_frames(w: int, h: int, player_index: int) -> List[pygame.Surface]:
    """Frames do Berserk girado em 360°, memoizados por tamanho e jogador."""
    key = (w, h, player_index)
    frames = _BERSERK_FRAMES.get(key)
    if frames is not None:
        return frames

    base = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(
        base, player_shot_color((150, 0, 255), player_index), (0, 0, w, h)
    )
    inner = pygame.Rect(0, 0, w, h).inflate(-4, -4)
    if inner.width > 0 and inner.height > 0:
        pygame.draw.ellipse(
            base, player_shot_color((255, 100, 255), player_index), inner
        )

    step = 360.0 / _BERSERK_NUM_FRAMES
    frames = []
    for i in range(_BERSERK_NUM_FRAMES):
        frame = pygame.transform.rotate(base, -i * step)
        try:
            frame = frame.convert_alpha()
        except pygame.error:
            pass
        frames.append(frame)
    _BERSERK_FRAMES[key] = frames
    return frames


# Cache estático do corpo do tiro explosivo (outer + body sem o core pulsante).
# Chave: (low_ammo_blink_on, player_index). O core e os sparks ficam dinâmicos.
_EXPLOSIVE_BODY_CACHE: Dict[Tuple[bool, int], pygame.Surface] = {}


def _build_explosive_body_surface(
    low_ammo_blink_on: bool, player_index: int
) -> pygame.Surface:
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
    pygame.draw.circle(
        surf, player_shot_color(outer_color, player_index), (center, center), radius + 1
    )
    pygame.draw.circle(
        surf, player_shot_color(body_color, player_index), (center, center), radius
    )
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    return surf


def _get_explosive_body(low_ammo_blink_on: bool, player_index: int) -> pygame.Surface:
    key = (low_ammo_blink_on, player_index)
    cached = _EXPLOSIVE_BODY_CACHE.get(key)
    if cached is None:
        cached = _build_explosive_body_surface(low_ammo_blink_on, player_index)
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
        owner_ship: Optional[Any] = None,
        size_multiplier: float = 1.0,
        boss_damage_mult: float = 1.0,
    ):
        self.x, self.y = x, y
        self.damage = damage
        self.dead = False
        self.size_multiplier = size_multiplier  # Giant Shot escala w/h (visual+hitbox)
        # Nerf de dano aplicado SÓ contra bosses, lido em `collisions.
        # _project_into_boss`. 1.0 = sem mudança (todo tiro comum).
        self.boss_damage_mult = boss_damage_mult
        self.piercing = piercing
        self.homing = homing
        self.explosive = explosive  # Tiro explosivo
        self.low_ammo = low_ammo  # Indica poucas cargas (para efeito de piscar)
        self.active = True  # Para o Pool Pattern
        self.target: Optional[Any] = None  # Alvo atual do tiro teleguiado
        self.assigned_target_id: Optional[int] = None  # ID do alvo atribuído
        # Velocidade de rastreamento (px/s). Reatribuída em
        # `_configure_shape_and_velocity` (Giant Shot acelera) — o valor aqui é
        # só o default antes daquela chamada.
        self.homing_speed = _HOMING_BASE_SPEED
        self.homing_turn_rate = 4.0  # Taxa de rotação (radianos/s)
        self.rotation_angle = 0.0  # Ângulo de rotação visual (graus)
        self.is_side_scroll = is_side_scroll  # Se está em modo side-scroll
        self.laser_sound_channel: Optional[pygame.mixer.Channel] = None
        self.vx = 0.0
        self.vy = 0.0
        self.direction = direction
        self.ship_id = ship_id
        # Nave que disparou — usado para atribuir kills ao Reverberador certo
        # em coop (sem isso, o combo do P2 cresce com kills do P1 e vice-versa).
        self.owner_ship: Optional[Any] = owner_ship
        # Derivado do dono em vez de pedido no construtor: todo call site já
        # passa `owner_ship`, e uma cópia local evita um getattr encadeado por
        # cor por frame no draw. Sem dono, desenha como P1.
        self.player_index: int = getattr(owner_ship, "player_index", 0)

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
        owner_ship: Optional[Any] = None,
        size_multiplier: float = 1.0,
        boss_damage_mult: float = 1.0,
    ):
        """Reconfigura a bala para reutilização no pool."""
        self.x, self.y = x, y
        self.damage = damage
        self.dead = False
        self.size_multiplier = size_multiplier
        self.boss_damage_mult = boss_damage_mult
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
        self.owner_ship = owner_ship
        self.player_index = getattr(owner_ship, "player_index", 0)
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
            # Berserk: gira no próprio eixo enquanto viaja. Fica fora do `if
            # homing` acima porque as duas rotações são independentes — um tiro
            # do Berserk não é teleguiado.
            if self.ship_id == "berserk":
                self.rotation_angle = (
                    self.rotation_angle + _BERSERK_SPIN_SPEED * dt
                ) % 360.0
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

        # Tamanho-base de todas as naves (visual + hitbox). Aplicado ANTES do
        # Giant Shot, que passa a escalar a partir do base novo — o "3x" do
        # upgrade continua sendo 3x do tiro que a nave realmente atira.
        bonus = Config.BULLET_BASE_SIZE_BONUS
        if bonus:
            base_w = max(1, base_w + bonus)
            base_h = max(1, base_h + bonus)

        # Giant Shot: escala o tamanho base (visual e hitbox) e acelera o tiro.
        mult = self.size_multiplier
        speed = Config.BULLET_SPEED
        if mult != 1.0:
            base_w, base_h = self._giant_dims(base_w, base_h, mult)
            speed *= GIANT_SHOT_SPEED_MULTIPLIER
        self.homing_speed = _HOMING_BASE_SPEED * (speed / Config.BULLET_SPEED)

        if direction is None:
            if self.is_side_scroll:
                self.vx = speed
                self.vy = 0.0
                self.w, self.h = base_w, base_h
            else:
                self.vx = 0.0
                self.vy = -speed
                self.w, self.h = base_h, base_w
            return

        dx, dy = direction
        # Ajustar orientação baseada na direção predominante
        if abs(dx) >= abs(dy):
            self.w, self.h = base_w, base_h
        else:
            self.w, self.h = base_h, base_w

        self.vx = dx * speed
        self.vy = dy * speed

    @staticmethod
    def _giant_dims(base_w: int, base_h: int, mult: float) -> Tuple[int, int]:
        """Escala o tiro por `mult` puxando a proporção para o quadrado.

        Cada lado é interpolado (em escala log) entre ele mesmo e a média
        geométrica dos dois — o lado do quadrado de mesma área —, na dose de
        `GIANT_SHOT_SQUARENESS`. A área final é `mult²` vezes a original para
        QUALQUER dose, então a forma muda sem alterar o quanto o tiro cresceu:
        um tiro fino vira um bloco chunky em vez de uma barra comprida, e um
        tiro já quadrado não muda de forma.
        """
        k = GIANT_SHOT_SQUARENESS
        mean = math.sqrt(base_w * base_h)
        w = mult * (base_w ** (1.0 - k)) * (mean**k)
        h = mult * (base_h ** (1.0 - k)) * (mean**k)
        return max(1, round(w)), max(1, round(h))

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
        """Desenha o projétil básico customizado conforme a nave.

        Toda cor passa por `player_shot_color`: o P1 recebe a tupla de volta intacta
        e o P2 a mesma cor com a matiz girada, casando com o casco ciano dele.
        """
        rect = self.rect
        center = rect.center
        tint = self.player_index

        if self.ship_id == "magneto":
            # Magneto: Tiro ovalado roxo/azul
            pygame.draw.ellipse(surface, player_shot_color((100, 100, 255), tint), rect)
            pygame.draw.ellipse(
                surface, player_shot_color((200, 200, 255), tint), rect.inflate(-4, -4)
            )
        elif self.ship_id == "estilete":
            # Estilete: Laser fino verde
            pygame.draw.rect(surface, player_shot_color((0, 255, 100), tint), rect)
            # Brilho central
            pygame.draw.line(
                surface,
                player_shot_color((200, 255, 200), tint),
                rect.topleft,
                rect.bottomleft,
                1,
            )
        elif self.ship_id == "ariete":
            # Aríete: Retângulo largo laranja intenso
            pygame.draw.rect(surface, player_shot_color((255, 80, 0), tint), rect)
            pygame.draw.rect(
                surface, player_shot_color((255, 150, 50), tint), rect.inflate(-2, -2)
            )
        elif self.ship_id == "cofre":
            # Cofre: Amarelo claro arredondado
            pygame.draw.rect(
                surface, player_shot_color((255, 220, 100), tint), rect, border_radius=3
            )
        elif self.ship_id == "fantasma":
            # Fantasma: Ciano pálido translúcido — surface pré-renderizada (cache estático).
            surface.blit(
                _get_fantasma_surface(rect.width, rect.height, tint), rect.topleft
            )
        elif self.ship_id == "engenheiro":
            # Engenheiro: Azul elétrico com núcleo branco
            pygame.draw.circle(
                surface, player_shot_color((0, 150, 255), tint), center, rect.width // 2
            )
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
            pygame.draw.polygon(surface, player_shot_color((192, 192, 220), tint), points)
        elif self.ship_id == "reverberador":
            # Reverberador: Magenta com anéis
            pygame.draw.rect(surface, player_shot_color((255, 0, 255), tint), rect)
            ring_color = player_shot_color((255, 100, 255, 100), tint)
            for i in range(1, 3):
                ring_rect = rect.inflate(i * 4, i * 4)
                pygame.draw.rect(surface, ring_color, ring_rect, 1)
        elif self.ship_id == "berserk":
            # Berserk: Rosa dos Ventos — roxo brilhante, girando no próprio eixo
            # (frames pré-rotacionados; 1 blit em vez de um transform por frame).
            frames = _get_berserk_frames(rect.width, rect.height, tint)
            idx = int(
                self.rotation_angle * _BERSERK_NUM_FRAMES / 360.0
            ) % _BERSERK_NUM_FRAMES
            frame = frames[idx]
            # A rotação muda o tamanho da surface — centralizar na bounding box
            # do tiro, senão ele "orbita" o próprio hitbox ao girar.
            surface.blit(frame, frame.get_rect(center=center))
        else:
            # Padrão / Outros
            color = colors.PURPLE if self.piercing else colors.YELLOW
            pygame.draw.rect(surface, player_shot_color(color, tint), rect)

    def _draw_homing_bullet(self, surface: pygame.Surface):
        """Desenha o tiro teleguiado como um '+' pixelizado que gira.
        Usa frames pré-rotacionados — 1 blit em vez de 26 draw.circle."""
        frames = _get_homing_frames(self.player_index, self.explosive)
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
        tint = self.player_index

        pulse_speed = 0.02 if self.low_ammo else 0.01
        pulse = abs(math.sin(ticks * pulse_speed)) * 0.3 + 0.7

        if self.low_ammo:
            blink_on = (int(ticks * 0.008) % 2) == 0
            if blink_on:
                core_color = (255, 150, 50)
            else:
                core_color = (255, int(200 * pulse) + 55, 0)
            body_surf = _get_explosive_body(blink_on, tint)
        else:
            core_color = (255, int(200 * pulse) + 55, 0)
            body_surf = _get_explosive_body(False, tint)

        # 1 blit em vez de 2 draw.circle (outer + body).
        bw, bh = body_surf.get_size()
        surface.blit(body_surf, (cx_int - bw // 2, cy_int - bh // 2))

        # Núcleo pulsante (dinâmico — fica fora do cache).
        pygame.draw.circle(
            surface, player_shot_color(core_color, tint), (cx_int, cy_int), radius - 2
        )

        # Sparks: posição dinâmica, mantém draw.circle.
        num_sparks = 6 if self.low_ammo else 4
        spark_radius = radius + 3
        time_offset = ticks * 0.003
        spark_color = player_shot_color(
            (255, 100, 100) if self.low_ammo else (255, 255, 100), tint
        )
        angle_step = 2 * math.pi / num_sparks
        cos = math.cos
        sin = math.sin
        for i in range(num_sparks):
            angle = time_offset + i * angle_step
            spark_x = center_x + cos(angle) * spark_radius
            spark_y = center_y + sin(angle) * spark_radius
            pygame.draw.circle(surface, spark_color, (int(spark_x), int(spark_y)), 1)
