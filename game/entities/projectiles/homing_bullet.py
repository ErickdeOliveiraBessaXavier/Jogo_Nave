import math
import random
from typing import Any, Iterable

import pygame

from ...core.assets import BASE_DIR, get_image
from ...core.config import config as Config
from ...core.player_tint import P2_SHOT_HUE_SHIFT, hue_shifted, player_shot_color
from ...core.sprite_loader import sprite_loader
from ...systems.targeting import is_huntable, target_point

# --- Arte do tiro ESPECIAL CARREGADO do Caçador ------------------------------
# 3 frames de 12x12 (losango de energia com faíscas nos quatro cantos). Não
# confundir com `bullet_fx/homing.py`, que é o '+' do MODIFICADOR teleguiado do
# tiro comum — este módulo é só o projétil do charge shot.
_SPRITE_DIR = BASE_DIR / "assets" / "images" / "Tiro_Especial_Nave_Caçador_Carregado"
_SPRITE_FILES = (
    "Caçador_Tiro_Especial_01.png",
    "Caçador_Tiro_Especial_02.png",
    "Caçador_Tiro_Especial_03.png",
)

# Sprite OPCIONAL do estouro, usado no clarão final da sobrecarga. Se o arquivo
# não existir, o núcleo já branco e inchado da própria sobrecarga faz o papel —
# é por isso que a ausência não é warning: o efeito fecha inteiro sem ele.
_FLASH_FILE = "Caçador_Tiro_Especial_Estouro.png"

# A arte nasce em 12x12, perto demais do hitbox de 10px para o tiro CARREGADO
# se distinguir do comum em campo. Dobrar dá presença de "especial" sem redesenhar
# nada. Fator INTEIRO de propósito: `transform.scale` é nearest-neighbor, então
# 2x replica cada pixel exato — em 1,5x a grade quebra e o pixel art borra.
_SPRITE_SCALE: int = 2

# 3 frames a 14fps ≈ 4,7 pulsos/s: lê como energia instável sem virar
# estroboscópio numa sprite pequena.
_ANIM_FPS: float = 14.0

# --- Giro em voo -------------------------------------------------------------
# Graus/s do rodopio constante. O giro é o que separa este projétil do tiro
# comum a um relance: ele não aponta para onde vai, ele ROLA até o alvo.
_ROT_SPEED: float = 420.0

# Passos do cache de pré-rotação (15° cada). Mesma escolha do '+' teleguiado
# (`bullet_fx/homing.py`): a 420°/s um passo dura ~2 frames a 60fps, abaixo do
# que o olho lê como travado, e evita rotacionar por bala por frame (§7).
_ROT_STEPS: int = 24

# --- Sobrecarga (fim do tempo de vida sem acertar nada) ----------------------
# Curta de propósito: é o epílogo de um projétil que já falhou, não um evento.
# Longa demais, vira ruído visual em cima de uma rajada de 5.
_OVERLOAD_TIME: float = 0.55
_OVERLOAD_ROT_SPEED_MAX: float = 2400.0  # graus/s no instante do estouro
_OVERLOAD_SHAKE_MAX: float = 6.0         # amplitude do tremor, em px
_OVERLOAD_GROW_MAX: float = 0.55         # +55% de tamanho ao fim
_OVERLOAD_STRETCH_MAX: float = 0.28      # amplitude do estica-e-comprime
_OVERLOAD_STRETCH_HZ: float = 9.0        # pulsações/s do estiramento
_OVERLOAD_FLASH_AT: float = 0.85         # fração do tempo em que vira clarão

# Estouro em área. Raio menor que o do tiro explosivo (60px) porque isto é
# consolo de um tiro que não acertou ninguém, não uma ferramenta de dano — e o
# dano é o do próprio projétil, para não inventar um número de balanceamento.
_OVERLOAD_BLAST_RADIUS: float = 40.0
_OVERLOAD_BLAST_COLOR: tuple[int, int, int] = (120, 220, 255)

_frames_by_player: dict[int, list[pygame.Surface]] = {}
_flash_by_player: dict[int, pygame.Surface | None] = {}
# Pré-rotações memoizadas sob demanda, por (jogador, frame da animação, passo).
_rot_cache: dict[tuple[int, int, int], pygame.Surface] = {}


def _prepare(path, player_index: int) -> pygame.Surface:
    """PNG do disco na cor do jogador e na escala do projétil.

    O resultado é uma surface PRÓPRIA (`scale` e `hue_shifted` alocam novas, e a
    cópia explícita cobre o caso de escala 1 para o P1) — a do `get_image` é
    compartilhada com qualquer outro consumidor do mesmo arquivo, e transformar
    a compartilhada é a armadilha do buffer de fade (CLAUDE.md §17).
    """
    sprite = get_image(path)
    if player_index == 1:
        # Giro de TIRO (curto), não o de nave. `player_sprite` daria a
        # meia-volta do casco e levaria o núcleo azul do Caçador ao VERMELHO —
        # a cor do casco do P1, e o oposto do que a distinção entre jogadores
        # quer dizer. O giro curto separa os dois deixando o tiro na mesma
        # família de cor (ver `P2_SHOT_HUE_SHIFT`).
        sprite = hue_shifted(sprite, P2_SHOT_HUE_SHIFT)
    if _SPRITE_SCALE != 1:
        w, h = sprite.get_size()
        sprite = pygame.transform.scale(sprite, (w * _SPRITE_SCALE, h * _SPRITE_SCALE))
    else:
        sprite = sprite.copy()
    try:
        sprite = sprite.convert_alpha()
    except pygame.error:
        pass
    return sprite


def _get_frames(player_index: int) -> list[pygame.Surface]:
    """Frames do pulso na cor do jogador, memoizados por P1/P2.

    Lista vazia (arquivo ausente) é caso previsto: o `draw` cai no círculo.
    """
    frames = _frames_by_player.get(player_index)
    if frames is not None:
        return frames

    frames = [
        _prepare(path, player_index)
        for path in (_SPRITE_DIR / name for name in _SPRITE_FILES)
        if path.exists()
    ]
    _frames_by_player[player_index] = frames
    return frames


def _get_flash_frame(player_index: int) -> pygame.Surface | None:
    """Sprite do estouro, ou `None` se a arte dedicada não existe."""
    if player_index in _flash_by_player:
        return _flash_by_player[player_index]
    path = _SPRITE_DIR / _FLASH_FILE
    frame = _prepare(path, player_index) if path.exists() else None
    _flash_by_player[player_index] = frame
    return frame


def _rotated(player_index: int, anim_idx: int, angle: float) -> pygame.Surface:
    """Frame `anim_idx` girado em `angle`, quantizado e memoizado (§7).

    Só as combinações realmente usadas materializam surface — o cache cheio são
    `_ROT_STEPS` × 3 frames × 2 jogadores de ~34px, na casa das centenas de KB.
    """
    step = int(angle * _ROT_STEPS / 360.0) % _ROT_STEPS
    key = (player_index, anim_idx, step)
    cached = _rot_cache.get(key)
    if cached is None:
        base = _get_frames(player_index)[anim_idx]
        cached = pygame.transform.rotate(base, -step * (360.0 / _ROT_STEPS))
        try:
            cached = cached.convert_alpha()
        except pygame.error:
            pass
        _rot_cache[key] = cached
    return cached


def preload_sprites() -> None:
    """Carrega os frames dos dois jogadores no boot, fora do primeiro disparo."""
    for player_index in (0, 1):
        _get_frames(player_index)
        _get_flash_frame(player_index)


class HomingBullet:
    """Tiro teleguiado com vida consumível que é reduzida pelo dano causado.

    O projétil vive até gastar a vida acertando coisas (consume_life) ou sair da
    tela. Cada instância pode ter um alvo fixo (locked_target) para garantir que
    múltiplos projéteis simultâneos não persigam o mesmo inimigo.

    Esgotar o `lifetime` sem acertar nada NÃO é morte: entra em sobrecarga
    (`_update_overload`) — para, treme, gira cada vez mais rápido, incha e
    embranquece até estourar em área. Um tiro especial que simplesmente some é
    lido como bug de render; um que se desfaz em cima do jogador é lido como
    consequência. Quem materializa o estouro é o `EntityManager`, via
    `take_pending_blast`.

    Interfaces esperadas pelo sistema de colisões:
    - atributos: x, y, w, h, rect, damage, life
    - métodos: update(dt, enemies), consume_life(amount), draw(surface)
    """

    def __init__(
        self,
        x: float,
        y: float,
        damage: int = 10,
        lifetime: float = 6.0,
        is_side_scroll: bool = False,
        direction: tuple[float, float] | None = None,
        max_life: int = 100,
        homing_speed: float | None = None,
        turn_rate: float = 5.0,
        locked_target: Any | None = None,
        source_ship: Any | None = None,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.damage = int(damage)
        self.max_life = int(max_life)
        self.life = float(self.max_life)
        self.dead = False
        self.lifetime = float(lifetime)
        self.age = 0.0
        self.is_side_scroll = is_side_scroll
        # Alvo fixo: quando definido, o projétil ignora outros inimigos enquanto
        # o alvo estiver vivo. Ao morrer, cai no _find_best_target normal.
        self.locked_target: Any | None = locked_target
        # Nave que originou o projétil. Em coop, evita que P1 e P2 (ambos
        # Caçador) compartilhem o mesmo gate de "homing já em tela".
        self.source_ship: Any | None = source_ship
        # Congelado no spawn (e não lido da nave no draw) para o projétil manter
        # a cor de quem atirou mesmo depois de a nave morrer. Mesmo nome que a
        # `Bullet` usa, que é o que os efeitos de impacto já procuram.
        self.player_index: int = int(getattr(source_ship, "player_index", 0) or 0)

        # Giro em torno do próprio eixo, contínuo desde o disparo (graus).
        self.rotation_angle: float = random.uniform(0.0, 360.0)

        # --- Sobrecarga ---------------------------------------------------
        # Ao esgotar o tempo de vida sem acertar nada, o projétil NÃO some: para
        # de voar e entra nesta sequência, que termina em estouro. `overload_t`
        # é o relógio dela e vale como progresso (0..`_OVERLOAD_TIME`) para
        # tremor, giro, inchaço e branco — um só relógio move os quatro, que é o
        # que os faz parecer a mesma coisa acontecendo em vez de quatro efeitos.
        self.overloading: bool = False
        self.overload_t: float = 0.0
        self.shake_x: float = 0.0
        self.shake_y: float = 0.0
        # Pedido de explosão em área, montado no estouro e consumido UMA vez
        # pelo `EntityManager` (§1: o projétil não alcança o manager; ele
        # descreve o que quer e quem tem o poder de spawnar resolve).
        self._pending_blast: dict[str, Any] | None = None

        speed = (
            homing_speed
            if homing_speed is not None
            else float(getattr(Config, "HOMING_BULLET_SPEED", 300))
        )
        self.homing_speed = float(speed)
        self.turn_rate = float(turn_rate)

        # Size and collision rect
        self.w = 10
        self.h = 10
        # `x`/`y` chegam como o CENTRO de onde o tiro sai (a boca do canhão, via
        # `Ship._muzzle_positions`) e o rect é ancorado no canto — a conversão
        # é aqui, como em `Bullet._anchor_on_center`. Sem ela o projétil nasce
        # 5px deslocado nos dois eixos, e o desvio muda de lado conforme a nave
        # gira, porque a boca gira e o deslocamento não.
        self.x -= self.w / 2.0
        self.y -= self.h / 2.0
        self.rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)

        # Initial velocity
        if direction:
            dx, dy = direction
            mag = (dx * dx + dy * dy) ** 0.5 or 1.0
            self.vx = dx / mag * self.homing_speed
            self.vy = dy / mag * self.homing_speed
        else:
            # Default upward
            self.vx = 0.0
            self.vy = -self.homing_speed

        # Track hits this frame to avoid multi-hit
        self.hit_this_frame: set[int] = set()

    def consume_life(self, amount: float) -> None:
        self.life = max(0.0, self.life - float(amount))
        if self.life <= 0.0:
            self.dead = True

    def _target_center(self, target: Any) -> tuple[float, float] | None:
        """Ponto de mira do alvo via geometria precisa compartilhada.

        Essencial para o boss da Serpente, cujo ``(x, y, w, h)`` é um bound
        fixo de tela inteira: ``target_point`` segue a cabeça via
        ``collision_circle``. Mirar em ``x + w/2`` levaria o projétil a um
        ponto invisível no topo central da tela.
        """
        return target_point(target)

    def _find_best_target(
        self, enemies: Iterable[Any], screen_w: float, screen_h: float
    ) -> Any | None:
        best = None
        best_d = float("inf")
        for e in enemies:
            # Ignora mortos, invulneráveis (boss em entrada/fase protegida) e
            # quem não está na tela — ver `is_huntable`.
            if not is_huntable(e, screen_w, screen_h):
                continue
            center = self._target_center(e)
            if center is None:
                continue
            cx, cy = center
            d = (cx - (self.x + self.w / 2)) ** 2 + (cy - (self.y + self.h / 2)) ** 2
            if d < best_d:
                best_d = d
                best = e
        return best

    def _is_off_screen(self, screen_w: int, screen_h: int) -> bool:
        """Verifica se o projétil saiu completamente da tela."""
        return (
            self.x + self.w < 0
            or self.x > screen_w
            or self.y + self.h < 0
            or self.y > screen_h
        )

    # ------------------------------------------------------------------
    # Sobrecarga
    # ------------------------------------------------------------------
    def take_pending_blast(self) -> dict[str, Any] | None:
        """Consome (uma única vez) o estouro em área deixado pela sobrecarga.

        Devolve kwargs prontos para `EntityManager.spawn_explosive_effect`, no
        mesmo contrato do `residue_bursts` da CityMine: a entidade calcula, quem
        pode spawnar spawna. `None` no caso normal — a esmagadora maioria dos
        frames de bala nenhuma está estourando.
        """
        blast = self._pending_blast
        self._pending_blast = None
        return blast

    def _overload_progress(self) -> float:
        """0..1 do avanço da sobrecarga. Único relógio de todos os efeitos dela."""
        return min(1.0, self.overload_t / _OVERLOAD_TIME)

    def _update_overload(self, dt: float) -> None:
        """Avança a sobrecarga: parado, tremendo, girando cada vez mais rápido.

        Tudo escala no MESMO `t` (quadrático, para a aceleração ser sentida como
        aceleração e não como rampa linear). O tremor sorteia aqui, e não no
        `draw`: aleatoriedade no render mudaria a imagem sem o estado mudar, e
        pausa/câmera lenta congelariam o projétil ainda vibrando (§3).
        """
        self.overload_t += dt
        self.age += dt  # o pulso de 3 frames continua correndo por baixo
        t = self._overload_progress()

        speed = _ROT_SPEED + (_OVERLOAD_ROT_SPEED_MAX - _ROT_SPEED) * t * t
        self.rotation_angle = (self.rotation_angle + speed * dt) % 360.0

        amplitude = _OVERLOAD_SHAKE_MAX * t * t
        self.shake_x = random.uniform(-amplitude, amplitude)
        self.shake_y = random.uniform(-amplitude, amplitude)

        if self.overload_t >= _OVERLOAD_TIME:
            self._detonate()

    def _begin_overload(self) -> None:
        self.overloading = True
        self.overload_t = 0.0
        # Para no lugar: a imobilidade repentina é o primeiro aviso de que algo
        # mudou, e é ela que dá ao tremor um ponto de referência para ler.
        self.vx = 0.0
        self.vy = 0.0

    def _detonate(self) -> None:
        self.dead = True
        self._pending_blast = {
            "x": self.x + self.w / 2.0,
            "y": self.y + self.h / 2.0,
            "radius": _OVERLOAD_BLAST_RADIUS,
            "damage": self.damage,
            "color": player_shot_color(_OVERLOAD_BLAST_COLOR, self.player_index),
        }

    def update(self, dt: float, enemies: list[Any] | None = None) -> None:
        if self.dead:
            return

        if self.overloading:
            self._update_overload(dt)
            return

        self.age += dt
        if self.age >= self.lifetime:
            self._begin_overload()
            return

        # Morte por saída de tela — sem sobrecarga. Fora do campo visível a
        # sequência inteira é invisível, e o estouro em área mataria um inimigo
        # ainda entrando pela borda sem o jogador ver de onde veio.
        sw = int(getattr(Config, "SCREEN_WIDTH", 1600))
        sh = int(getattr(Config, "SCREEN_HEIGHT", 900))
        if self._is_off_screen(sw, sh):
            self.dead = True
            return

        # Homing logic: preferir locked_target se ainda caçável, senão buscar o
        # mais próximo. Re-adquire se o alvo morreu, ficou invulnerável (ex.:
        # cabeça da Serpente volta a ficar protegida) ou SAIU DA TELA — este
        # último era o caso em que o projétil virava escolta de quem estava indo
        # embora e morria fora do campo de visão sem acertar nada.
        if enemies:
            if self.locked_target is not None and not is_huntable(
                self.locked_target, sw, sh
            ):
                self.locked_target = None
            target = (
                self.locked_target
                if self.locked_target is not None
                else self._find_best_target(enemies, sw, sh)
            )
            center = self._target_center(target) if target is not None else None
            if center is not None:
                tx, ty = center
                cx = self.x + self.w / 2
                cy = self.y + self.h / 2
                desired = math.atan2(ty - cy, tx - cx)
                current = (
                    math.atan2(self.vy, self.vx)
                    if (self.vx or self.vy)
                    else -math.pi / 2
                )
                diff = (desired - current + math.pi) % (2 * math.pi) - math.pi
                max_turn = self.turn_rate * dt
                if diff > max_turn:
                    diff = max_turn
                elif diff < -max_turn:
                    diff = -max_turn
                angle = current + diff
                self.vx = math.cos(angle) * self.homing_speed
                self.vy = math.sin(angle) * self.homing_speed

        # Integrate position
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

        # Rodopio constante, independente da direção de voo.
        self.rotation_angle = (self.rotation_angle + _ROT_SPEED * dt) % 360.0

    def _overload_surface(self, base: pygame.Surface) -> pygame.Surface:
        """`base` inchada, estirada, girada e clareando — tudo no mesmo `t`.

        A ordem importa: estica-e-comprime nos eixos da SPRITE e só então gira,
        senão o estiramento ficaria preso aos eixos da tela e o giro passaria por
        cima dele como se fossem dois efeitos sem relação. O branco entra por
        adição (preserva o alpha e a silhueta) na surface já transformada, que é
        recém-alocada — não há risco de sujar o cache.
        """
        t = self._overload_progress()
        grow = 1.0 + _OVERLOAD_GROW_MAX * t
        # Um eixo estica enquanto o outro comprime: preserva a massa aparente, e
        # é o que lê como "pressão por dentro" em vez de simples zoom.
        stretch = (
            _OVERLOAD_STRETCH_MAX
            * t
            * math.sin(self.overload_t * _OVERLOAD_STRETCH_HZ * math.tau)
        )
        w, h = base.get_size()
        surf = pygame.transform.scale(
            base,
            (
                max(1, round(w * grow * (1.0 + stretch))),
                max(1, round(h * grow * (1.0 - stretch))),
            ),
        )
        surf = pygame.transform.rotate(surf, -self.rotation_angle)
        white = int(255 * t**1.6)
        if white > 0:
            surf.fill((white, white, white), special_flags=pygame.BLEND_RGB_ADD)
        return surf

    def draw(self, surface: pygame.Surface) -> None:
        """Sprite girando no próprio eixo; na sobrecarga, tremendo e clareando.

        A fase da animação e o ângulo saem de `age`/`rotation_angle`, acumulados
        pelo `update` a partir do `dt` — nada de `time.time()`, que ignoraria
        pausa e câmera lenta (§3).
        """
        frames = _get_frames(self.player_index)
        if not frames:
            # Sprites ausentes (arte não instalada): círculo de sempre, para o
            # projétil nunca ficar invisível em jogo.
            s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            pygame.draw.circle(
                s, (0, 200, 255, 200), (self.w // 2, self.h // 2), self.w // 2
            )
            surface.blit(s, (int(self.x), int(self.y)))
            return

        anim_idx = int(self.age * _ANIM_FPS) % len(frames)
        if self.overloading:
            # No trecho final o núcleo dá lugar ao estouro; sem arte dedicada, o
            # próprio núcleo já está branco e inchado e faz o papel.
            base = frames[anim_idx]
            if self._overload_progress() >= _OVERLOAD_FLASH_AT:
                base = _get_flash_frame(self.player_index) or base
            frame = self._overload_surface(base)
            off_x, off_y = self.shake_x, self.shake_y
        else:
            # Voo normal: giro quantizado e memoizado, 1 blit e zero alocação.
            frame = _rotated(self.player_index, anim_idx, self.rotation_angle)
            off_x = off_y = 0.0

        fw, fh = frame.get_size()
        # A sprite girada é bem maior que o hitbox (10px): ancorar pelo CENTRO,
        # senão o desenho descola do que realmente colide. O excedente é
        # brilho/faísca em volta do núcleo, então o centro continua sendo o que o
        # olho lê como o projétil.
        surface.blit(
            frame,
            (
                int(self.x + self.w / 2 - fw / 2 + off_x),
                int(self.y + self.h / 2 - fh / 2 + off_y),
            ),
        )


sprite_loader.register("HomingBullet", preload_sprites)
