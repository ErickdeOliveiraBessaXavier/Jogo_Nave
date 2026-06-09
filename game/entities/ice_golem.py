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
from typing import TYPE_CHECKING, Any, List

import pygame

from ..core import colors
from ..core.assets import BASE_DIR, get_image
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader
from .enemy_hit_mixin import EnemyHitMixin
from .explosion import ExplosionType

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


SPRITE_DIR = "Ice_Golem_Cristal"


def _load_ice_golem_sprites() -> None:
    """Pré-carrega (uma vez) os sprites da gema, das rochas e dos estilhaços."""
    IceGolem.load_sprites()
    IceGolemFragment.load_sprites()
    IceShard.load_sprites()
    IceGemShard.load_sprites()


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


class _IceDustParticle:
    """Grão de poeira mineral que se desprende de uma rocha orbital.

    Detalhe cosmético discreto: reforça a sensação de massa e desgaste das
    rochas energizadas. Segue o mesmo padrão do `_SerpentDustParticle`
    (MountainSerpentBoss) para consistência visual do tema Montanha. `update`
    move/decai; `draw` apenas desenha (§3).
    """

    __slots__ = ("x", "y", "vx", "vy", "size", "life", "max_life")

    _VX_RANGE = (-14.0, 14.0)  # px/s
    _VY_RANGE = (16.0, 44.0)  # px/s (positivo = cai)
    _GRAVITY = 70.0  # px/s²
    _LIFE_RANGE = (0.4, 0.85)  # segundos
    _SIZE_RANGE = (1, 3)  # pixels
    _BASE_COLOR = (168, 192, 214)  # poeira mineral fria (azul-acinzentada)

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(*self._VX_RANGE)
        self.vy = random.uniform(*self._VY_RANGE)
        self.size = random.randint(*self._SIZE_RANGE)
        self.max_life = random.uniform(*self._LIFE_RANGE)
        self.life = self.max_life

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self._GRAVITY * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0.0:
            return
        fade = max(0.0, self.life / self.max_life)
        r, g, b = self._BASE_COLOR
        pygame.draw.rect(
            surface,
            (int(r * fade), int(g * fade), int(b * fade)),
            (int(self.x), int(self.y), self.size, self.size),
        )


class _GemEnergyMote:
    """Faísca de energia azul do núcleo — atração (nascimento) ou fuga (colapso).

    Dois modos:
    - ``homing=True``: nasce a alguma distância e **converge para o centro vivo**
      da gema a cada frame (atração durante o nascimento/reconstrução). Como
      persegue o centro atual — e não um ponto capturado no spawn — as faíscas
      terminam exatamente no centro visual do cristal, mesmo com a gema flutuando
      ou perseguindo o jogador (alinhamento pedido).
    - ``homing=False``: nasce junto ao núcleo e **escapa para fora** em linha
      reta (pequenos pulsos de energia vazando durante o colapso crítico).

    Detalhe puramente cosmético — `update` move/decai, `draw` só desenha (§3).
    """

    __slots__ = (
        "x", "y", "vx", "vy", "speed", "homing", "crystalline",
        "life", "max_life", "size", "color",
    )

    _HOME_SPEED = (90.0, 180.0)  # px/s rumo ao centro (atração)
    _OUT_SPEED = (70.0, 160.0)  # px/s para fora (fuga no colapso)
    _LIFE = (0.35, 0.7)  # segundos
    _COLORS = ((120, 220, 255), (180, 240, 255), (90, 180, 255))  # azul/ciano gelo

    def __init__(
        self,
        cx: float,
        cy: float,
        angle: float,
        radius: float,
        homing: bool = True,
        crystalline: bool = False,
    ) -> None:
        self.x = cx + math.cos(angle) * radius
        self.y = cy + math.sin(angle) * radius
        self.homing = homing
        # Cristalino: desenhado como um pequeno losango (caco) em vez de círculo,
        # reforçando a leitura de "energia cristalina" se condensando.
        self.crystalline = crystalline
        if homing:
            self.speed = random.uniform(*self._HOME_SPEED)
            self.vx = 0.0  # recalculado por frame em direção ao centro vivo
            self.vy = 0.0
        else:
            self.speed = 0.0
            spd = random.uniform(*self._OUT_SPEED)
            self.vx = math.cos(angle) * spd  # para fora do núcleo
            self.vy = math.sin(angle) * spd
        self.max_life = random.uniform(*self._LIFE)
        self.life = self.max_life
        self.size = random.randint(2, 3) + (1 if crystalline else 0)
        self.color = random.choice(self._COLORS)

    @property
    def dead(self) -> bool:
        return self.life <= 0.0

    def update(self, dt: float, cx: float, cy: float) -> None:
        if self.homing:
            dx, dy = cx - self.x, cy - self.y
            dist = math.hypot(dx, dy)
            step = self.speed * dt
            if dist <= step or dist < 1.0:
                # Chegou ao centro visual: dissipa exatamente sobre o cristal.
                self.x, self.y = cx, cy
                self.life = 0.0
                return
            self.x += dx / dist * step
            self.y += dy / dist * step
        else:
            self.x += self.vx * dt
            self.y += self.vy * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0.0:
            return
        fade = max(0.0, self.life / self.max_life)
        r, g, b = self.color
        col = (int(r * fade), int(g * fade), int(b * fade))
        x, y, s = int(self.x), int(self.y), self.size
        if self.crystalline:
            # Losango cristalino (caco de energia).
            pygame.draw.polygon(surface, col, ((x, y - s), (x + s, y), (x, y + s), (x - s, y)))
        else:
            pygame.draw.circle(surface, col, (x, y), s)


class IceShard:
    """Estilhaço **puramente visual** de uma rocha destruída.

    NÃO é inimigo: não causa dano, não é atingível por tiro e não entra na
    spatial grid. Existe só para reforçar a leitura de *quebra/destruição* da
    rocha — voa para fora herdando a direção da explosão, gira, cai por gravidade
    e esmaece. Vive numa lista cosmética do `EntityManager` (`ice_shards`), no
    mesmo molde de `SplitterDebris`/`CarrierDebris` (atualiza/desenha, nunca
    colide). Decisão de design: microfragmentos com dano prejudicavam a leitura
    do combate (dano "injusto", difícil de rastrear) — viraram efeito visual.

    Orientado por conteúdo: TODOS os sprites em
    ``assets/images/Ice_Golem_Cristal/Fragmentos`` são carregados (ordem
    alfabética). Tamanho propositalmente **grande/legível** (`MIN_SIZE`..
    `MAX_SIZE`), pois o efeito é o protagonista, não uma ameaça discreta.
    """

    FRAGMENTS_SUBDIR = "Fragmentos"  # único caminho referenciado, sob SPRITE_DIR
    # Maiores que os antigos microfragmentos (12–18): o efeito precisa ler claro.
    MIN_SIZE = 20
    MAX_SIZE = 32
    GRAVITY = 220.0  # px/s²: cacos caem como detritos (top-down)
    _LIFE = (0.7, 1.2)  # s de vida antes de sumir (com fade-out no fim)

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

        self.max_life = random.uniform(*self._LIFE)
        self.life = self.max_life
        self.dead = False

        # Sprite-base escalado ao tamanho sorteado (rotacionado no draw).
        if self._raw_sprites:
            self._base = _scale(random.choice(self._raw_sprites), size)
        else:
            self._base = None

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float) -> None:
        self.vy += self.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle = (self.angle + self.spin * dt) % 360.0
        self.life -= dt

        # Some ao esgotar a vida ou sair da tela (com margem) — sem acúmulo.
        margin = self.w + 48
        if (
            self.life <= 0.0
            or self.y > Config.SCREEN_HEIGHT + margin
            or self.y < -margin
            or self.x < -margin
            or self.x > Config.SCREEN_WIDTH + margin
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
        # Fade-out na metade final da vida (some suave, sem "piscar fora").
        fade = max(0.0, min(1.0, self.life / (self.max_life * 0.5)))
        if self._base is not None:
            img = pygame.transform.rotate(self._base, self.angle)
            if fade < 1.0:
                img = img.copy()
                img.fill(
                    (255, 255, 255, int(255 * fade)),
                    special_flags=pygame.BLEND_RGBA_MULT,
                )
            surface.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            box = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            pygame.draw.rect(
                box, (170, 215, 245, int(255 * fade)), (0, 0, self.w, self.h),
                border_radius=2,
            )
            surface.blit(box, (int(self.x), int(self.y)))


class IceGemShard(IceShard):
    """Estilhaço **visual** do núcleo (gema) — arte própria em ``Fragmentos_Gem``.

    Mesma física/desenho cosmético do `IceShard` (sem dano, sem colisão), mas com
    seu próprio conjunto de sprites (os cacos da gema central) e um tamanho maior,
    pois representam o cristal-núcleo se despedaçando. Arremessados quando a gema
    explode, junto às partículas azuis do colapso.

    Como `load_sprites` resolve `cls.FRAGMENTS_SUBDIR`/`cls._raw_sprites` via
    `cls`, basta sobrescrever esses dois atributos — o resto é herdado.
    """

    FRAGMENTS_SUBDIR = "Fragmentos_Gem"
    MIN_SIZE = 24
    MAX_SIZE = 38

    # Cache próprio (não compartilha a free-list de sprites do IceShard).
    _raw_sprites: List[pygame.Surface] = []


class IceGolemFragment(EnemyHitMixin):
    """Uma rocha orbital: armadura, arma (bumerangue) e fonte de fragmentos.

    É uma entidade-irmã na lista de inimigos. A gema escreve sua posição-alvo
    de órbita (`home_x/home_y/orbit_angle`) a cada frame e dispara o ataque via
    `start_boomerang`. A rocha só é dona da própria cinemática de dash, HP e
    desenho — toda a geometria da formação vive na gema.
    """

    FRAG_SIZE = 46
    BASE_HEALTH = 55

    # As rochas são parte estrutural do golem: a gema as controla pelo ciclo de
    # vida inteiro (inclusive trazendo-as de volta de fora da tela na expansão e
    # na reconstrução). Logo NÃO podem ser ceifadas pela regra genérica de
    # "inimigo fora da tela" do EntityManager. Gate por class attribute (§5),
    # consultado via getattr — sem isinstance novo no manager.
    offscreen_cull_exempt = True

    # Velocidade de convergência ao entrar na arena (reconstrução da armadura).
    ENTER_SPEED = 230.0  # px/s

    # Bumerangue — propositalmente lento para priorizar leitura e tempo de
    # reação: o jogador deve ler a trajetória, decidir e esquivar.
    BOOM_DURATION = 1.7  # tempo total do dash (ida + volta)
    BOOM_ADVANCE_FRAC = 0.5  # fração do tempo gasta avançando
    # Alcance máximo: cobre praticamente toda a tela para que o fragmento chegue
    # de fato à posição do jogador (cap só para o caso degenerado fora da tela).
    BOOM_DASH_DISTANCE = 760.0

    # Antecipação (telegraph): antes de disparar o dash, a rocha treme em
    # formação por WINDUP_DURATION, dando ao jogador uma janela clara para ler o
    # ataque e reagir. A tremedeira cresce até o disparo.
    WINDUP_DURATION = 0.8  # s de antecipação tremendo antes do dash
    WINDUP_SHAKE_AMP = 4.0  # px (amplitude máxima do tremor)
    WINDUP_SHAKE_FREQ = 46.0  # rad/s

    # Rotação própria contínua (rocha energizada/instável, não sprite girando em
    # círculo). Cada rocha sorteia sentido/velocidade próprios.
    SELF_SPIN_RANGE = (-150.0, 150.0)  # graus/s

    # Rastro fantasmagórico (estilo Alucard) durante o dash — mesma técnica do
    # SerpentRockBullet: imagens residuais com alpha decrescente.
    _TRAIL_INTERVAL = 0.045  # s entre fantasmas
    _TRAIL_LIFETIME = 0.28  # s de vida de cada fantasma
    _TRAIL_MAX_ALPHA = 120  # alpha inicial do fantasma

    # Poeira mineral desprendendo enquanto orbita.
    _PARTICLE_INTERVAL = (0.10, 0.22)  # s entre grãos

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

    def __init__(self, corner: str, base_angle: float, entering: bool = False):
        """corner: chave em `_CORNER_FILES`. base_angle: ângulo do slot (rad).

        entering: se True, a rocha nasce fora da tela e converge para a órbita
        (usado na reconstrução da armadura), em vez de já colar na posição.
        """
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

        # Reconstrução: rocha vindo de fora, ainda convergindo para a formação.
        self.entering = entering

        # Alvo de órbita escrito pela gema (canto superior-esquerdo da rocha).
        self.home_x = 0.0
        self.home_y = 0.0
        self.orbit_angle = base_angle  # para girar a arte com a formação

        # Estado de ataque bumerangue.
        self.attacking = False
        self.winding_up = False  # antecipação (tremor) antes do dash
        self._windup_t = 0.0
        self._boom_t = 0.0
        self._launch_cx = 0.0  # centro no instante do disparo
        self._launch_cy = 0.0
        self._target_cx = 0.0  # ponto de avanço (em direção ao jogador)
        self._target_cy = 0.0

        # Rotação própria contínua sobre o eixo (independente da órbita).
        self.self_angle = random.uniform(0.0, 360.0)
        self.self_spin = random.uniform(*self.SELF_SPIN_RANGE)  # graus/s

        # Rastro fantasmagórico (só durante o dash) e poeira mineral (sempre).
        self._afterimages: List[dict] = []
        self._trail_timer = 0.0
        self._particles: List[_IceDustParticle] = []
        self._particle_timer = random.uniform(*self._PARTICLE_INTERVAL)

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
        """Entra na antecipação do ataque (chamado pela gema).

        Telegrafa o alvo (na direção do jogador no instante do gatilho) e começa
        a tremer em formação; o dash em si só dispara após `WINDUP_DURATION` (ver
        `_update_windup`). Assim o jogador lê o ataque e tem janela para reagir.
        """
        if self.attacking or self.winding_up or self.dead or self.entering:
            return
        cx, cy = self.center
        dx, dy = player_x - cx, player_y - cy
        dist = math.hypot(dx, dy) or 1.0
        reach = min(self.BOOM_DASH_DISTANCE, dist)
        self._target_cx = cx + dx / dist * reach
        self._target_cy = cy + dy / dist * reach
        self.winding_up = True
        self._windup_t = 0.0

    # update_in_context exigido pelo dispatcher polimórfico do EntityManager (§5).
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Giro próprio contínuo e detalhes cosméticos (poeira / rastro).
        self.self_angle = (self.self_angle + self.self_spin * dt) % 360.0
        self._update_particles(dt)
        self._update_trail(dt)

        if self.attacking:
            self._update_boomerang(dt)
        elif self.winding_up:
            self._update_windup(dt)
        elif self.entering:
            self._update_entering(dt)
        else:
            # Em órbita: cola na posição-alvo escrita pela gema.
            self.x = self.home_x
            self.y = self.home_y

    def _update_windup(self, dt: float) -> None:
        """Antecipação: treme em formação por `WINDUP_DURATION` e então dispara.

        A rocha permanece colada na órbita (a gema segue girando a formação) — só
        o desenho treme (ver `draw`). Esgotada a antecipação, o dash parte do
        centro atual rumo ao alvo telegrafado em `start_boomerang`.
        """
        self._windup_t += dt
        self.x = self.home_x
        self.y = self.home_y
        if self._windup_t >= self.WINDUP_DURATION:
            self.winding_up = False
            cx, cy = self.center
            self._launch_cx, self._launch_cy = cx, cy
            self._boom_t = 0.0
            self.attacking = True

    def _update_entering(self, dt: float) -> None:
        """Converge de fora da tela até a posição orbital viva (que a gema move).

        Avança a passo constante em direção a `home_x/home_y`; ao alcançar,
        assume a órbita (`entering = False`) e passa a colar na formação.
        """
        dx = self.home_x - self.x
        dy = self.home_y - self.y
        dist = math.hypot(dx, dy)
        step = self.ENTER_SPEED * dt
        if dist <= step or dist < 1.0:
            self.x, self.y = self.home_x, self.home_y
            self.entering = False
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step

    def _render_angle(self) -> float:
        """Ângulo de desenho (graus): giro da formação + giro próprio.

        pygame.rotate é CCW(+); o avanço de `orbit_angle` (screen-space) é
        visualmente horário, então a parte orbital entra com -graus. O giro
        próprio (`self_angle`) soma por cima para a rocha parecer instável.
        """
        return -math.degrees(self.orbit_angle - self.base_angle) + self.self_angle

    def _update_particles(self, dt: float) -> None:
        """Emite e atualiza grãos de poeira mineral (in-place reversa)."""
        self._particle_timer -= dt
        if self._particle_timer <= 0.0:
            cx, cy = self.center
            self._particles.append(
                _IceDustParticle(
                    cx + random.uniform(-self.w * 0.3, self.w * 0.3),
                    cy + random.uniform(-self.h * 0.3, self.h * 0.3),
                )
            )
            self._particle_timer = random.uniform(*self._PARTICLE_INTERVAL)
        parts = self._particles
        for i in range(len(parts) - 1, -1, -1):
            parts[i].update(dt)
            if parts[i].dead:
                parts.pop(i)

    def _update_trail(self, dt: float) -> None:
        """Decai os fantasmas existentes; emite novos só durante o dash."""
        ai = self._afterimages
        for i in range(len(ai) - 1, -1, -1):
            ai[i]["life"] -= dt
            if ai[i]["life"] <= 0.0:
                ai.pop(i)
        if not self.attacking:
            return
        self._trail_timer -= dt
        if self._trail_timer <= 0.0:
            cx, cy = self.center
            ai.append(
                {"cx": cx, "cy": cy, "rot": self._render_angle(), "life": self._TRAIL_LIFETIME}
            )
            self._trail_timer = self._TRAIL_INTERVAL

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
        """Instancia cacos `IceShard` **cosméticos** herdando a direção da quebra.

        A direção base é o vetor radial para fora do núcleo (`orbit_angle`), com
        pequenas variações de ângulo/velocidade por caco. Sprites e tamanho são
        sorteados pelo próprio `IceShard` (content-driven). Os cacos NÃO causam
        dano nem colidem — são puramente visuais (ver `IceShard`)."""
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
            # Cacos visuais saem no `on_remove` (lista cosmética), não pelo canal
            # de `fragments` — assim a quebra não vira ameaça de gameplay.
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=28,
                sound=hit_sounds.EXPLOSION_ASTEROID,
            )
        return HitResult(explosion_size=8, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        # Armadura sólida: machuca a nave (o dano à nave é aplicado pelo
        # dispatcher de colisão) mas a rocha **não** é destruída pelo contato.
        from ..systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead

    def on_remove(self, entity_manager: Any) -> None:
        """Ao ser removida (morta por tiro ou estilhaçada pela gema), solta os
        cacos visuais na lista cosmética do EntityManager — sem dano/colisão."""
        entity_manager.ice_shards.extend(self.make_shards())

    def draw(self, surface: pygame.Surface) -> None:
        # Poeira mineral desenhada atrás da rocha (detalhe sutil de massa).
        for p in self._particles:
            p.draw(surface)

        sprite = self._sprites.get(self.corner)
        cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
        # Antecipação: tremor crescente telegrafando o disparo iminente. Usa o
        # acumulador `_windup_t` (alimentado pelo update), seguro a pausa/slow-mo.
        if self.winding_up:
            k = self._windup_t / self.WINDUP_DURATION
            amp = self.WINDUP_SHAKE_AMP * (0.4 + 0.6 * k)
            cx += int(math.sin(self._windup_t * self.WINDUP_SHAKE_FREQ) * amp)
            cy += int(math.cos(self._windup_t * self.WINDUP_SHAKE_FREQ * 1.3) * amp * 0.7)
        if sprite is not None:
            # Rastro fantasmagórico (Alucard) durante o dash: imagens residuais
            # com alpha decrescente, mesma técnica do SerpentRockBullet.
            for ai in self._afterimages:
                ghost = pygame.transform.rotate(sprite, ai["rot"])
                ghost.set_alpha(
                    int((ai["life"] / self._TRAIL_LIFETIME) * self._TRAIL_MAX_ALPHA)
                )
                surface.blit(
                    ghost,
                    ghost.get_rect(center=(int(ai["cx"]), int(ai["cy"]))).topleft,
                )

            # A peça de canto mantém a face interna apontada para o núcleo
            # (giro da formação) somada ao giro próprio da rocha.
            img = pygame.transform.rotate(sprite, self._render_angle())
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

    # Núcleo estrutural e persistente: nunca ceifado pela regra de "fora da tela"
    # do EntityManager (§5: gate por class attribute, lido via getattr).
    offscreen_cull_exempt = True

    # Tamanho do alvo (a gema). Pequeno de propósito: é o ponto fraco focado.
    GEM_SIZE = 42
    SPRITE_TARGET = 54  # sprite desenhado um pouco maior que o hitbox
    # `W`/`H`: contrato de tamanho lido pelo spawner (`_entry_position`).
    W = GEM_SIZE
    H = GEM_SIZE

    MOVE_SPEED = 46.0

    CORE_HEALTH = 220

    # Órbita
    BASE_ORBIT_DISTANCE = 82.0
    EXPANDED_ORBIT_DISTANCE = 188.0
    SPIN_CLOSED = 1.1  # rad/s
    SPIN_EXPANSION = 2.6  # rad/s

    # Fases
    PHASE_CLOSED_DURATION = 3.5
    EXPANSION_DURATION = 4.5
    BOOMERANG_STAGGER = 0.85  # intervalo entre disparos individuais

    # Reconstrução da armadura: se a gema ficar sem nenhuma rocha viva por este
    # tempo, novas rochas surgem de fora (pela base) e convergem para a órbita.
    REBUILD_DELAY = 10.0  # s sem rochas até disparar a reconstrução
    REBUILD_ENTRY_MARGIN = 70.0  # px abaixo do rodapé onde as rochas nascem
    REBUILD_ENTRY_STAGGER = 46.0  # px de escalonamento vertical na entrada

    # Animação da gema
    NUM_GEM_FRAMES = 8
    GEM_ANIM_FPS = 7.0

    # Tremor de impacto: feedback forte quando o jogador acerta o ponto fraco.
    # Curto e perceptível, sem comprometer a leitura do combate.
    GEM_SHAKE_DURATION = 0.18  # s
    GEM_SHAKE_AMPLITUDE = 6.0  # px
    GEM_SHAKE_FREQ = 60.0  # rad/s

    # --- Nascimento (3 fases; a gema NÃO existe até a ruptura) ---------------
    # A entrada é teatral: a gema parece ser *criada* pela energia acumulada, não
    # estar lá desde o início. Três fases encadeadas:
    #   1. ENERGY      — círculo de energia pequeno cresce, pulsa ritmadamente,
    #                    intensifica e emite partículas azuis cristalinas
    #                    convergindo (acúmulo). Sem cristal visível.
    #   2. INSTABILITY — pico de energia: pulsos mais rápidos, brilho maior, o
    #                    círculo oscila e vazamentos de energia escapam para fora.
    #   3. RUPTURE     — ruptura: o círculo COLAPSA para dentro (energia condensa
    #                    num ponto); só então a gema surge já formada, com um
    #                    breve clarão/pulso. Depois disso → invocação das rochas.
    # Durações ajustadas à janela do SFX de nascimento (~1.74s): a soma fica
    # logo abaixo disso para a ruptura/revelação da gema cair junto ao clímax do
    # áudio (sem o visual se estender além do som — evita dessincronização).
    BIRTH_ENERGY_DURATION = 0.9  # s de crescimento + pulsação (acúmulo)
    BIRTH_INSTABILITY_DURATION = 0.5  # s de instabilidade no pico
    BIRTH_RUPTURE_DURATION = 0.3  # s de condensação + nascimento da gema
    BIRTH_CIRCLE_RADIUS = 80.0  # px: raio máximo do círculo no pico

    # --- Colapso do núcleo (estado crítico antes da explosão) ---------------
    # Ao zerar a vida, a gema NÃO explode na hora: entra em colapso — treme cada
    # vez mais forte/rápido, vai ficando branca e brilhante, e deixa escapar
    # pulsos de energia. Só ao fim da duração o cristal estoura de fato.
    COLLAPSE_DURATION = 1.15  # s do estado crítico até a explosão
    COLLAPSE_PULSE_INTERVAL = (0.03, 0.08)  # s entre pulsos de energia que escapam

    # Explosão de morte: proporcional ao tamanho real do inimigo (a gema é o
    # ponto fraco focado, não um miniboss). Reduzida de um valor exagerado.
    DEATH_EXPLOSION_SIZE = 52
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

        self.w = self.GEM_SIZE
        self.h = self.GEM_SIZE

        # Nascimento: a gema se FORMA in loco a partir de um círculo de energia
        # (não entra deslizando da borda nem cai do topo). A posição de
        # nascimento é forçada para DENTRO da tela, com folga para o círculo de
        # energia caber inteiro. Sem isso, em fases side-scroll a posição de
        # entrada vem fora da borda direita (x = SCREEN_WIDTH + ...) e TODO o
        # nascimento aconteceria fora de tela — a gema só "apareceria" já formada
        # ao entrar no quadro (o bug do canto superior direito).
        self.target_y = float(random.randint(100, 165))
        self.y = self.target_y
        self.side_scroll = side_scroll
        _r = self.BIRTH_CIRCLE_RADIUS
        _lo = _r
        _hi = max(_lo, Config.SCREEN_WIDTH - self.w - _r)
        self.x = min(max(float(x), _lo), _hi)
        self._birth_t = 0.0  # tempo decorrido na sequência de nascimento
        self._born = False  # True após o estouro revelar a gema (operacional)
        self._birth_sound_played = False  # som de nascimento tocado uma vez

        # Saúde / estado
        self.dead = False
        self.core_health = self.CORE_HEALTH
        self.hit_timer = 0.0
        self.shake_timer = 0.0  # tremor de impacto ao receber dano efetivo
        self.active = True
        self._deflect = False  # último hit foi defletido pela armadura?

        # Colapso do núcleo: estado crítico entre "vida zerou" e a explosão.
        self.collapsing = False
        self._collapse_t = 0.0
        self._collapse_pulse_timer = 0.0

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

        # Reconstrução: conta o tempo desde que ficou sem rochas vivas.
        self._rebuild_timer = self.REBUILD_DELAY

        # Faíscas de energia azul emitidas durante o nascimento/reconstrução
        # (gema "atraindo" os fragmentos). Cosmético — ver `_update_energy_motes`.
        self._energy_motes: List[_GemEnergyMote] = []
        self._mote_timer = 0.0
        # Vazamentos de energia para fora durante a instabilidade do nascimento.
        self._leak_timer = 0.0

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

    # Cantos do quadrado em screen-space (y para baixo): slot -> ângulo (rad).
    _FRAGMENT_SLOTS = (
        ("tl", 5 * math.pi / 4),  # superior-esquerdo
        ("tr", 7 * math.pi / 4),  # superior-direito
        ("br", math.pi / 4),  # inferior-direito
        ("bl", 3 * math.pi / 4),  # inferior-esquerdo
    )

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if self.collapsing:
            # Núcleo em colapso: avança o estado crítico (pulsos de energia) e,
            # ao fim, dispara a explosão (precisa do ctx p/ explosão e cacos).
            self._advance_collapse(ctx)
            return
        if not self._fragments_spawned:
            # Nascimento: primeiro o círculo de energia se forma e estoura,
            # revelando a gema (`_born`). SÓ ENTÃO as rochas são invocadas —
            # emergem de baixo e convergem para a órbita, reutilizando a lógica
            # da reconstrução da armadura (§11). Sequência: energia → nascimento
            # da gema → reconstrução.
            if self._born:
                self._assemble_fragments(ctx)
                self._fragments_spawned = True
        else:
            self._update_rebuild(ctx)

    def _update_rebuild(self, ctx: "EnemyUpdateContext") -> None:
        """Reconstrói a armadura se a gema passar `REBUILD_DELAY` sem rochas.

        Enquanto houver rocha viva, o timer permanece cheio. Esgotado, dispara a
        mesma montagem do nascimento: rochas surgem fora da tela (pela base) e
        convergem para a órbita (`entering`), reformando a proteção mineral.
        """
        if self.dead:
            return
        if self.live_fragments:
            self._rebuild_timer = self.REBUILD_DELAY
            return
        self._rebuild_timer -= ctx.sdt
        if self._rebuild_timer <= 0.0:
            self._assemble_fragments(ctx)
            self._rebuild_timer = self.REBUILD_DELAY

    def _assemble_fragments(self, ctx: "EnemyUpdateContext") -> None:
        """Faz 4 rochas nascerem abaixo do rodapé e convergirem para a órbita.

        Serve tanto ao **nascimento** (montagem inicial da relíquia) quanto à
        **reconstrução** da armadura após destruição — mesma coreografia.
        """
        # Descarta as carcaças mortas de um ciclo anterior (one-shot, fora do hot
        # path: comprehension de rebuild é aceitável — §6). No nascimento a lista
        # já está vazia, então é no-op.
        self.fragments = [f for f in self.fragments if not f.dead]
        cx, _ = self.center
        base_y = Config.SCREEN_HEIGHT + self.REBUILD_ENTRY_MARGIN
        for i, (corner, ang) in enumerate(self._FRAGMENT_SLOTS):
            frag = IceGolemFragment(corner, ang, entering=True)
            # Nasce fora da tela, escalonado em x/y para emergir em fila.
            frag.x = cx - frag.w / 2 + (i - 1.5) * frag.w * 0.6
            frag.y = base_y + i * self.REBUILD_ENTRY_STAGGER
            self.fragments.append(frag)
            ctx.new_enemies.append(frag)
        # Escreve já o alvo de órbita para a convergência começar neste frame.
        self._position_fragments()

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        self.anim_time += dt
        self.anim_phase += self.GEM_ANIM_FPS * dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - dt)

        # Faíscas de energia (nascimento/reconstrução) — convergem para o centro
        # vivo da gema, sinalizando que ela está "chamando/acumulando" energia.
        self._update_energy_motes(dt)

        if self.collapsing:
            # Núcleo crítico: congela o combate (sem mover/girar). O tremor, o
            # branqueamento e o brilho crescente ficam no draw; os pulsos de
            # energia que escapam são emitidos em `_advance_collapse`. Mantém só
            # uma flutuação tênue para o cristal não parecer "morto" cedo demais.
            self.y = self.target_y + math.sin(self.anim_time + self.bob_phase) * 2.0
            return

        if not self._born:
            # Nascimento: o círculo de energia cresce e estoura (visual no draw);
            # aqui só avança o relógio até revelar a gema.
            self._update_birth(dt)
            return

        # Movimento lateral lento perseguindo o jogador.
        cx, _ = self.center
        dx = player_x - cx
        if abs(dx) > 4.0:
            self.x += math.copysign(self.MOVE_SPEED * dt, dx)
        self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
        # Flutuação cosmética vertical.
        self.y = self.target_y + math.sin(self.anim_time + self.bob_phase) * 4.0

        if self._is_rebuilding():
            # Armadura reformando: a gema suspende os ataques e gira devagar na
            # formação fechada até as rochas reassumirem a órbita. Mantém o
            # núcleo exposto durante a reconstrução (janela de pressão) e evita
            # perseguir um alvo orbital mais rápido que a velocidade de entrada.
            self.phase = IceGolemPhase.FORMATION_CLOSED
            self.phase_timer = self.PHASE_CLOSED_DURATION
        else:
            self._update_phase(dt, player_x, player_y)
        self._update_spin_and_orbit(dt)
        self._position_fragments()

    def _birth_total(self) -> float:
        """Duração total do nascimento (soma das 3 fases)."""
        return (
            self.BIRTH_ENERGY_DURATION
            + self.BIRTH_INSTABILITY_DURATION
            + self.BIRTH_RUPTURE_DURATION
        )

    def _birth_phase(self) -> str:
        """Fase atual do nascimento: 'energy' | 'instability' | 'rupture'."""
        t = self._birth_t
        if t < self.BIRTH_ENERGY_DURATION:
            return "energy"
        if t < self.BIRTH_ENERGY_DURATION + self.BIRTH_INSTABILITY_DURATION:
            return "instability"
        return "rupture"

    def _birth_circle_radius(self) -> float:
        """Raio do círculo de energia agora: cresce → estável → condensa a 0."""
        t = self._birth_t
        e = self.BIRTH_ENERGY_DURATION
        i = self.BIRTH_INSTABILITY_DURATION
        if t < e:  # crescimento acelerado a partir do pequeno
            p = t / e
            return self.BIRTH_CIRCLE_RADIUS * (p * p)
        if t < e + i:  # estável no pico (a pulsação fica no draw)
            return self.BIRTH_CIRCLE_RADIUS
        # ruptura: condensa para o centro (fica em ~0 antes da gema surgir)
        rp = (t - (e + i)) / self.BIRTH_RUPTURE_DURATION
        return self.BIRTH_CIRCLE_RADIUS * max(0.0, 1.0 - rp / 0.6)

    def _update_birth(self, dt: float) -> None:
        """Avança o nascimento e emite as partículas de energia de cada fase.

        Sequência: crescimento/pulsação (energy) → instabilidade (instability,
        com vazamentos para fora) → ruptura/condensação (rupture). A gema só é
        revelada no draw, durante a ruptura; aqui só roda o relógio e as
        partículas. Sem cristal visível antes da ruptura.
        """
        # Som de nascimento — uma vez, no início da sequência (círculo surgindo).
        if not self._birth_sound_played:
            from ..systems import hit_sounds

            hit_sounds.GEM_BIRTH()
            self._birth_sound_played = True

        self._birth_t += dt
        if self._birth_t >= self._birth_total():
            self._born = True
            return

        cx, cy = self.center
        phase = self._birth_phase()

        if phase != "rupture":
            # Partículas azuis cristalinas convergindo (acúmulo de energia). A
            # densidade acelera no pico (instabilidade).
            accel = 1.0 if phase == "energy" else 2.3
            self._mote_timer -= dt
            if self._mote_timer <= 0.0:
                ring_r = max(self.GEM_SIZE * 0.5, self._birth_circle_radius())
                ang = random.uniform(0.0, math.tau)
                radius = ring_r * random.uniform(0.85, 1.25)
                self._energy_motes.append(
                    _GemEnergyMote(
                        cx, cy, ang, radius, crystalline=random.random() < 0.55
                    )
                )
                self._mote_timer = random.uniform(0.03, 0.07) / accel

            # Instabilidade: vazamentos de energia escapando para fora.
            if phase == "instability":
                self._leak_timer -= dt
                if self._leak_timer <= 0.0:
                    ang = random.uniform(0.0, math.tau)
                    self._energy_motes.append(
                        _GemEnergyMote(
                            cx, cy, ang, self.GEM_SIZE * 0.35,
                            homing=False, crystalline=random.random() < 0.4,
                        )
                    )
                    self._leak_timer = random.uniform(0.05, 0.12)

        # Flutuação tênue (a oscilação visível da instabilidade fica no draw).
        self.y = self.target_y + math.sin(self.anim_time + self.bob_phase) * 2.0

    def _advance_collapse(self, ctx: "EnemyUpdateContext") -> None:
        """Avança o estado crítico e, ao fim, faz o cristal estourar.

        Durante o colapso escapam pulsos de energia do núcleo (faíscas azuis
        para fora). A frequência da tremedeira e o branqueamento crescem no draw
        conforme `_collapse_t`. Esgotada a duração, a gema explode de fato:
        explosão azul-cristalina + cacos da gema + estilhaços das rochas vivas.
        """
        self._collapse_t += ctx.sdt

        # Pulsos de energia que escapam do núcleo (faíscas para fora).
        self._collapse_pulse_timer -= ctx.sdt
        if self._collapse_pulse_timer <= 0.0:
            cx, cy = self.center
            ang = random.uniform(0.0, math.tau)
            self._energy_motes.append(
                _GemEnergyMote(cx, cy, ang, self.GEM_SIZE * 0.25, homing=False)
            )
            self._collapse_pulse_timer = random.uniform(*self.COLLAPSE_PULSE_INTERVAL)

        if self._collapse_t >= self.COLLAPSE_DURATION:
            self._explode(ctx)

    def _explode(self, ctx: "EnemyUpdateContext") -> None:
        """Explosão final do núcleo (morte no update, sem `on_hit` — como o
        Tesla Twin): explosão azul-cristalina proporcional + som.

        Os cacos (gema e rochas) são puramente visuais e saem via `on_remove`:
        a gema solta os seus, e cada rocha restante é marcada morta para que o
        próprio `on_remove` dela solte os cacos na lista cosmética — sem dano."""
        from ..systems import hit_sounds

        self.dead = True
        cx, cy = self.center
        # Explosão azul-cristalina (paleta ICE_CORE), tamanho proporcional.
        ctx.new_explosions.append(
            (cx, cy, self.DEATH_EXPLOSION_SIZE, ExplosionType.ICE_CORE)
        )
        # Rochas que ainda restavam estilhaçam junto: marca-as mortas — o
        # `on_remove` de cada uma cria os cacos visuais (parente coordena — §1).
        for frag in self.fragments:
            frag.dead = True
        # Explosão FÍSICA da entidade: som de explosão padrão (não o GEM_DEATH,
        # que é o colapso energético e já tocou no início do estado crítico).
        hit_sounds.EXPLOSION_ASTEROID()

    def make_gem_shards(self) -> tuple:
        """Cacos **visuais** do núcleo (`IceGemShard`) em todas as direções.

        Saem do centro visual da gema em ângulos espalhados, reforçando a
        sensação de que o cristal central se despedaçou. Sem dano/colisão."""
        cx, cy = self.center
        count = random.randint(7, 10)
        shards = []
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            speed = random.uniform(140.0, 280.0)
            shards.append(
                IceGemShard(cx, cy, math.cos(ang) * speed, math.sin(ang) * speed)
            )
        return tuple(shards)

    def on_remove(self, entity_manager: Any) -> None:
        """Ao ser removida (após o colapso/explosão), solta os cacos visuais do
        núcleo na lista cosmética do EntityManager — sem dano/colisão."""
        entity_manager.ice_shards.extend(self.make_gem_shards())

    def _is_rebuilding(self) -> bool:
        """True enquanto alguma rocha ainda converge para a formação."""
        return any(f.entering for f in self.fragments if not f.dead)

    def _update_energy_motes(self, dt: float) -> None:
        """Atualiza as faíscas azuis e emite atração enquanto rochas convergem.

        As faíscas perseguem o **centro vivo** da gema a cada frame — por isso
        `update` recebe `cx, cy`: garante que terminem exatamente no centro
        visual do cristal mesmo com a gema flutuando. A emissão aqui cobre a
        montagem/reconstrução da armadura (rochas `entering`); o **nascimento**
        emite as suas próprias partículas em `_update_birth`.
        """
        cx, cy = self.center
        motes = self._energy_motes
        for i in range(len(motes) - 1, -1, -1):
            motes[i].update(dt, cx, cy)
            if motes[i].dead:
                motes.pop(i)
        if not self._is_rebuilding():
            return
        self._mote_timer -= dt
        if self._mote_timer <= 0.0:
            ang = random.uniform(0.0, math.tau)
            radius = random.uniform(self.GEM_SIZE * 0.7, self.orbit_distance + self.GEM_SIZE)
            motes.append(_GemEnergyMote(cx, cy, ang, radius))
            self._mote_timer = random.uniform(0.04, 0.10)

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

        # Ciclo completo: ninguém na fila e ninguém mais atacando nem em
        # antecipação (senão a expansão começaria antes do último dash sair).
        cycle_done = not self._boom_pending and not any(
            f.attacking or f.winding_up for f in self.live_fragments
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
        # Rochas atacando OU ainda convergindo (reconstrução) não protegem o
        # núcleo — a janela continua aberta até a armadura reformar de fato.
        missing = (4 - n) / 4.0
        away = sum(1 for f in live if f.attacking or f.entering) / 4.0
        return min(1.0, 0.10 + 0.45 * missing + 0.25 * away)

    def take_damage(self, amount: int) -> None:
        self.core_health -= amount
        self.hit_timer = 0.1
        # Dano efetivo (chegou à gema): tremor de impacto para sinalizar o acerto
        # no ponto fraco. Deflexão não chama take_damage, então não treme.
        self.shake_timer = self.GEM_SHAKE_DURATION
        # A morte NÃO é imediata: ao zerar a vida a gema entra em colapso
        # (ver on_hit/_begin_collapse). take_damage por si só não marca `dead`.

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        # Núcleo ainda nascendo (círculo de energia) ou já em colapso:
        # invulnerável, só centelha como feedback. O golpe fatal já registrou a
        # morte e a explosão é resolvida pelo colapso — não reprocessa dano.
        if not self._born or self.collapsing:
            return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)

        vuln = self._gem_vulnerability()
        effective = int(round(damage * vuln))

        if effective <= 0:
            # Tiro ricocheteia na armadura — feedback claro, sem perda de HP.
            self._deflect = True
            self.hit_timer = 0.06
            return HitResult(explosion_size=6, sound=hit_sounds.BOSS_DAMAGE)

        self._deflect = False
        self.take_damage(effective)
        if self.core_health <= 0:
            return self._begin_collapse()
        return HitResult(explosion_size=12, sound=hit_sounds.BOSS_DAMAGE)

    def _begin_collapse(self) -> "HitResult":
        """Golpe fatal: entra no estado crítico (colapso) em vez de explodir já.

        Registra a morte (pontos/score/evento) no próprio golpe fatal, mas a
        entidade segue viva (`dead = False`, logo não é removida) tremendo e
        branqueando por `COLLAPSE_DURATION`. A explosão azul-cristalina, os cacos
        da gema e o estilhaçar das rochas saem depois, em `_explode` (no update).
        """
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.collapsing = True
        self.dead = False
        self._collapse_t = 0.0
        self._collapse_pulse_timer = 0.0
        # Som de morte/colapso: energia do núcleo desabando, acompanha todo o
        # estado crítico até a explosão final (que tem seu próprio som em _explode).
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=14,
            explosion_type=ExplosionType.ICE_CORE,
            sound=hit_sounds.GEM_DEATH,
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
        # Centro visual exato do cristal (fonte única, igual ao das partículas).
        cx, cy = int(self.center[0]), int(self.center[1])

        # Nascimento: círculo de energia → estouro revelando a gema (sem a gema
        # plena ainda). Sai antes de qualquer halo/escudo de combate.
        if not self._born:
            self._draw_birth(surface, cx, cy)
            return

        # Colapso do núcleo: treme cada vez mais, branqueia e brilha.
        if self.collapsing:
            self._draw_collapse(surface, cx, cy)
            return

        # Tremor de impacto: deslocamento curto e decrescente quando a gema leva
        # dano efetivo. Usa o acumulador `anim_time` (não time.time()), seguro a
        # pausa/slow-motion; §3: draw lê estado, quem decai é o update.
        if self.shake_timer > 0.0:
            k = self.shake_timer / self.GEM_SHAKE_DURATION
            cx += int(
                math.sin(self.anim_time * self.GEM_SHAKE_FREQ) * self.GEM_SHAKE_AMPLITUDE * k
            )
            cy += int(
                math.cos(self.anim_time * self.GEM_SHAKE_FREQ * 1.3)
                * self.GEM_SHAKE_AMPLITUDE
                * 0.6
                * k
            )

        vuln = self._gem_vulnerability()

        # Brilho energético único ao redor da gema — consolida o antigo halo de
        # exposição + o anel de escudo num só efeito: um círculo preenchido e
        # suave, sem bordas (mais glow do que escudo tradicional). Cresce e
        # intensifica quando a gema está exposta (leitura da janela de ataque) e
        # fica mais contido/suave quando protegida; pulsa de leve sempre.
        glow_r = int(self.GEM_SIZE * (0.85 + 0.55 * vuln))
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * (4.0 if vuln > 0.4 else 6.0))
        glow_a = int((45 + 80 * vuln) * (0.7 + 0.3 * pulse))
        self._draw_soft_glow(surface, cx, cy, glow_r, (120, 215, 255), glow_a)

        # Faíscas de energia convergindo para o núcleo (montagem da formação).
        for mote in self._energy_motes:
            mote.draw(surface)

        self._draw_gem(surface, cx, cy, vuln)

    @staticmethod
    def _draw_soft_glow(
        surface: pygame.Surface,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
        max_alpha: int,
        steps: int = 6,
    ) -> None:
        """Glow radial macio, sem borda visível: círculos concêntricos do mais
        largo/fraco ao mais estreito/forte formam um degradê suave (centro
        brilhante esmaecendo para fora)."""
        if radius <= 0 or max_alpha <= 0:
            return
        glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        r, g, b = color
        for i in range(steps, 0, -1):
            rr = int(radius * i / steps)
            a = max(0, min(255, int(max_alpha * (1.0 - (i - 1) / steps))))
            pygame.draw.circle(glow, (r, g, b, a), (radius, radius), rr)
        surface.blit(glow, (cx - radius, cy - radius))

    def _draw_birth(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        """Nascimento em 3 estágios — a gema só aparece na ruptura.

        energy: círculo cresce, pulsa ritmado e intensifica.
        instability: pulsos rápidos, mais brilho, o círculo oscila.
        rupture: o círculo condensa para o centro; aí a gema surge já formada,
        com um breve clarão/pulso.
        """
        phase = self._birth_phase()

        # Oscilação visível do círculo só na instabilidade.
        ox = oy = 0
        if phase == "instability":
            ip = (self._birth_t - self.BIRTH_ENERGY_DURATION) / self.BIRTH_INSTABILITY_DURATION
            wob = 2.0 + 4.5 * ip
            ox = int(math.sin(self.anim_time * 42.0) * wob)
            oy = int(math.cos(self.anim_time * 47.0) * wob)
        ccx, ccy = cx + ox, cy + oy

        # Partículas de energia (atração + vazamentos) atrás do círculo.
        for mote in self._energy_motes:
            mote.draw(surface)

        if phase in ("energy", "instability"):
            # Intensidade global sobe ao longo de energy+instability.
            pre = self.BIRTH_ENERGY_DURATION + self.BIRTH_INSTABILITY_DURATION
            glob = min(1.0, self._birth_t / pre)
            unstable = phase == "instability"

            r = max(2, int(self._birth_circle_radius()))
            pulse_freq = 9.0 if not unstable else 24.0  # pulsos mais rápidos no pico
            pulse = 0.85 + 0.15 * math.sin(self.anim_time * pulse_freq)
            rr = max(2, int(r * pulse))
            glow = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
            core_a = min(235, int(35 + 175 * glob))
            pygame.draw.circle(glow, (150, 225, 255, core_a), (rr, rr), rr)
            pygame.draw.circle(
                glow, (225, 245, 255, min(255, core_a + 50)),
                (rr, rr), max(1, int(rr * 0.42)),
            )
            surface.blit(glow, (ccx - rr, ccy - rr))

            # Anéis de luz emanando para fora (mais rápidos/brilhantes no pico).
            ring_speed = 1.4 if not unstable else 2.8
            ring_a = 150 if not unstable else 185
            for k in range(3):
                rphase = (self.anim_time * ring_speed + k / 3.0) % 1.0
                rad = int(self.BIRTH_CIRCLE_RADIUS * (0.3 + 0.95 * rphase) * (0.4 + 0.6 * glob))
                a = int(ring_a * (1.0 - rphase) * glob)
                if a > 0 and rad > 1:
                    ring = pygame.Surface((rad * 2 + 2, rad * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(ring, (130, 220, 255, a), (rad + 1, rad + 1), rad, 2)
                    surface.blit(ring, (ccx - rad - 1, ccy - rad - 1))
        else:
            # Ruptura: o círculo condensa para o centro (anel encolhendo); ao
            # condensar, um breve clarão e a gema surge já formada.
            rp = (self._birth_t - (self.BIRTH_ENERGY_DURATION + self.BIRTH_INSTABILITY_DURATION)) \
                / self.BIRTH_RUPTURE_DURATION
            condense = max(0.0, 1.0 - rp / 0.6)
            if condense > 0.0:
                rr = max(1, int(self.BIRTH_CIRCLE_RADIUS * condense))
                a = min(255, int(210 * condense + 30))
                ring = pygame.Surface((rr * 2 + 2, rr * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(ring, (180, 235, 255, a), (rr + 1, rr + 1), rr, 3)
                surface.blit(ring, (cx - rr - 1, cy - rr - 1))

            # Gema surgindo já formada (fade-in rápido) + clarão de nascimento.
            reveal = max(0.0, min(1.0, (rp - 0.35) / 0.65))
            if reveal > 0.0:
                fp = 1.0 - reveal  # clarão mais forte no instante do surgimento
                flash_r = int(self.GEM_SIZE * (0.7 + 0.9 * fp) + 6)
                fa = int(205 * fp)
                if fa > 0 and flash_r > 0:
                    flash = pygame.Surface((flash_r * 2, flash_r * 2), pygame.SRCALPHA)
                    pygame.draw.circle(flash, (235, 250, 255, fa), (flash_r, flash_r), flash_r)
                    surface.blit(flash, (cx - flash_r, cy - flash_r))
                self._draw_gem(surface, cx, cy, 0.0, reveal=reveal)

    def _draw_collapse(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        """Estado crítico: a tremedeira (amplitude e frequência) e o brilho
        branco crescem com o avanço; pulsos de energia escapam do núcleo."""
        cp = min(1.0, self._collapse_t / self.COLLAPSE_DURATION)

        # Tremedeira progressiva: amplitude e frequência sobem com o colapso.
        amp = self.GEM_SHAKE_AMPLITUDE * (0.5 + 2.0 * cp)
        freq = self.GEM_SHAKE_FREQ * (0.8 + 2.2 * cp)
        cx += int(math.sin(self.anim_time * freq) * amp)
        cy += int(math.cos(self.anim_time * freq * 1.3) * amp * 0.7)

        # Brilho crescente: halo branco-gelo inchando conforme o núcleo satura.
        halo = int(self.GEM_SIZE * (0.7 + 1.3 * cp))
        glow = pygame.Surface((halo * 2, halo * 2), pygame.SRCALPHA)
        a = int(60 + 150 * cp + 30 * math.sin(self.anim_time * 22.0))
        col = (int(150 + 105 * cp), int(225 + 30 * cp), 255, max(0, min(235, a)))
        pygame.draw.circle(glow, col, (halo, halo), halo)
        surface.blit(glow, (cx - halo, cy - halo))

        # Pulsos de energia escapando (faíscas para fora) por cima do halo.
        for mote in self._energy_motes:
            mote.draw(surface)

        # A gema vai ficando cada vez mais branca e instável (white = cp).
        self._draw_gem(surface, cx, cy, 1.0, white=cp)

    def _draw_gem(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        vuln: float,
        reveal: float = 1.0,
        white: float = 0.0,
    ) -> None:
        """Desenha o cristal centrado em (cx, cy).

        `reveal` (<1): pop de escala + alpha ao surgir do estouro do nascimento.
        `white` (>0): branqueamento progressivo do núcleo durante o colapso.
        """
        frames = self._gem_frames
        if frames:
            frame = frames[int(self.anim_phase) % len(frames)]
            copied = False
            if self.hit_timer > 0.0:
                frame = frame.copy()
                copied = True
                tint = colors.WHITE if not self._deflect else (120, 200, 255)
                frame.fill(tint, special_flags=pygame.BLEND_RGB_ADD)
            if white > 0.0:
                if not copied:
                    frame = frame.copy()
                    copied = True
                w = int(210 * white)
                frame.fill((w, w, w), special_flags=pygame.BLEND_RGB_ADD)
            if reveal < 1.0:
                # A gema surge JÁ FORMADA (escala quase cheia, só um leve assentar)
                # com fade-in rápido. rotozoom devolve nova surface (original
                # intacta); como o sprite tem alpha por pixel, esmaece via
                # BLEND_RGBA_MULT.
                scale = max(0.05, 0.82 + 0.18 * reveal)
                frame = pygame.transform.rotozoom(frame, 0.0, scale)
                alpha = max(0, min(255, int(255 * reveal)))
                frame.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(frame, frame.get_rect(center=(cx, cy)).topleft)
            return

        # Fallback procedural se a arte não carregou.
        gem_color = (int(100 + 120 * vuln), int(180 + 60 * vuln), 255)
        pygame.draw.circle(surface, gem_color, (cx, cy), self.GEM_SIZE // 2)
        pygame.draw.circle(surface, (200, 235, 255), (cx, cy), self.GEM_SIZE // 2, 2)


# Registra para o preload de sprites (mesma convenção do StoneEagle/Satellite).
sprite_loader.register("IceGolem", _load_ice_golem_sprites)
