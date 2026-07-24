import math
from typing import Any, Dict, List, Optional, Tuple

import pygame

from ...core import colors
from ...core.config import config as Config
from ...core.player_tint import player_shot_color
from ...core.visual_quality import visual_quality as vq
from ...core.upgrades_config import (
    GIANT_SHOT_SPEED_MULTIPLIER,
    GIANT_SHOT_SQUARENESS,
    giant_visual_scale,
)
from ...systems.targeting import target_point

# Velocidade de rastreamento do tiro teleguiado (px/s), antes do Giant Shot.
_HOMING_BASE_SPEED: float = 300.0

# Giro do '+' no próprio eixo (graus/s). Em VIAGEM (perseguindo um alvo) gira no
# ritmo de sempre — 1 volta/s. Em ESPERA (sem inimigo em tela, pairando no
# lugar) gira mais rápido: parado, o giro lento de um '+' quase simétrico lê como
# estático; acelerar deixa claro que a bala está viva, à espreita do próximo.
_HOMING_SPIN_SPEED: float = 360.0
_HOMING_IDLE_SPIN_SPEED: float = 900.0


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
# Chave: (player_index, explosive, scale_key) — `scale_key` distingue o tiro
# normal do Giant Shot (combinação teleguiado + tiro aumentado), quantizado
# em 1 casa para não estourar o cache com floats quase iguais.
_HOMING_NUM_FRAMES: int = 24
_HOMING_FRAMES: Dict[Tuple[int, bool, float], List[pygame.Surface]] = {}


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


def _get_homing_frames(
    player_index: int, explosive: bool, scale: float = 1.0
) -> List[pygame.Surface]:
    """Frames rotacionados do teleguiado, memoizados por (jogador, explosivo, escala).

    Renderizados sob demanda no primeiro draw — não no import — para garantir
    que o display já esteja inicializado quando o convert_alpha rodar.

    `scale` (> 1.0 quando o Giant Shot está ativo) engorda a sprite para casar
    com o hitbox aumentado, tornando visível a combinação teleguiado + tiro
    grande. A escala é aplicada na surface base ANTES da rotação, para as bordas
    rotacionadas saírem mais suaves.
    """
    scale_key = round(scale, 1)
    key = (player_index, explosive, scale_key)
    frames = _HOMING_FRAMES.get(key)
    if frames is not None:
        return frames

    base = _build_homing_base_surface(explosive, player_index)
    if scale_key != 1.0:
        bw, bh = base.get_size()
        base = pygame.transform.scale(
            base, (max(1, round(bw * scale_key)), max(1, round(bh * scale_key)))
        )
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
# Chave: (low_ammo_blink_on, player_index, radius). O `radius` cresce com o
# Giant Shot (combinação explosivo + tiro aumentado); o core e os sparks ficam
# dinâmicos.
_EXPLOSIVE_BODY_CACHE: Dict[Tuple[bool, int, int], pygame.Surface] = {}


def _build_explosive_body_surface(
    low_ammo_blink_on: bool, player_index: int, radius: int = 5
) -> pygame.Surface:
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


def _get_explosive_body(
    low_ammo_blink_on: bool, player_index: int, radius: int = 5
) -> pygame.Surface:
    key = (low_ammo_blink_on, player_index, radius)
    cached = _EXPLOSIVE_BODY_CACHE.get(key)
    if cached is None:
        cached = _build_explosive_body_surface(low_ammo_blink_on, player_index, radius)
        _EXPLOSIVE_BODY_CACHE[key] = cached
    return cached


# Halo pulsante ('respiração') dos tiros de power-up. Sprite radial cacheada por
# (raio, cor, passo) — o `passo` quantiza a fase do pulso em `_GLOW_STEPS`
# níveis, então o brilho "respira" trocando de sprite cacheada em vez de alocar
# por frame. Um blit por bala. Chave inclui a cor (já com a matiz do jogador).
_GLOW_STEPS: int = 5
# Teto de cada eixo do halo (px), para o Giant Shot crescer sem estourar a tela
# nem inchar o cache. Piso por eixo evita glow fino demais no laser estreito.
_GLOW_MAX_PX: int = 140
_GLOW_MIN_COMMON: int = 12
_GLOW_MIN_POWER: int = 8
_GLOW_CACHE: Dict[Tuple[int, int, Tuple[int, int, int], int], pygame.Surface] = {}

# Halo do tiro COMUM: aditivo, com o RGB pré-multiplicado pela intensidade.
# Alpha-blend (o caminho dos power-ups) precisa de alpha alto para aparecer, e
# nessa dose o halo vira uma mancha chapada em volta de um tiro pequeno; somando
# ao fundo, o brilho aparece sobre o preto do espaço sem borrar o projétil.
# `_COMMON_GLOW_PEAK` = fração do brilho da cor somada no centro, no pico do pulso.
# Doses baixas de propósito: com dezenas de tiros na tela os halos SOMAM entre si,
# e o que era brilho individual vira uma mancha só, lavando inimigos e projéteis.
_COMMON_GLOW_MIN: float = 0.22
_COMMON_GLOW_PEAK: float = 0.45
# Expoente da queda radial. Acima de 2 o brilho se concentra num núcleo apertado
# em vez de se espalhar — é o que mantém o tiro "aceso" sem borrar a vizinhança.
_COMMON_GLOW_FALLOFF: float = 3.0
_COMMON_GLOW_CACHE: Dict[Tuple[int, int, Tuple[int, int, int], int], pygame.Surface] = {}


def _get_common_shot_glow(
    w: int, h: int, color: Tuple[int, int, int], step: int
) -> pygame.Surface:
    """Halo ELÍPTICO aditivo do tiro comum, memoizado por (w, h, cor, passo).

    A elipse acompanha as proporções do projétil — `w`/`h` já vêm trocados
    conforme a orientação (side-scroll = largo, top-down = alto) e escalados pelo
    tamanho-base da nave e pelo Giant Shot —, então o glow é sempre uma extensão
    natural do tiro, não um círculo genérico. Degradê quadrático do centro à borda,
    com a cor pré-multiplicada pela intensidade para blit com ``BLEND_RGB_ADD``.
    """
    key = (w, h, color, step)
    cached = _COMMON_GLOW_CACHE.get(key)
    if cached is not None:
        return cached

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    peak = _COMMON_GLOW_MIN + (step / _GLOW_STEPS) * (
        _COMMON_GLOW_PEAK - _COMMON_GLOW_MIN
    )
    r_col, g_col, b_col = color
    cx, cy = w / 2.0, h / 2.0
    # Uma "casca" elíptica por ~pixel do maior semieixo — do exterior (apagado) ao
    # centro (aceso), cada elipse menor sobrescrevendo, formando o degradê radial.
    shells = max(2, max(w, h) // 2)
    for i in range(shells, 0, -1):
        t = i / shells
        f = peak * (1.0 - t) ** _COMMON_GLOW_FALLOFF
        ew = max(1, int(w * t))
        eh = max(1, int(h * t))
        pygame.draw.ellipse(
            surf,
            (int(r_col * f), int(g_col * f), int(b_col * f), 255),
            pygame.Rect(int(cx - ew / 2), int(cy - eh / 2), ew, eh),
        )
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _COMMON_GLOW_CACHE[key] = surf
    return surf


def _get_power_glow(
    w: int, h: int, color: Tuple[int, int, int], step: int
) -> pygame.Surface:
    """Halo ELÍPTICO suave da cor pedida, com brilho central no nível `step`.

    Acompanha as proporções do projétil (`w`/`h`, já orientados e escalados).
    Construído da casca externa (alpha ~0) ao centro (alpha `peak`), com queda
    quadrática — degradê macio. Memoizado por (w, h, cor, passo).
    """
    key = (w, h, color, step)
    cached = _GLOW_CACHE.get(key)
    if cached is not None:
        return cached

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    peak = 30 + int((step / _GLOW_STEPS) * 130)  # alpha central pulsa ~30..160
    r_col, g_col, b_col = color
    cx, cy = w / 2.0, h / 2.0
    shells = max(2, max(w, h) // 2)
    for i in range(shells, 0, -1):
        t = i / shells
        a = int(peak * (1.0 - t) * (1.0 - t))
        if a > 0:
            ew = max(1, int(w * t))
            eh = max(1, int(h * t))
            pygame.draw.ellipse(
                surf,
                (r_col, g_col, b_col, a),
                pygame.Rect(int(cx - ew / 2), int(cy - eh / 2), ew, eh),
            )
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _GLOW_CACHE[key] = surf
    return surf


# Rampa de cor do tiro do Reverberador: violeta apagado (sem combo) -> magenta
# pleno (metade do cap) -> rosa quase branco (cap). O tiro esquenta junto com o
# bônus de dano, então dá para ler a força do combo sem olhar o HUD.
_REVERB_COLD = (140, 30, 180)
_REVERB_MID = (255, 0, 255)
_REVERB_HOT = (255, 190, 255)
_REVERB_RING_COLD = (180, 70, 210)
_REVERB_RING_HOT = (255, 225, 255)


def _lerp_color(
    a: Tuple[int, int, int], b: Tuple[int, int, int], t: float
) -> Tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _reverberador_colors(k: float) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Cores (corpo, anel) do tiro do Reverberador para o combo `k` (0..1)."""
    if k < 0.5:
        body = _lerp_color(_REVERB_COLD, _REVERB_MID, k / 0.5)
    else:
        body = _lerp_color(_REVERB_MID, _REVERB_HOT, (k - 0.5) / 0.5)
    return body, _lerp_color(_REVERB_RING_COLD, _REVERB_RING_HOT, k)


# Cor-base do halo do tiro COMUM de cada nave. Espelha o corpo desenhado em
# `_draw_ship_specific_bullet` — mudou a cor do tiro lá, mude aqui também, senão
# o halo deixa de refletir o próprio tiro. Naves ausentes caem no default
# (roxo perfurante / amarelo).
_SHIP_GLOW_COLORS: Dict[str, Tuple[int, int, int]] = {
    "magneto": (150, 150, 255),  # média do corpo azul + núcleo claro
    "estilete": (0, 255, 100),
    "ariete": (255, 110, 20),
    "cofre": (255, 220, 100),
    "fantasma": (180, 255, 255),
    "engenheiro": (0, 150, 255),
    "cacador": (192, 192, 220),
    "berserk": (200, 60, 255),  # entre o roxo externo e o rosa interno
}


def _owner_combo_intensity(owner_ship: Optional[Any]) -> float:
    """Progresso do combo (0..1) do dono no instante do disparo.

    Fica congelado na bala em vez de lido por frame: o tiro carrega a força com
    que saiu, e um dano tomado no meio do voo não apaga os projéteis no ar.
    """
    try:
        return max(0.0, min(1.0, float(getattr(owner_ship, "combo_progress", 0.0))))
    except (TypeError, ValueError):
        return 0.0


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
        self.homing_turn_rate = 4.0  # Curva de perseguição (radianos/s)
        # Direção de voo do teleguiado (radianos). É virada gradualmente em
        # direção ao alvo (limite = homing_turn_rate) para o rastreio ser
        # orgânico e não mudar de rumo de forma abrupta. None = ainda não voou.
        self.homing_heading: Optional[float] = None
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
        # Combo do Reverberador congelado no disparo (0..1) — pinta o projétil.
        self.combo_intensity: float = _owner_combo_intensity(owner_ship)
        # Cargas de perfuração restantes (Aríete). Consumidas em `collisions`.
        self.pierce_remaining: int = 0

        # Rect persistente — atualizado in-place em vez de alocar por acesso.
        self._rect = pygame.Rect(int(x), int(y), 1, 1)

        self._configure_shape_and_velocity(direction)
        self.pierce_remaining = self._owner_pierce_count()
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
        self.homing_heading = None
        self.rotation_angle = 0.0
        self.laser_sound_channel = None
        self.vx = 0.0
        self.vy = 0.0
        self.direction = direction
        self.ship_id = ship_id
        self.owner_ship = owner_ship
        self.player_index = getattr(owner_ship, "player_index", 0)
        self.combo_intensity = _owner_combo_intensity(owner_ship)
        self._configure_shape_and_velocity(direction)
        self.pierce_remaining = self._owner_pierce_count()
        self._sync_rect()

    def update(self, dt: float, enemies: Optional[List[Any]] = None) -> None:
        if self.homing:
            # `enemies` pode vir vazio (nenhum hostil): ainda assim entramos aqui
            # para pairar no lugar, em vez de cair no `else` e subir para fora da
            # tela. O alvo é atribuído pelo coordenador (EntityManager).
            self._update_homing(dt)
            # Gira no próprio eixo sempre — mais rápido enquanto espera (sem
            # alvo), para pairar girando em vez de parecer congelado.
            spin = (
                _HOMING_IDLE_SPIN_SPEED if self.target is None else _HOMING_SPIN_SPEED
            )
            self.rotation_angle = (self.rotation_angle + spin * dt) % 360.0
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

    def _update_homing(self, dt: float) -> None:
        """Persegue o alvo atribuído pelo coordenador (``EntityManager``).

        A seleção de alvo vive fora da bala: é balanceada entre todos os
        teleguiados e restrita a inimigos em tela (ver
        ``EntityManager._assign_homing_targets``). Aqui a bala só age sobre o
        ``self.target`` já resolvido.

        Sem alvo — nenhum inimigo visível — a bala **paira no lugar**, esperando
        o próximo entrar; não sobe para fora da tela.

        A perseguição é **orgânica**: em vez de apontar direto ao alvo a cada
        frame (virada instantânea), a bala vira a própria direção de voo
        (``homing_heading``) em direção ao alvo, limitada por
        ``homing_turn_rate``. Ao trocar de alvo ou o alvo desviar, ela curva
        suavemente em vez de mudar de rumo de repente.
        """
        target = self.target
        if target is not None and getattr(target, "dead", True):
            target = self.target = None

        if target is None:
            # Idle: zera a velocidade para que, parada, não seja morta pela
            # checagem de fora-da-tela no fim de `update`. O heading é preservado
            # para curvar a partir dele quando um novo alvo aparecer.
            self.vx = 0.0
            self.vy = 0.0
            return

        # Ponto de mira preciso (segue a geometria real de bosses via
        # collision_circle; cai para o centro do rect nos inimigos comuns).
        aim = target_point(target)
        if aim is None:
            return
        dx = aim[0] - self.x
        dy = aim[1] - self.y
        distance = (dx * dx + dy * dy) ** 0.5
        if distance <= 0:
            return

        desired = math.atan2(dy, dx)

        # 1º frame de voo: alinha o heading à direção com que a bala nasceu (ou
        # já ao alvo, se nasceu parada) — evita uma curva inicial fantasma.
        if self.homing_heading is None:
            if self.vx != 0.0 or self.vy != 0.0:
                self.homing_heading = math.atan2(self.vy, self.vx)
            else:
                self.homing_heading = desired

        # Vira o heading em direção ao alvo, no máximo homing_turn_rate*dt.
        # O delta é normalizado para (-π, π] para virar sempre pelo lado curto.
        diff = (desired - self.homing_heading + math.pi) % (2 * math.pi) - math.pi
        max_turn = self.homing_turn_rate * dt
        if diff > max_turn:
            diff = max_turn
        elif diff < -max_turn:
            diff = -max_turn
        self.homing_heading += diff

        hx = math.cos(self.homing_heading)
        hy = math.sin(self.homing_heading)
        self.vx = hx * self.homing_speed
        self.vy = hy * self.homing_speed
        self.x += hx * self.homing_speed * dt
        self.y += hy * self.homing_speed * dt

    def _owner_bullet_speed_mult(self) -> float:
        """`bullet_speed_mult` do perfil do dono (1.0 sem dono/perfil)."""
        profile = getattr(self.owner_ship, "profile", None)
        try:
            return max(0.1, float(getattr(profile, "bullet_speed_mult", 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def _owner_pierce_count(self) -> int:
        """Alvos extras que o tiro comum atravessa, vindos do perfil do dono.

        Só vale para o tiro básico: teleguiado e explosivo têm as próprias
        regras de impacto e não devem herdar a perfuração da nave.
        """
        if self.homing or self.explosive:
            return 0
        profile = getattr(self.owner_ship, "profile", None)
        try:
            return max(0, int(getattr(profile, "pierce_count", 0)))
        except (TypeError, ValueError):
            return 0

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

        # Velocidade por nave (`bullet_speed_mult`): contrapartida da cadência —
        # o tiro pesado chega antes, o tiro-metralhadora chega depois. Lida do
        # perfil do dono em vez de uma tabela local, para não duplicar o valor.
        mult = self.size_multiplier
        speed = Config.BULLET_SPEED * self._owner_bullet_speed_mult()
        giant_ratio = 1.0
        if mult != 1.0:
            base_w, base_h = self._giant_dims(base_w, base_h, mult)
            speed *= GIANT_SHOT_SPEED_MULTIPLIER
            giant_ratio = GIANT_SHOT_SPEED_MULTIPLIER
        # O teleguiado segue só a escala do Giant Shot: ele tem tuning próprio
        # (`_HOMING_BASE_SPEED` + turn rate), e herdar a velocidade da nave
        # mexeria no raio de curva de um powerup já balanceado à parte.
        self.homing_speed = _HOMING_BASE_SPEED * giant_ratio

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

    def assign_target(self, target: Any) -> None:
        """Atribui um alvo específico ao tiro teleguiado."""
        self.target = target
        self.assigned_target_id = id(target) if target else None

    def draw(self, surface: pygame.Surface):
        # Halo pulsante ANTES do corpo (fica atrás do tiro).
        self._draw_power_pulse(surface)
        if self.homing:
            self._draw_homing_bullet(surface)
        elif self.explosive:
            self._draw_explosive_bullet(surface)
        else:
            self._draw_ship_specific_bullet(surface)

    def _draw_power_pulse(self, surface: pygame.Surface) -> None:
        """Halo pulsante ('respiração') dos tiros de power-up.

        Dá vida às habilidades — sobretudo ao Giant Shot, que sem isto é só um
        tiro grande e estático. Cor por fantasia (explosivo laranja > chain
        azul-elétrico > teleguiado verde > gigante âmbar) e raio proporcional ao
        tiro (o gigante respira maior). Um blit de sprite cacheada por bala;
        gateado pela Qualidade Visual — some no Baixo, encolhe no Médio.

        O tiro COMUM também ganha halo, na cor do próprio projétil da nave
        (`_common_shot_glow_color`), mas por soma ao fundo (`BLEND_RGB_ADD`) em
        vez de alpha-blend: o tiro é pequeno e um halo translúcido nesse tamanho
        desaparece contra o fundo escuro.
        """
        if not vq.glow_enabled:
            return
        is_giant = self.size_multiplier > 1.0
        # Chain Lightning vive na nave (has_chain_shot), não na bala: lê o dono,
        # como o próprio sistema de colisão faz para encadear.
        is_chain = bool(getattr(self.owner_ship, "has_chain_shot", False))

        # Cor + ritmo por fantasia. Prioridade quando combinados: o efeito mais
        # dramático manda na cor do halo.
        is_common = not (self.explosive or is_chain or self.homing or is_giant)
        radius_factor = 1.4
        if self.explosive:
            base_color = (255, 120, 0)  # laranja de pavio
            speed = 0.009
        elif is_chain:
            base_color = (70, 170, 255)  # azul-elétrico do raio
            speed = 0.014  # tremular rápido, nervoso
        elif self.homing:
            base_color = (0, 255, 100)  # verde do '+'
            # Em espera (sem alvo) pulsa mais rápido — casa com o giro idle.
            speed = 0.011 if self.target is None else 0.006
        elif is_giant:
            # Giant Shot só ESCALA o tiro da nave — o corpo continua na cor dela,
            # então o halo acompanha (antes era âmbar fixo, destoando: um tiro
            # verde do Estilete ficava com glow amarelo). A identidade do gigante
            # vem do tamanho + respiração, não de uma cor genérica.
            base_color = self._common_shot_glow_color()
            speed = 0.005
        else:
            base_color = self._common_shot_glow_color()
            speed = 0.007
            # Colado ao tiro: o suficiente para o halo aparecer em volta do
            # corpo, sem virar uma bola que se funde com a do tiro vizinho.
            radius_factor = 1.4
        color = player_shot_color(base_color, self.player_index)

        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * speed)  # 0..1
        step = int(round(pulse * _GLOW_STEPS))

        # Halo ELÍPTICO derivado do próprio tiro: cada eixo escala com o `w`/`h`
        # atual da bala — que já embute a orientação (side/top-down), o tamanho-base
        # da nave e o Giant Shot. `×2` porque o fator é semieixo (raio), a superfície
        # é o diâmetro. Piso por eixo evita glow fino demais no laser estreito; teto
        # deixa o gigante crescer sem estourar. Quantiza em par p/ limitar o cache.
        min_px = _GLOW_MIN_COMMON if is_common else _GLOW_MIN_POWER
        axis = radius_factor * 2.0 * vq.glow_scale
        glow_w = max(min_px, min(int(self.w * axis), _GLOW_MAX_PX))
        glow_h = max(min_px, min(int(self.h * axis), _GLOW_MAX_PX))
        glow_w -= glow_w % 2
        glow_h -= glow_h % 2

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        pos = (int(cx - glow_w / 2), int(cy - glow_h / 2))
        if is_common:
            surface.blit(
                _get_common_shot_glow(glow_w, glow_h, color, step),
                pos,
                special_flags=pygame.BLEND_RGB_ADD,
            )
        else:
            surface.blit(_get_power_glow(glow_w, glow_h, color, step), pos)

    def _common_shot_glow_color(self) -> Tuple[int, int, int]:
        """Cor-base do halo de um tiro comum: a mesma cor do corpo desenhado."""
        if self.ship_id == "reverberador":
            # A rampa do combo é contínua e cada cor vira uma entrada no cache
            # de glow — quantizar em 5 passos mantém o cache pequeno sem que a
            # transição fique perceptívelmente escalonada.
            k = round(self.combo_intensity * 4) / 4.0
            return _reverberador_colors(k)[0]
        color = _SHIP_GLOW_COLORS.get(self.ship_id)
        if color is not None:
            return color
        return colors.PURPLE if self.piercing else colors.YELLOW

    def _breathing_rect(self, rect: pygame.Rect) -> pygame.Rect:
        """Rect visual do Giant Shot pulsando ±12% em torno do centro.

        Retorna uma CÓPIA inflada (``rect.inflate`` não muta o original), então o
        hitbox em ``self._rect`` fica intacto — é só respiração cosmética. Ritmo
        lento, alinhado ao halo âmbar do gigante. A amplitude é generosa (±12%)
        porque, arredondada em pixels, uma dose menor sumiria nos tiros pequenos.
        """
        factor = 0.12 * math.sin(pygame.time.get_ticks() * 0.005)
        return rect.inflate(round(rect.width * factor), round(rect.height * factor))

    def _draw_ship_specific_bullet(self, surface: pygame.Surface):
        """Desenha o projétil básico customizado conforme a nave.

        Toda cor passa por `player_shot_color`: o P1 recebe a tupla de volta intacta
        e o P2 a mesma cor com a matiz girada, casando com o casco ciano dele.
        """
        rect = self.rect
        # Giant Shot "respira": o corpo pulsa ±6% no tamanho VISUAL (o hitbox
        # segue em self._rect, intacto). Berserk fica de fora — já gira no eixo e
        # o tamanho variável estouraria o cache de frames pré-rotacionados.
        if self.size_multiplier > 1.0 and self.ship_id != "berserk":
            rect = self._breathing_rect(rect)
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
            # Reverberador: magenta com anéis que ESQUENTA com o combo — quanto
            # maior o bônus de dano, mais clara a cor e mais um anel entra.
            k = self.combo_intensity
            body_color, ring_color = _reverberador_colors(k)
            pygame.draw.rect(surface, player_shot_color(body_color, tint), rect)
            # Núcleo branco a partir da metade do combo: o tiro fica incandescente.
            if k >= 0.5 and rect.width > 2 and rect.height > 2:
                core = rect.inflate(-max(2, rect.width // 3), -max(2, rect.height // 3))
                pygame.draw.rect(surface, player_shot_color((255, 255, 255), tint), core)
            tinted_ring = player_shot_color(ring_color, tint)
            for i in range(1, 4 if k >= 0.6 else 3):
                ring_rect = rect.inflate(i * 4, i * 4)
                pygame.draw.rect(surface, tinted_ring, ring_rect, 1)
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
        frames = _get_homing_frames(
            self.player_index,
            self.explosive,
            giant_visual_scale(self.size_multiplier),
        )
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
        # Giant Shot engorda o hitbox (~3x); a granada acompanha pela raiz para
        # crescer visível sem virar um borrão. `scale = 1.0` (sem Giant Shot)
        # mantém o raio 5 original.
        scale = giant_visual_scale(self.size_multiplier)
        radius = max(1, round(5 * scale))

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
            body_surf = _get_explosive_body(blink_on, tint, radius)
        else:
            core_color = (255, int(200 * pulse) + 55, 0)
            body_surf = _get_explosive_body(False, tint, radius)

        # 1 blit em vez de 2 draw.circle (outer + body).
        bw, bh = body_surf.get_size()
        surface.blit(body_surf, (cx_int - bw // 2, cy_int - bh // 2))

        # Núcleo pulsante (dinâmico — fica fora do cache).
        pygame.draw.circle(
            surface,
            player_shot_color(core_color, tint),
            (cx_int, cy_int),
            max(1, radius - 2),
        )

        # Sparks: posição dinâmica, mantém draw.circle.
        num_sparks = 6 if self.low_ammo else 4
        spark_radius = radius + 3
        time_offset = ticks * 0.003
        spark_color = player_shot_color(
            (255, 100, 100) if self.low_ammo else (255, 255, 100), tint
        )
        angle_step = 2 * math.pi / num_sparks
        spark_dot = max(1, round(scale))
        cos = math.cos
        sin = math.sin
        for i in range(num_sparks):
            angle = time_offset + i * angle_step
            spark_x = center_x + cos(angle) * spark_radius
            spark_y = center_y + sin(angle) * spark_radius
            pygame.draw.circle(
                surface, spark_color, (int(spark_x), int(spark_y)), spark_dot
            )
