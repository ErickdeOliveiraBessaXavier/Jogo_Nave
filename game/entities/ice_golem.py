"""IceGolem — Tank Ofensivo do bioma MOUNTAINS.

Reformulação: o golem deixa de ser um tank passivo e vira um sistema único em
que **defesa, ataque e ponto fraco são a mesma coisa**, girando em torno de uma
gema central.

Arquitetura (entidades-irmãs, não partes internas)
---------------------------------------------------
- `IceGolem` **é a gema central** — o núcleo flutuante e o verdadeiro ponto
  fraco. É a entidade que o spawner cria.
- `IceGolemFragment` — 4 rochas que orbitam a gema. Cada uma é uma entidade
  irmã na lista de inimigos (criadas pela gema no 1º update via
  `ctx.new_enemies`). Assim cada rocha é atingível por bala e colide com a nave
  por conta própria, pelo caminho de colisão padrão — sem máscara composta por
  frame (§7). A gema **coordena** as rochas escrevendo posições-alvo públicas
  (`home_x/home_y/orbit_angle`) e chamando `start_boomerang` — nunca lê estado
  privado delas (§1).

Defesa = janelas, não muralha
-----------------------------
A gema é sempre atingível, mas aplica **redução de dano por exposição** no
`on_hit`: com as 4 rochas em formação fechada o tiro quase ricocheteia (~10%);
a vulnerabilidade sobe conforme rochas morrem, conforme rochas saem da órbita
no bumerangue, e ao máximo na fase de expansão. A estratégia ideal é achar a
janela da gema exposta — destruir todas as pedras é um caminho alternativo
(mais caos na tela), não o único.

Fragmentação
------------
Ao morrer, cada rocha **não some**: retorna `HitResult(fragments=...)` com
2-3 mini-meteoros de gelo arremessados (canal `absorb_fragments`/pool já
existente). Vira ameaça secundária — a decisão é "abro a gema mas crio caos?".

Fases (FSM na gema)
-------------------
1. ``FORMATION_CLOSED`` — órbita próxima, giro lento. Gema protegida.
2. ``BOOMERANG_ATTACK`` — cada rocha, **uma por vez** (escalonada), abandona a
   órbita, avança até o jogador e retorna ao ponto orbital (satélite/bumerangue).
   Pressão constante e alternada.
3. ``EXPANSION`` — giro acelera e a órbita abre e fecha; a gema fica exposta
   (janela de vulnerabilidade) enquanto as rochas controlam mais área.

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3); reação de dano via
`HitResult` (§8); fragmentação pelo canal de `fragments`/pool (§7).
"""

import math
import random
from enum import Enum
from typing import TYPE_CHECKING, List

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


SPRITE_DIR = "Ice_Golem_Cristal"


def _load_ice_golem_sprites() -> None:
    """Pré-carrega (uma vez) os sprites da gema, das rochas e dos estilhaços."""
    IceGolem.load_sprites()
    IceGolemFragment.load_sprites()
    IceShard.load_sprites()


class IceGolemPhase(Enum):
    """Estados de fase do IceGolem."""

    FORMATION_CLOSED = "closed"  # Formação defensiva, gema protegida
    BOOMERANG_ATTACK = "boomerang"  # Rochas atacam uma a uma e retornam
    EXPANSION = "expansion"  # Órbita abre, gema exposta


def _scale(surf: pygame.Surface, target: int) -> pygame.Surface:
    """Escala mantendo proporção para que o maior lado seja `target`."""
    w, h = surf.get_size()
    f = target / max(w, h)
    return pygame.transform.smoothscale(surf, (round(w * f), round(h * f)))


# Extensões de imagem aceitas ao varrer a pasta de fragmentos (content-driven).
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"})


class IceShard(EnemyHitMixin):
    """Estilhaço físico de uma rocha destruída — entidade independente.

    Totalmente orientado por conteúdo: TODOS os sprites presentes em
    ``assets/images/Ice_Golem_Cristal/Fragmentos`` são carregados
    automaticamente (ordem alfabética) e ficam disponíveis para sorteio. Basta
    adicionar/remover arquivos na pasta para mudar os fragmentos — nenhum nome
    de arquivo é hardcoded além da pasta raiz.

    Cada estilhaço sorteia um sprite e um tamanho pequeno (`MIN_SIZE`..`MAX_SIZE`),
    herda a direção geral da explosão com pequenas variações de ângulo/velocidade
    e ganha rotação própria — transmitindo uma quebra natural.
    """

    FRAGMENTS_SUBDIR = "Fragmentos"  # único caminho referenciado, sob SPRITE_DIR
    MIN_SIZE = 12
    MAX_SIZE = 18
    GRAVITY = 220.0  # px/s²: estilhaços caem como detritos (top-down)

    _raw_sprites: List[pygame.Surface] = []

    @classmethod
    def load_sprites(cls) -> None:
        """Varre a pasta de fragmentos e carrega tudo que for imagem."""
        if cls._raw_sprites:
            return
        folder = BASE_DIR / "assets" / "images" / SPRITE_DIR / cls.FRAGMENTS_SUBDIR
        if not folder.is_dir():
            return
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in _IMAGE_EXTS:
                cls._raw_sprites.append(get_image(path))

    @classmethod
    def has_sprites(cls) -> bool:
        return bool(cls._raw_sprites)

    def __init__(self, cx: float, cy: float, vx: float, vy: float):
        if not self._raw_sprites:
            self.load_sprites()

        size = random.randint(self.MIN_SIZE, self.MAX_SIZE)
        self.w = size
        self.h = size
        self.x = cx - size / 2
        self.y = cy - size / 2
        self.vx = vx
        self.vy = vy

        self.angle = random.uniform(0.0, 360.0)
        self.spin = random.uniform(-360.0, 360.0)  # graus/s

        self.dead = False
        self.health = 1
        self.active = True

        # Sprite-base escalado ao tamanho sorteado (rotacionado no draw).
        if self._raw_sprites:
            self._base = _scale(random.choice(self._raw_sprites), size)
        else:
            self._base = None

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.5

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        self.vy += self.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle = (self.angle + self.spin * dt) % 360.0

        # Remove ao sair da tela (com margem) — não acumula no hot path.
        margin = self.w + 48
        if (
            self.y > Config.SCREEN_HEIGHT + margin
            or self.y < -margin
            or self.x < -margin
            or self.x > Config.SCREEN_WIDTH + margin
        ):
            self.dead = True

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 10

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=10,
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=4, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, explosion_size=8, sound=hit_sounds.EXPLOSION_ASTEROID)

    def should_remove(self) -> bool:
        return self.dead

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
        if self._base is not None:
            img = pygame.transform.rotate(self._base, self.angle)
            surface.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            pygame.draw.rect(
                surface, (170, 215, 245), (int(self.x), int(self.y), self.w, self.h),
                border_radius=2,
            )


class IceGolemFragment(EnemyHitMixin):
    """Uma rocha orbital: armadura, arma (bumerangue) e fonte de fragmentos.

    É uma entidade-irmã na lista de inimigos. A gema escreve sua posição-alvo
    de órbita (`home_x/home_y/orbit_angle`) a cada frame e dispara o ataque via
    `start_boomerang`. A rocha só é dona da própria cinemática de dash, HP e
    desenho — toda a geometria da formação vive na gema.
    """

    FRAG_SIZE = 46
    BASE_HEALTH = 55

    # Bumerangue
    BOOM_DURATION = 1.05  # tempo total do dash (ida + volta)
    BOOM_ADVANCE_FRAC = 0.45  # fração do tempo gasta avançando
    BOOM_DASH_DISTANCE = 320.0  # alcance máximo do avanço

    # Mapeia o slot ao arquivo do canto correspondente (a arte é desenhada para
    # cantos de um quadrado; cada slot recebe a peça que aponta para fora).
    _CORNER_FILES = {
        "tl": "Canto_Superior_Esquerdo.png",
        "tr": "Canto_Superior_Direito.png",
        "br": "Canto_Inferior_Direito.png",
        "bl": "Canto_Inferior_Esquerdo.png",
    }
    _sprites: dict[str, pygame.Surface] = {}

    @classmethod
    def load_sprites(cls) -> None:
        if cls._sprites:
            return
        for key, fname in cls._CORNER_FILES.items():
            path = BASE_DIR / "assets" / "images" / SPRITE_DIR / fname
            if path.exists():
                cls._sprites[key] = _scale(get_image(path), cls.FRAG_SIZE)

    def __init__(self, corner: str, base_angle: float):
        """corner: chave em `_CORNER_FILES`. base_angle: ângulo do slot (rad)."""
        if not self._sprites:
            self.load_sprites()
        self.corner = corner
        self.base_angle = base_angle

        self.w = self.FRAG_SIZE
        self.h = self.FRAG_SIZE
        # Posição inicial = origem; a gema reescreve já no 1º update dela.
        self.x = 0.0
        self.y = 0.0

        self.health = self.BASE_HEALTH
        self.dead = False
        self.hit_timer = 0.0

        # Alvo de órbita escrito pela gema (canto superior-esquerdo da rocha).
        self.home_x = 0.0
        self.home_y = 0.0
        self.orbit_angle = base_angle  # para girar a arte com a formação

        # Estado de ataque bumerangue.
        self.attacking = False
        self._boom_t = 0.0
        self._launch_cx = 0.0  # centro no instante do disparo
        self._launch_cy = 0.0
        self._target_cx = 0.0  # ponto de avanço (em direção ao jogador)
        self._target_cy = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def collision_circle(self) -> tuple[float, float, float]:
        cx, cy = self.center
        return cx, cy, self.w * 0.45

    def start_boomerang(self, player_x: float, player_y: float) -> None:
        """Inicia o dash em direção ao jogador (chamado pela gema)."""
        if self.attacking or self.dead:
            return
        cx, cy = self.center
        self._launch_cx, self._launch_cy = cx, cy
        dx, dy = player_x - cx, player_y - cy
        dist = math.hypot(dx, dy) or 1.0
        reach = min(self.BOOM_DASH_DISTANCE, dist)
        self._target_cx = cx + dx / dist * reach
        self._target_cy = cy + dy / dist * reach
        self._boom_t = 0.0
        self.attacking = True

    # update_in_context exigido pelo dispatcher polimórfico do EntityManager (§5).
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.attacking:
            self._update_boomerang(dt)
        else:
            # Em órbita: cola na posição-alvo escrita pela gema.
            self.x = self.home_x
            self.y = self.home_y

    def _update_boomerang(self, dt: float) -> None:
        """Ida em direção ao jogador, volta para a posição orbital (que se move)."""
        self._boom_t = min(1.0, self._boom_t + dt / self.BOOM_DURATION)
        adv = self.BOOM_ADVANCE_FRAC
        # Centro atual da posição orbital viva (a gema continua girando a formação).
        home_cx = self.home_x + self.w / 2
        home_cy = self.home_y + self.h / 2

        if self._boom_t < adv:
            k = self._ease_out(self._boom_t / adv)
            cx = self._launch_cx + (self._target_cx - self._launch_cx) * k
            cy = self._launch_cy + (self._target_cy - self._launch_cy) * k
        else:
            k = self._ease_in((self._boom_t - adv) / (1.0 - adv))
            cx = self._target_cx + (home_cx - self._target_cx) * k
            cy = self._target_cy + (home_cy - self._target_cy) * k

        self.x = cx - self.w / 2
        self.y = cy - self.h / 2

        if self._boom_t >= 1.0:
            self.attacking = False
            self.x, self.y = self.home_x, self.home_y

    @staticmethod
    def _ease_out(t: float) -> float:
        return 1.0 - (1.0 - t) * (1.0 - t)

    @staticmethod
    def _ease_in(t: float) -> float:
        return t * t

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 120

    def make_shards(self) -> tuple:
        """Instancia estilhaços `IceShard` herdando a direção geral da explosão.

        A direção base é o vetor radial para fora do núcleo (`orbit_angle`), com
        pequenas variações de ângulo/velocidade por estilhaço. Sprites e tamanho
        são sorteados pelo próprio `IceShard` (content-driven). Público: a gema
        também chama isto ao morrer para estilhaçar as rochas restantes (parente
        coordenando o composite — §1)."""
        cx, cy = self.center
        count = random.randint(2, 4)
        base = self.orbit_angle  # direção geral: para fora do núcleo
        shards = []
        for _ in range(count):
            ang = base + random.uniform(-0.5, 0.5)
            speed = random.uniform(160.0, 250.0)
            vx = math.cos(ang) * speed
            vy = math.sin(ang) * speed
            shards.append(IceShard(cx, cy, vx, vy))
        return tuple(shards)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=28,
                sound=hit_sounds.EXPLOSION_ASTEROID,
                fragments=self.make_shards(),
            )
        return HitResult(explosion_size=8, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        # Armadura sólida: machuca a nave (o dano à nave é aplicado pelo
        # dispatcher de colisão) mas a rocha **não** é destruída pelo contato.
        from ..systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead

    def draw(self, surface: pygame.Surface) -> None:
        sprite = self._sprites.get(self.corner)
        cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
        if sprite is not None:
            # Gira a arte com a formação: a peça de canto mantém a face interna
            # apontada para o núcleo durante todo o giro. pygame.rotate é CCW(+);
            # o avanço de `orbit_angle` (screen-space) é visualmente horário, então
            # compensa-se com -graus.
            rot = -math.degrees(self.orbit_angle - self.base_angle)
            img = pygame.transform.rotate(sprite, rot)
            if self.hit_timer > 0.0:
                img = img.copy()
                img.fill(colors.WHITE, special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            color = (200, 235, 255) if self.hit_timer > 0.0 else (150, 200, 240)
            pygame.draw.rect(
                surface, color, (int(self.x), int(self.y), self.w, self.h),
                border_radius=4,
            )


class IceGolem(EnemyHitMixin):
    """A gema central — núcleo flutuante, ponto fraco e cérebro da formação."""

    # Tamanho do alvo (a gema). Pequeno de propósito: é o ponto fraco focado.
    GEM_SIZE = 54
    SPRITE_TARGET = 72  # sprite desenhado um pouco maior que o hitbox
    # `W`/`H`: contrato de tamanho lido pelo spawner (`_entry_position`).
    W = GEM_SIZE
    H = GEM_SIZE

    MOVE_SPEED = 46.0
    ENTRY_SPEED = 90.0

    CORE_HEALTH = 220

    # Órbita
    BASE_ORBIT_DISTANCE = 60.0
    EXPANDED_ORBIT_DISTANCE = 128.0
    SPIN_CLOSED = 1.1  # rad/s
    SPIN_EXPANSION = 2.6  # rad/s

    # Fases
    PHASE_CLOSED_DURATION = 3.5
    EXPANSION_DURATION = 4.5
    BOOMERANG_STAGGER = 0.85  # intervalo entre disparos individuais

    # Animação da gema
    NUM_GEM_FRAMES = 8
    GEM_ANIM_FPS = 7.0

    _explosion_size_killed = 90
    _gem_frames: List[pygame.Surface] = []

    @classmethod
    def load_sprites(cls) -> None:
        if cls._gem_frames:
            return
        # A animação é base + _01.._07 (8 frames; o 1º não tem sufixo numérico).
        names = ["Gema_Central_Controladora.png"] + [
            f"Gema_Central_Controladora_{i:02d}.png" for i in range(1, cls.NUM_GEM_FRAMES)
        ]
        frames: List[pygame.Surface] = []
        for name in names:
            path = BASE_DIR / "assets" / "images" / SPRITE_DIR / name
            if path.exists():
                frames.append(_scale(get_image(path), cls.SPRITE_TARGET))
        cls._gem_frames = frames

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        if not self._gem_frames:
            self.load_sprites()

        self.x = x
        self.y = y
        self.w = self.GEM_SIZE
        self.h = self.GEM_SIZE

        # Entrada
        self.target_y = float(random.randint(80, 160))
        self.entry_speed = self.ENTRY_SPEED
        self._entry_done = False
        self.side_scroll = side_scroll

        # Saúde / estado
        self.dead = False
        self.core_health = self.CORE_HEALTH
        self.hit_timer = 0.0
        self.active = True
        self._deflect = False  # último hit foi defletido pela armadura?

        self._aggr = max(0.5, aggressiveness_multiplier)

        # Fragmentos (criados no 1º update via ctx.new_enemies).
        self.fragments: List[IceGolemFragment] = []
        self._fragments_spawned = False

        # FSM
        self.phase = IceGolemPhase.FORMATION_CLOSED
        self.phase_timer = self.PHASE_CLOSED_DURATION
        self.spin = 0.0
        self.orbit_distance = self.BASE_ORBIT_DISTANCE

        # Bumerangue
        self._boom_pending: List[IceGolemFragment] = []
        self._boom_timer = 0.0

        # Animação cosmética
        self.anim_time = 0.0
        self.anim_phase = random.uniform(0.0, float(self.NUM_GEM_FRAMES))
        self.bob_phase = random.uniform(0.0, math.tau)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def health(self) -> int:
        """Compat: código legado/spawner acessa `health`."""
        return self.core_health

    @health.setter
    def health(self, value: int) -> None:
        self.core_health = value

    @property
    def live_fragments(self) -> List[IceGolemFragment]:
        return [f for f in self.fragments if not f.dead]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        if not self._fragments_spawned:
            self._spawn_fragments(ctx)
            self._fragments_spawned = True
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def _spawn_fragments(self, ctx: "EnemyUpdateContext") -> None:
        """Cria as 4 rochas e as registra como inimigos-irmãos (§2/§5)."""
        # Cantos do quadrado em screen-space (y para baixo).
        slots = [
            ("tl", 5 * math.pi / 4),  # superior-esquerdo
            ("tr", 7 * math.pi / 4),  # superior-direito
            ("br", math.pi / 4),  # inferior-direito
            ("bl", 3 * math.pi / 4),  # inferior-esquerdo
        ]
        for corner, ang in slots:
            frag = IceGolemFragment(corner, ang)
            self.fragments.append(frag)
            ctx.new_enemies.append(frag)
        self._position_fragments()

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        self.anim_time += dt
        self.anim_phase += self.GEM_ANIM_FPS * dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Entrada
        if not self._entry_done:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._entry_done = True
            self._position_fragments()
            return

        # Movimento lateral lento perseguindo o jogador.
        cx, _ = self.center
        dx = player_x - cx
        if abs(dx) > 4.0:
            self.x += math.copysign(self.MOVE_SPEED * dt, dx)
        self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
        # Flutuação cosmética vertical.
        self.y = self.target_y + math.sin(self.anim_time + self.bob_phase) * 4.0

        self._update_phase(dt, player_x, player_y)
        self._update_spin_and_orbit(dt)
        self._position_fragments()

    def _update_phase(self, dt: float, player_x: float, player_y: float) -> None:
        self.phase_timer -= dt

        if self.phase == IceGolemPhase.FORMATION_CLOSED:
            if self.phase_timer <= 0.0:
                self._enter_boomerang()
        elif self.phase == IceGolemPhase.BOOMERANG_ATTACK:
            self._update_boomerang_cycle(dt, player_x, player_y)
        else:  # EXPANSION
            if self.phase_timer <= 0.0:
                self.phase = IceGolemPhase.FORMATION_CLOSED
                self.phase_timer = self.PHASE_CLOSED_DURATION / self._aggr

    def _enter_boomerang(self) -> None:
        self.phase = IceGolemPhase.BOOMERANG_ATTACK
        # Fila de quem ainda vai atacar neste ciclo (só rochas vivas).
        self._boom_pending = list(self.live_fragments)
        self._boom_timer = 0.4

    def _update_boomerang_cycle(
        self, dt: float, player_x: float, player_y: float
    ) -> None:
        """Dispara as rochas uma a uma; ao fim do ciclo entra em expansão."""
        # Limpa mortas da fila.
        self._boom_pending = [f for f in self._boom_pending if not f.dead]

        self._boom_timer -= dt
        if self._boom_timer <= 0.0 and self._boom_pending:
            frag = self._boom_pending.pop(0)
            frag.start_boomerang(player_x, player_y)
            self._boom_timer = self.BOOMERANG_STAGGER / self._aggr

        # Ciclo completo: ninguém na fila e ninguém mais atacando.
        cycle_done = not self._boom_pending and not any(
            f.attacking for f in self.live_fragments
        )
        if cycle_done:
            self.phase = IceGolemPhase.EXPANSION
            self.phase_timer = self.EXPANSION_DURATION

    def _update_spin_and_orbit(self, dt: float) -> None:
        if self.phase == IceGolemPhase.EXPANSION:
            self.spin += self.SPIN_EXPANSION * dt
            # Abre e fecha ao longo da fase (vai a EXPANDED no meio e volta).
            p = 1.0 - max(0.0, self.phase_timer) / self.EXPANSION_DURATION
            open_k = math.sin(p * math.pi)  # 0 → 1 → 0
            self.orbit_distance = (
                self.BASE_ORBIT_DISTANCE
                + (self.EXPANDED_ORBIT_DISTANCE - self.BASE_ORBIT_DISTANCE) * open_k
            )
        else:
            self.spin += self.SPIN_CLOSED * dt
            self.orbit_distance = self.BASE_ORBIT_DISTANCE

    def _position_fragments(self) -> None:
        """Escreve a posição-alvo de órbita de cada rocha viva (geometria na gema)."""
        cx, cy = self.center
        for frag in self.fragments:
            if frag.dead:
                continue
            angle = frag.base_angle + self.spin
            frag.orbit_angle = angle
            frag.home_x = cx + math.cos(angle) * self.orbit_distance - frag.w / 2
            frag.home_y = cy + math.sin(angle) * self.orbit_distance - frag.h / 2

    # ------------------------------------------------------------------
    # Dano / exposição
    # ------------------------------------------------------------------

    def _gem_vulnerability(self) -> float:
        """Fração de dano que chega à gema, em [0, 1].

        - 0 rochas vivas → totalmente exposta.
        - Expansão → exposição alta, modulada pela abertura da órbita.
        - Fechada/bumerangue → protegida; melhora ao perder rochas e quando
          rochas estão fora da órbita (atacando).
        """
        live = self.live_fragments
        n = len(live)
        if n == 0:
            return 1.0

        if self.phase == IceGolemPhase.EXPANSION:
            open_k = (self.orbit_distance - self.BASE_ORBIT_DISTANCE) / (
                self.EXPANDED_ORBIT_DISTANCE - self.BASE_ORBIT_DISTANCE
            )
            return min(1.0, 0.45 + 0.55 * open_k)

        # Fechada / bumerangue: base ~10% com 4 rochas, sobe ao perder rochas.
        missing = (4 - n) / 4.0
        away = sum(1 for f in live if f.attacking) / 4.0
        return min(1.0, 0.10 + 0.45 * missing + 0.25 * away)

    def take_damage(self, amount: int) -> None:
        self.core_health -= amount
        self.hit_timer = 0.1
        if self.core_health <= 0:
            self.dead = True

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        vuln = self._gem_vulnerability()
        effective = int(round(damage * vuln))

        if effective <= 0:
            # Tiro ricocheteia na armadura — feedback claro, sem perda de HP.
            self._deflect = True
            self.hit_timer = 0.06
            return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)

        self._deflect = False
        self.take_damage(effective)
        if self.dead:
            return self._build_death_result()
        return HitResult(explosion_size=12, sound=hit_sounds.BOSS_DAMAGE)

    def _build_death_result(self) -> "HitResult":
        """Morte da gema = fim do encontro: as rochas estilhaçam junto."""
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        shards: list = []
        for frag in self.fragments:
            if not frag.dead:
                shards.extend(frag.make_shards())
                frag.dead = True
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=self._explosion_size_killed,
            sound=hit_sounds.EXPLOSION_ALIEN,
            fragments=tuple(shards),
        )

    def get_points_value(self) -> int:
        return 600

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead

    # ------------------------------------------------------------------
    # Render (§3: sem efeitos colaterais)
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.center[0]), int(self.center[1])

        # Halo de exposição: cresce quando a gema está vulnerável (leitura visual
        # da janela de ataque).
        vuln = self._gem_vulnerability()
        if vuln > 0.4:
            halo = int(self.GEM_SIZE * (0.6 + 0.5 * vuln))
            glow = pygame.Surface((halo * 2, halo * 2), pygame.SRCALPHA)
            a = int(60 * vuln + 30 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0)))
            pygame.draw.circle(glow, (120, 220, 255, max(0, min(120, a))), (halo, halo), halo)
            surface.blit(glow, (cx - halo, cy - halo))

        self._draw_gem(surface, cx, cy, vuln)

        # Escudo quando protegida: anel ciano pulsante (não desenha em vuln alta).
        if vuln <= 0.4:
            r = int(self.GEM_SIZE * 0.7 + 2 * math.sin(self.anim_time * 6.0))
            pygame.draw.circle(surface, (140, 210, 255), (cx, cy), r, 1)

    def _draw_gem(self, surface: pygame.Surface, cx: int, cy: int, vuln: float) -> None:
        frames = self._gem_frames
        if frames:
            frame = frames[int(self.anim_phase) % len(frames)]
            if self.hit_timer > 0.0:
                frame = frame.copy()
                tint = colors.WHITE if not self._deflect else (120, 200, 255)
                frame.fill(tint, special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(frame, frame.get_rect(center=(cx, cy)).topleft)
            return

        # Fallback procedural se a arte não carregou.
        gem_color = (int(100 + 120 * vuln), int(180 + 60 * vuln), 255)
        pygame.draw.circle(surface, gem_color, (cx, cy), self.GEM_SIZE // 2)
        pygame.draw.circle(surface, (200, 235, 255), (cx, cy), self.GEM_SIZE // 2, 2)


# Registra para o preload de sprites (mesma convenção do StoneEagle/Satellite).
sprite_loader.register("IceGolem", _load_ice_golem_sprites)
