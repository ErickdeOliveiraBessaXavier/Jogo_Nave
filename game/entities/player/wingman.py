import math
import random
from typing import Any, Dict, Final, List, Tuple

import pygame

from ...core.assets import BASE_DIR
from ...core.player_tint import player_sprite
from ...core.config import config as Config
from ...core.sound import sound_manager
from ...systems import aiming
from ...systems.targeting import is_targetable, target_point
from ..projectiles.mini_ship_bullet import MiniShipBullet
from ...core.fire_timer import FireTimer

# Asset em game/assets/icons/ (o caminho antigo `entities/assets/icons/` não
# existia — o sprite não carregava e o Wingman caía no fallback).
_SPRITE_PATH = BASE_DIR / "assets" / "icons" / "mini_ship.png"

# Nerf de dano aplicado SÓ contra bosses (sobre o multiplicador global de
# upgrades). O Wingman tem cadência alta (0.4 s), dano 1.5x e podem existir
# vários — sem isso o DPS em boss fica desproporcional ao das outras escoltas.
_WINGMAN_BOSS_DAMAGE_MULT: Final = 0.5

# ── Anti-sobreposição do esquadrão ──────────────────────────────────────────
#
# O upgrade solta TRÊS escoltas, e as três compartilhavam o mesmo destino: em
# FOLLOW, um ponto fixo atrás do jogador (o `side_offset` sorteado só tinha dois
# valores, então duas delas caíam no mesmo lugar com 50% de chance); em HUNT, a
# mesma órbita, no mesmo raio e no mesmo sentido, em volta do mesmo alvo — o
# mais próximo, que é o mesmo para todas. Convergir era o comportamento
# projetado; ficar uma em cima da outra era a consequência.
#
# A separação tem três camadas, e cada uma resolve o empilhamento de um jeito
# que as outras não alcançam:
#
# 1. **vaga de formação** (FOLLOW): destinos distintos, então o equilíbrio já é
#    aberto — nada precisa empurrar ninguém no caso comum;
# 2. **anel e sentido por vaga** (HUNT): raios diferentes e órbitas opostas em
#    volta do alvo, o que separa sem brigar com a perseguição;
# 3. **repulsão** (sempre): a rede de segurança para o que as duas primeiras não
#    preveem — alvo trocando, escolta nascendo, todas espremidas contra a borda.
#
# As vagas são recalculadas por frame a partir do esquadrão vivo, então quando
# uma expira as outras FECHAM A FORMAÇÃO em vez de deixar o buraco.
_SEPARATION_RADIUS: Final = 44.0  # ~1.8x a largura (24px) — distância "coladas"
_SEPARATION_ACCEL: Final = 1500.0  # px/s² no limite do encosto
_FORMATION_SPACING: Final = 56.0  # distância lateral entre vagas vizinhas
_FORMATION_DEPTH: Final = 24.0  # o quanto as pontas do V ficam mais atrás
_FORMATION_BASE_Y: Final = 60.0  # distância atrás do jogador (vaga central)
_HUNT_RING_STEP: Final = 34.0  # anel extra por vaga na perseguição

class Wingman:
    # Chaveado por (tamanho, jogador): as escoltas do P2 são recoloridas junto
    # com a nave dele, então não podem dividir uma surface única de classe.
    _sprites: Dict[Tuple[int, int], pygame.Surface] = {}

    @classmethod
    def _get_sprite(cls, size: int, player_index: int) -> pygame.Surface:
        key = (size, player_index)
        sprite = cls._sprites.get(key)
        if sprite is None:
            raw = player_sprite(_SPRITE_PATH, player_index, cast_neutral=True)
            sprite = pygame.transform.smoothscale(raw, (size, size))
            cls._sprites[key] = sprite
        return sprite

    def __init__(self, player: Any, duration: float):
        self.player = player
        self.w, self.h = 24, 24
        self._sprite = self._get_sprite(self.w, getattr(player, "player_index", 0))
        
        # Inicia ao lado do jogador
        side_offset = 50 if random.random() > 0.5 else -50
        self.x = player.x + side_offset
        self.y = player.y + random.uniform(-20, 20)
        
        self.vx = 0.0
        self.vy = 0.0
        self.speed = 450.0
        self.turn_rate = 9.0
        
        self.duration = duration
        self.timer = duration
        self.dead = False
        
        self.shoot_cooldown = 0.4
        self._fire_timer = FireTimer()
        
        self.target = None
        self.state = "FOLLOW"  # "FOLLOW" ou "HUNT"
        
        # Lógica de rotação (giro suave do sprite na direção da mira)
        self.current_angle = aiming.ANGLE_UP
        self.target_angle = aiming.ANGLE_UP
        
        # Lógica de Animação de Nascimento
        self.spawn_timer = 0.0
        self.spawn_duration = 0.8
        self.scale = 0.0
        
        # Vaga na formação, recalculada por frame a partir do esquadrão vivo
        # (ver `_resolve_slot`). O par abaixo é o destino em FOLLOW; nasce na
        # vaga central e se acomoda no primeiro update, quando as irmãs são
        # conhecidas. Guardar a vaga no construtor não serviria: o índice muda
        # quando uma escolta expira, e a formação tem que fechar sozinha.
        self.slot = 0
        self.squad_size = 1
        self.follow_offset_x = float(side_offset)
        self.follow_offset_y = _FORMATION_BASE_Y

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(
        self,
        dt: float,
        enemies: List[Any],
        bullets: List[Any],
        squadron: List["Wingman"] | None = None,
    ):
        """Tick da escolta.

        `squadron` é a lista viva de escoltas do `EntityManager` — a fonte da
        vaga de formação e da repulsão. Entra por parâmetro, e não por acesso ao
        manager (§1): a escolta continua sem conhecer quem a hospeda, e testar
        a separação é montar uma lista de duas.
        """
        self.timer -= dt
        if self.timer <= 0:
            self.dead = True
            return

        self._resolve_slot(squadron)

        # Animação de nascimento
        if self.spawn_timer < self.spawn_duration:
            self.spawn_timer += dt
            self.scale = min(1.0, self.spawn_timer / self.spawn_duration)
            # Não ataca nem persegue enquanto está nascendo — mas já se afasta
            # das irmãs: nascer em cima de uma delas é o instante em que a
            # sobreposição é mais visível, com a escolta crescendo do zero.
            self._follow_behavior(dt)
            self._apply_separation(dt, squadron)
            self.x += self.vx * dt
            self.y += self.vy * dt
            return

        self.scale = 1.0

        # Re-adquire se não houver alvo ou se o atual morreu / ficou
        # invulnerável (ex.: cabeça da Serpente volta a ficar protegida).
        if self.target is None or not is_targetable(self.target):
            self.target = self._find_target(enemies)
        
        if self.target:
            self.state = "HUNT"
        else:
            self.state = "FOLLOW"

        if self.state == "HUNT":
            self._hunt_behavior(dt)
        else:
            self._follow_behavior(dt)

        # Depois do comportamento e antes da integração: a repulsão corrige a
        # velocidade que o comportamento acabou de pedir, no mesmo frame.
        self._apply_separation(dt, squadron)

        # Integração de movimento
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Atualizar ângulo visual
        if self.state == "HUNT" and self.target:
            tx, ty = self._target_center(self.target)
            self.target_angle = aiming.angle_to(
                tx - (self.x + self.w / 2), ty - (self.y + self.h / 2)
            )
        elif math.hypot(self.vx, self.vy) > 10:
            self.target_angle = aiming.angle_to(self.vx, self.vy)
        else:
            self.target_angle = aiming.ANGLE_UP

        # Interpolação suave do ângulo (evita snaps bruscos)
        self.current_angle = aiming.approach_angle(
            self.current_angle, self.target_angle, dt
        )

        # Limites da tela
        margin = 20
        self.x = max(margin, min(Config.SCREEN_WIDTH - self.w - margin, self.x))
        self.y = max(margin, min(Config.SCREEN_HEIGHT - self.h - margin, self.y))

        # Disparo — cadência pelo FireTimer compartilhado (o padrão antigo
        # descartava a sobra do frame a cada tiro e rendia abaixo do configurado).
        self._fire_timer.advance(dt, self.shoot_cooldown)
        if (
            self.state == "HUNT"
            and self.target
            and self._fire_timer.consume(self.shoot_cooldown)
        ):
            self._shoot(bullets)

    def _resolve_slot(self, squadron: List["Wingman"] | None) -> None:
        """Descobre a vaga desta escolta entre as do MESMO jogador.

        Por jogador, e não no esquadrão inteiro: as vagas são posições relativas
        à nave dona, então em coop as escoltas do P2 formam em volta do P2. A
        REPULSÃO, ao contrário, vale contra todo mundo — sobreposição é visual e
        não liga para quem é o dono.

        Sem alocar lista (§7): a contagem e o índice saem do mesmo laço. São
        poucas escoltas, mas isto roda por escolta por frame.
        """
        if not squadron:
            self.slot, self.squad_size = 0, 1
            self._update_formation_offsets()
            return

        slot = 0
        size = 0
        for other in squadron:
            if other.player is not self.player or other.dead:
                continue
            if other is self:
                slot = size
            size += 1

        self.slot = slot
        self.squad_size = max(1, size)
        self._update_formation_offsets()

    def _update_formation_offsets(self) -> None:
        """Posição da vaga em V atrás do jogador.

        As vagas se distribuem simetricamente em torno do centro e as pontas
        ficam mais atrás — a mesma leitura de "esquadrão em formação" que
        qualquer jogo de nave usa, e que substituiu o sorteio de dois lados que
        empilhava as escoltas metade das vezes.
        """
        centered = self.slot - (self.squad_size - 1) / 2.0
        self.follow_offset_x = centered * _FORMATION_SPACING
        self.follow_offset_y = _FORMATION_BASE_Y + abs(centered) * _FORMATION_DEPTH

    def _apply_separation(self, dt: float, squadron: List["Wingman"] | None) -> None:
        """Empurra a escolta para longe das irmãs coladas nela.

        Força proporcional à INVASÃO (0 no limite do raio, máxima no encosto):
        escoltas apenas próximas mal se notam, e só o encosto real gera um
        empurrão forte. Acelera a velocidade em vez de teleportar a posição —
        corrigir posição direto brigaria com o comportamento no frame seguinte e
        apareceria como tremor.

        Empate exato (mesma posição, o caso do nascimento em cima de outra) tem
        desempate determinístico pela vaga: sem ele, `dx = dy = 0` e as duas
        ficariam presas uma na outra para sempre.
        """
        if not squadron:
            return

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        push_x = 0.0
        push_y = 0.0

        for other in squadron:
            if other is self or other.dead:
                continue
            dx = cx - (other.x + other.w / 2)
            dy = cy - (other.y + other.h / 2)
            dist_sq = dx * dx + dy * dy
            if dist_sq >= _SEPARATION_RADIUS * _SEPARATION_RADIUS:
                continue

            dist = math.sqrt(dist_sq)
            if dist < 1e-4:
                # Sobrepostas no mesmo pixel: abre pelo ângulo da vaga.
                angle = self.slot * 2.399963  # ângulo áureo: vagas divergem
                dx, dy, dist = math.cos(angle), math.sin(angle), 1.0

            strength = (1.0 - dist / _SEPARATION_RADIUS) * _SEPARATION_ACCEL
            push_x += (dx / dist) * strength
            push_y += (dy / dist) * strength

        if push_x or push_y:
            self.vx += push_x * dt
            self.vy += push_y * dt

    def _target_center(self, target: Any) -> tuple[float, float]:
        """Ponto de mira do alvo, usando a geometria precisa compartilhada.

        Crucial para o boss da Serpente, cujo ``(x, y, w, h)`` é um bound fixo
        de tela inteira: ``target_point`` segue a cabeça via ``collision_circle``.
        """
        point = target_point(target)
        if point is not None:
            return point
        return (
            getattr(target, "x", 0.0) + getattr(target, "w", 0.0) / 2,
            getattr(target, "y", 0.0) + getattr(target, "h", 0.0) / 2,
        )

    def _find_target(self, enemies: List[Any]) -> Any:
        best = None
        best_d = 600 * 600 # Alcance máximo de detecção
        for e in enemies:
            # Ignora mortos e invulneráveis (boss em entrada/fase protegida)
            if not is_targetable(e):
                continue
            ex, ey = self._target_center(e)
            dx = ex - (self.x + self.w / 2)
            dy = ey - (self.y + self.h / 2)
            d = dx * dx + dy * dy
            if d < best_d:
                best_d = d
                best = e
        return best

    def _hunt_behavior(self, dt: float):
        if not self.target:
            return

        tx, ty = self._target_center(self.target)

        # Mantém uma distância segura enquanto persegue
        dx = tx - (self.x + self.w / 2)
        dy = ty - (self.y + self.h / 2)
        dist = math.hypot(dx, dy) or 1.0
        
        # Se estiver muito perto, tenta manter distância; se longe, aproxima.
        #
        # O anel é POR VAGA: as escoltas escolhem o mesmo alvo (o mais próximo é
        # o mesmo para todas), então um raio único as juntava no mesmo ponto da
        # órbita. Com um anel por vaga elas se distribuem em profundidade, e
        # alternar o sentido do giro faz as vizinhas se cruzarem em vez de
        # viajarem coladas — as duas coisas separam sem enfraquecer a caçada.
        target_dist = 150.0 + self.slot * _HUNT_RING_STEP
        if dist > target_dist:
            desired_vx = (dx / dist) * self.speed
            desired_vy = (dy / dist) * self.speed
        else:
            # Orbita ou flutua por perto
            spin = -1.0 if self.slot % 2 else 1.0
            desired_vx = (-dy / dist) * self.speed * 0.5 * spin
            desired_vy = (dx / dist) * self.speed * 0.5 * spin
        
        self.vx += (desired_vx - self.vx) * self.turn_rate * dt
        self.vy += (desired_vy - self.vy) * self.turn_rate * dt

    def _follow_behavior(self, dt: float):
        # Acompanha o jogador
        tx = self.player.x + self.player.w / 2 + self.follow_offset_x
        ty = self.player.y + self.player.h / 2 + self.follow_offset_y
        
        dx = tx - (self.x + self.w / 2)
        dy = ty - (self.y + self.h / 2)
        dist = math.hypot(dx, dy)
        
        if dist > 20:
            follow_speed = self.speed * 0.8
            desired_vx = (dx / dist) * follow_speed
            desired_vy = (dy / dist) * follow_speed
            self.vx += (desired_vx - self.vx) * (self.turn_rate * 0.5) * dt
            self.vy += (desired_vy - self.vy) * (self.turn_rate * 0.5) * dt
        else:
            self.vx *= (1 - 4 * dt)
            self.vy *= (1 - 4 * dt)

    def _shoot(self, bullets: List[Any]):
        if not self.target:
            return

        tx, ty = self._target_center(self.target)
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        
        angle = math.atan2(ty - cy, tx - cx)
        b_speed = Config.BULLET_SPEED * 1.1
        
        # Usa MiniShipBullet para consistência
        bullets.append(
            MiniShipBullet(
                cx - 2,
                cy - 2,
                math.cos(angle) * b_speed,
                math.sin(angle) * b_speed,
                damage=Config.MINI_SHIP_BULLET_DAMAGE * 1.5,  # Wingman é um pouco mais forte
                owner_ship=self.player,
                boss_damage_mult=_WINGMAN_BOSS_DAMAGE_MULT,  # nerf só em boss
            )
        )
        sound_manager.play_shot()

    def draw(self, surface: pygame.Surface):
        if self._sprite:
            # Pisca quando está prestes a expirar (últimos 3 segundos)
            if self.timer < 3.0 and int(self.timer * 10) % 2 == 0:
                return
            
            # Aplicar rotação ao sprite (base aponta para cima)
            rotated_sprite = aiming.rotate_sprite_up(self._sprite, self.current_angle)

            # Desenha com um brilho ciano suave ao redor
            rect = rotated_sprite.get_rect(center=(int(self.x + self.w / 2), int(self.y + self.h / 2)))
            
            surface.blit(rotated_sprite, rect)
