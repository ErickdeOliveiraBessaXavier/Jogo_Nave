"""Esferas de energia da Tríade — o vocabulário de ataque inteiro do chefe.

**Uma classe, seis comportamentos.** O boss não tem seis projéteis: tem UM, com
um `behavior` que troca só a função de movimento. É o que mantém a leitura do
encontro coesa — o jogador aprende "esfera de energia" uma vez, e depois aprende
*como cada uma se move*, que é informação nova de verdade.

Despacho por atributo, nunca por cascata de `isinstance` (§5): o construtor liga
`self._move` à função do comportamento e o `update_in_context` só a chama.
Comportamento novo = uma função e uma entrada no mapa.

## A assinatura visual

Núcleo brilhante com pequenos raios circulando — a esfera parece *energizada*.
Uma rotina de desenho só, e a DENSIDADE dos raios comunica o comportamento:
âncora crepita denso e parado, seeker arrasta os raios para trás, tether joga o
arco para o par. O efeito é estético, como pedido no conceito, mas carrega
informação de graça.

## Onde elas vivem

Em `em.enemies`, via `BossUpdateResult.spawned_enemies` — mesmo caminho dos
projéteis do Metropolis Overlord (`metropolis_projectiles`). Isso lhes dá de
graça colisão com a nave, grade espacial, limpeza de fim de fase e — de
propósito — **serem destrutíveis a tiro**. A Convergência da Fase 3 recompensa
quem limpou as âncoras, então a esfera precisa ser um alvo.
"""

from __future__ import annotations

import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

import pygame

from ....core.config import config as Config
from ....core.scale import gameplay_scale, scaled
from ....core.visual_quality import visual_quality as vq
from ...enemies._shared.enemy_hit_mixin import EnemyHitMixin
from . import triad_pixel_map as pmap

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class OrbBehavior(Enum):
    """Como a esfera se move. A aparência é a mesma; o movimento é o conteúdo."""

    SEEKER = auto()  # curva fraca por um tempo, depois segue reto
    LOB = auto()  # arco para cima e queda irregular
    ERRATIC = auto()  # senoide + correções em espasmos ("míssil burro")
    ANCHOR = auto()  # parada, crepita, expira — negação de espaço
    TETHER = auto()  # par ligado por arco elétrico (o arco é o hitbox)
    RING = auto()  # radial, velocidade constante
    VACUUM = auto()  # sendo puxada para o núcleo — inofensiva, é consumo


# ── Tuning por comportamento (px/s no design base 1280×720) ───────────────────
_SEEKER_SPEED = 190.0
_SEEKER_TURN_RATE = 1.15  # rad/s — angular, NÃO escala com resolução
_SEEKER_HOMING_TIME = 1.2  # depois disso desiste e segue reto
# Ao desistir, ela COMPROMETE: acelera até 2,1× e vai embora. Medido, o teleguiado
# ficava 7,15s em cena — quase todo esse tempo *depois* de já não representar
# decisão nenhuma, só flutuando pela arena a 190 px/s (mais devagar que a nave).
# Projétil que já foi resolvido e não sai do caminho não é dificuldade, é sujeira
# visual: ele fica sobrepondo as levas seguintes e a fase perde a leitura de
# ondas. Acelerar também lê bem — "ela se lançou" é a leitura óbvia do gesto.
_SEEKER_COMMIT_SPEED = 2.1
_SEEKER_COMMIT_ACCEL = 3.0  # por segundo, até o multiplicador cheio

# ── Chuva: SUBIR → ESTAGNAR → DESCER serpenteando ─────────────────────────────
# Três tempos, e a pausa no meio é o que faz o ataque ser legível: as esferas
# sobem, PARAM espalhadas no alto — simetricamente, o que o olho lê como
# formação e não como bagunça — e só então começam a cair devagar. O jogador vê
# a formação inteira montada antes de ela virar ameaça, e escolhe por onde vai
# passar com tempo.
#
# A parábola antiga não dava isso: subida e queda eram um movimento só, então a
# ameaça chegava junto com a leitura.
_LOB_RISE_TIME = 0.75    # subida, com desaceleração até parar no ponto
# 1,0s de estagnação. Era 0,55s, e o playtest mostrou que a parte difícil da
# Chuva não é a queda — é o POSICIONAMENTO: a nave costuma estar lá em cima
# atirando no chefe, e a formação se montava justo no caminho dela. Com os
# postos empurrados para o topo da tela (`_CHUVA_TOPO`) e um segundo cheio de
# pausa, o jogador tem tempo de sair de baixo antes de a queda começar.
_LOB_HOLD_TIME = 1.00
_LOB_FALL_SPEED = 125.0  # queda LENTA: dá para atravessar a formação andando
_LOB_WEAVE_AMP = 55.0    # amplitude do serpenteio na descida
_LOB_WEAVE_FREQ = 5.5
# Entrada da queda. Sem ela a virada "estagnada → caindo" era um TRANCO: a esfera
# estava parada e no frame seguinte já ia a 125 px/s para baixo e ~147 px/s para
# o lado. Medido frame a frame, e é isso que se via como um tranco lateral.
#
# Pior: a fase do serpenteio era sorteada no construtor, então o primeiro frame
# da queda calculava `sin(fase_aleatória)` e a esfera podia TELEPORTAR até ±55px
# de lado. Passava despercebido quando o sorteio caía perto de zero.
#
# A rampa resolve as três coisas de uma vez — posição, velocidade lateral e
# velocidade vertical entram todas em zero e crescem juntas.
_LOB_FALL_RAMP = 0.45

# ── Âncoras (minas): permanentes ──────────────────────────────────────────────
# Não expiram. Só somem quando levam tiro ou quando o chefe morre. Vira terreno,
# não projétil: o jogador decide se gasta tiro limpando o caminho ou se convive
# com o espaço negado. O teto de quantidade em tela é do BOSS (`_ANCORA_MAX`) —
# é ele que sabe quantas já colocou.
_ANCHOR_LIFETIME = float("inf")

# ── Pulsação ──────────────────────────────────────────────────────────────────
# Toda esfera respira. É a assinatura visual do vocabulário: "energia contida",
# não "bolinha". A fase é própria de cada uma, senão o conjunto pisca em bloco e
# lê como erro de render. O raio é quantizado no draw, então o cache de halo
# continua fechando em poucas entradas.
_PULSE_FREQ = 6.4
_PULSE_AMP = 0.20
_LOB_WEAVE_RAMP = 0.45   # segundos até a amplitude cheia, para não sair torto

# Serpenteio da Cadência. Ela persegue E oscila: o jogador vê que vem atrás dele,
# mas não consegue ler a posição exata do próximo instante — a esquiva vira
# leitura de fase, não de linha reta.
_SEEKER_WEAVE_AMP = 78.0
_SEEKER_WEAVE_FREQ = 4.2

_ERRATIC_SPEED = 135.0
_ERRATIC_CORRECTION_INTERVAL = 0.5
_ERRATIC_TURN_STEP = 0.42  # rad por espasmo
_ERRATIC_WOBBLE_FREQ = 5.5
_ERRATIC_WOBBLE_AMP = 62.0


_RING_SPEED = 165.0

# Sucção da Convergência. PÚBLICA porque é contrato entre módulos: o boss usa o
# mesmo valor como tempo de nascimento da salva de volta, e as duas coisas têm
# que casar no frame (§1 — nada de o boss ler um privado daqui).
# Tempo FIXO em vez de aceleração: assim todas chegam ao
# núcleo no mesmo instante, e a implosão lê como um gesto único do chefe em vez
# de esferas pingando. É esse mesmo tempo que a salva de volta usa de nascimento,
# então o estouro sai exatamente quando a última esfera é engolida.
VACUUM_TIME = 0.55

_TETHER_SAMPLES = 5  # círculos de colisão distribuídos ao longo do arco

# ── Ciclo de vida: nascer e morrer são VISÍVEIS ───────────────────────────────
# Projétil que aparece já valendo dano não é dificuldade, é emboscada — a mesma
# regra do telégrafo dos feixes (§7 do plano), aplicada ao vocabulário de esferas.
#
# NASCIMENTO: a esfera existe, é visível e **não fere**. Um anel se fecha sobre o
# ponto e o núcleo cresce de zero; quando o anel encosta, ela passa a valer. O
# jogador lê "vai nascer um projétil ali" e tem tempo de sair. Ela já é ALVO
# nessa janela, de propósito: quem lê cedo pode apagá-la antes de virar ameaça.
#
# MORTE: some em ~0,25s com o núcleo colapsando e um anel se abrindo. Sumir de um
# frame para o outro faz o jogador duvidar se levou dano ou não.
_BIRTH_TIME = 0.55
_DEATH_TIME = 0.26

_BIRTH = "birth"
_LIVE = "live"
_DYING = "dying"


_HALO_SPRITES: Dict[tuple, pygame.Surface] = {}
_ALPHA_STEPS = 8


def _halo_sprite(
    r: int,
    core: Tuple[int, int, int],
    bright: Tuple[int, int, int],
    alpha_scale: float,
) -> pygame.Surface:
    """Halo da esfera, desenhado uma vez por (raio, cor, faixa de alpha).

    Antes era uma `Surface` SRCALPHA nova **por esfera e por frame**. Com uma
    esfera solta ninguém nota; com o Pulso contínuo e a Chuva espalhada são
    dezenas em cena, e é a mesma classe de desperdício que travava os feixes
    (§7). O alpha é quantizado em oito faixas — a diferença entre faixas não é
    perceptível num halo, e sem a quantização o cache nunca acertaria.
    """
    passo = max(0, min(_ALPHA_STEPS, int(alpha_scale * _ALPHA_STEPS + 0.5)))
    key = (r, core, bright, passo)
    sprite = _HALO_SPRITES.get(key)
    if sprite is None:
        a = passo / _ALPHA_STEPS
        sprite = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pygame.draw.circle(sprite, (*core, int(70 * a)), (r * 2, r * 2), r * 2)
        pygame.draw.circle(sprite, (*core, int(150 * a)), (r * 2, r * 2), r)
        pygame.draw.circle(sprite, (*bright, int(235 * a)), (r * 2, r * 2), max(1, r // 2))
        _HALO_SPRITES[key] = sprite
    return sprite


class TriadOrb(EnemyHitMixin):
    """Uma esfera de energia. O `behavior` decide só como ela anda."""

    is_boss: bool = False
    HEALTH: int = 4
    POINTS: int = 0
    # 1,15× o tamanho original (9,0 e 11,0). O raio é colisão E desenho ao mesmo
    # tempo, então isto engorda a área de dano junto com a leitura — que é o
    # ponto: esferas pequenas demais faziam o jogador julgar o vão entre elas
    # pelo halo e não pelo corpo, e o halo é maior que a hitbox.
    RADIUS: float = 10.35
    ANCHOR_RADIUS: float = 12.65

    def __init__(
        self,
        x: float,
        y: float,
        behavior: OrbBehavior,
        *,
        angle: float = 0.0,
        speed: float | None = None,
        lifetime: float = 8.0,
        color: Tuple[int, int, int] = pmap.CYAN,
        target: Optional[Tuple[float, float]] = None,
        birth: float | None = None,
    ) -> None:
        sc = gameplay_scale()
        self.behavior = behavior
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.health = self.HEALTH
        self.dead = False
        self.anim = 0.0  # acumulador do draw, alimentado pelo update (§3)

        base_radius = self.ANCHOR_RADIUS if behavior is OrbBehavior.ANCHOR else self.RADIUS
        self.radius = base_radius * sc

        self.angle = angle
        self.speed = (speed if speed is not None else self._default_speed()) * sc
        self.vx = math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed
        self.lifetime = _ANCHOR_LIFETIME if behavior is OrbBehavior.ANCHOR else lifetime

        # Estado específico de comportamento. Mora aqui (e não numa subclasse)
        # porque a esfera é UMA entidade: subclassear por movimento traria de
        # volta a cascata de tipo que o §5 proíbe.
        self._homing_left = _SEEKER_HOMING_TIME
        self._commit = 1.0
        # De qual ataque esta esfera saiu. É o que permite ao chefe saber se uma
        # salva ainda está em cena antes de repetir o MESMO ataque.
        self.origin: str = ""
        self._correction_timer = 0.0
        self._wobble_phase = random.uniform(0.0, math.tau)
        self._pulse_phase = random.uniform(0.0, math.tau)
        # Fase do ciclo de vida. `birth` mais longo é o que ESCALONA uma salva:
        # emitir dez esferas no mesmo frame com nascimentos diferentes lê como
        # dez chegadas em sequência, sem o boss precisar de um relógio próprio.
        # Onde ela nasceu. O `_lob_from` é o mesmo ponto, mas com significado de
        # movimento; este é registro, e é o que permite auditar de onde uma salva
        # brotou depois de as esferas já terem andado.
        self.spawn = (self.x, self.y)
        self._lob_from = (self.x, self.y)
        self._lob_t = 0.0
        self._weave_dir = 1.0
        # Sucção da Convergência (ver `pull_to`).
        self._vac_from = (self.x, self.y)
        self._vac_t = 0.0
        self._consumed = False
        # Esfera PREMIADA: sai na cor contrária à da fase e larga um power-up ao
        # ser destruída. Quem marca é o chefe (ele conhece a fase); a esfera só
        # carrega o contrato. Ver `TriadBoss._sortear_premio`.
        self.prize: bool = False
        self._phase = _BIRTH
        self._phase_t = 0.0
        self._birth_time = _BIRTH_TIME if birth is None else max(0.05, birth)
        self.target = target
        self.partner: "TriadOrb | None" = None
        self._is_tether_master = False

        self._rect = pygame.Rect(0, 0, int(self.radius * 2), int(self.radius * 2))
        self._sync_rect()

        # Despacho por atributo (§5): a função de movimento é escolhida UMA vez.
        self._move: Callable[["TriadOrb", float, "EnemyUpdateContext"], None] = _MOVERS[
            behavior
        ]

    def _default_speed(self) -> float:
        return {
            OrbBehavior.SEEKER: _SEEKER_SPEED,
            OrbBehavior.LOB: 0.0,
            OrbBehavior.ERRATIC: _ERRATIC_SPEED,
            OrbBehavior.ANCHOR: 0.0,
            OrbBehavior.TETHER: 0.0,
            OrbBehavior.RING: _RING_SPEED,
        }[self.behavior]

    # ── Par do TETHER ────────────────────────────────────────────────────────
    @classmethod
    def link_pair(cls, a: "TriadOrb", b: "TriadOrb") -> None:
        """Liga duas esferas pelo arco. Só UMA das duas carrega o hitbox do arco.

        Sem o `master`, os círculos do arco existiriam em dobro e o segmento
        cobraria dano duas vezes no mesmo frame.
        """
        a.partner, b.partner = b, a
        a._is_tether_master = True
        b._is_tether_master = False

    # ── Contrato de entidade ─────────────────────────────────────────────────
    def _sync_rect(self) -> None:
        if self._phase is _DYING:
            self._rect.update(int(self.x), int(self.y), 0, 0)
            return
        if self.behavior is OrbBehavior.TETHER and self._is_tether_master and self.partner:
            # O rect precisa cobrir o ARCO inteiro: é o pré-filtro AABB de quem
            # colide com o segmento, não só com as duas pontas.
            p = self.partner
            left, right = min(self.x, p.x), max(self.x, p.x)
            top, bottom = min(self.y, p.y), max(self.y, p.y)
            r = int(self.radius)
            self._rect.update(
                int(left) - r, int(top) - r,
                int(right - left) + r * 2, int(bottom - top) + r * 2,
            )
            return
        self._rect.update(
            int(self.x - self.radius), int(self.y - self.radius),
            int(self.radius * 2), int(self.radius * 2),
        )

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        """Só fere depois de nascida e antes de começar a morrer.

        É o contrato inteiro do telégrafo: a esfera aparece, é visível, e não
        vale dano até o anel de nascimento encostar no núcleo.
        """
        return self._phase is _LIVE and not self._consumed

    @property
    def is_collectible(self) -> bool:
        """Pode ser recolhida pela Convergência: está na arena e ainda é dela.

        Inclui a esfera que ainda está NASCENDO — ela ocupa espaço na tela e o
        jogador a vê, então conta como "coisa que ele deixou viva". Exclui só o
        que já está saindo: em animação de morte ou já sendo sugada.
        """
        return not self.dead and self._phase is not _DYING and not self._consumed

    @property
    def is_hatching(self) -> bool:
        """Ainda nascendo — visível, inofensiva, e já pode levar tiro."""
        return self._phase is _BIRTH

    def can_take_damage(self) -> bool:
        """Contrato de `systems.targeting`. Quem já está morrendo sai da mira.

        Sem isto o teleguiado e o auto-aim gastariam carga numa esfera que já
        está tocando a animação de morte — alvo que não existe mais.
        """
        return self._phase is not _DYING and not self._consumed

    def _collision_radius(self) -> float:
        """Zero enquanto morre: some da colisão sem sair da lista de desenho.

        É o que deixa a animação de morte rodar sem a esfera continuar
        absorvendo tiro nem empurrando o avanço de fase. Raio zero nunca
        intersecta, então nenhum sistema precisa saber que esta fase existe.
        """
        return 0.0 if (self._phase is _DYING or self._consumed) else self.radius

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, self._collision_radius()

    def collision_circles(self) -> List[tuple[float, float, float]]:
        """Silhueta real (§8). No TETHER, **o arco é o hitbox** — não as pontas.

        É o que transforma dois projéteis numa LINHA móvel: o melhor retorno de
        complexidade por projétil no kit do chefe.
        """
        if not (self.behavior is OrbBehavior.TETHER and self._is_tether_master):
            return [(self.x, self.y, self._collision_radius())]
        p = self.partner
        if p is None or p.dead or self._phase is _DYING:
            return [(self.x, self.y, self._collision_radius())]
        circles: List[tuple[float, float, float]] = []
        r = self.radius * 0.75
        for i in range(_TETHER_SAMPLES + 1):
            t = i / _TETHER_SAMPLES
            circles.append((self.x + (p.x - self.x) * t, self.y + (p.y - self.y) * t, r))
        return circles

    def take_damage(self, amount: int) -> None:
        if self._phase is _DYING:
            return
        self.health -= amount
        if self.health <= 0:
            self.begin_death()

    def pull_to(self, ponto: Tuple[float, float]) -> None:
        """Passa a ser SUGADA para `ponto`, inofensiva, e some ao chegar.

        É a única troca de comportamento em tempo de execução do vocabulário, e
        ela existe porque a Convergência precisa que a esfera ainda seja a MESMA
        esfera — o jogador tem que ver aquela âncora que ele não limpou sendo
        engolida e voltando como parte do estouro. Matá-la e criar outra no
        núcleo contaria a mesma história com um corte no meio.

        Inofensiva a partir daqui: ela cruza a arena depressa e em linha reta, e
        cobrar dano nesse trajeto seria dano sem esquiva.
        """
        if self._phase is _DYING or self.behavior is OrbBehavior.VACUUM:
            return
        self.behavior = OrbBehavior.VACUUM
        self._move = _MOVERS[OrbBehavior.VACUUM]
        # Corta o nascimento: a esfera está sendo CONSUMIDA, e o anel de
        # nascimento é telégrafo de ameaça — ela deixou de ser uma. Sem isto,
        # uma esfera puxada enquanto ainda nascia ficava parada esperando o
        # próprio telégrafo terminar antes de começar a ser sugada.
        self._phase = _LIVE
        self.target = ponto
        self._vac_from = (self.x, self.y)
        self._vac_t = 0.0
        self._consumed = True
        self._sync_rect()

    def begin_death(self) -> None:
        """Entra na animação de morte. Idempotente.

        Não marca `dead` na hora: a esfera continua na lista por mais ~0,25s
        para o estouro aparecer. Nesse intervalo ela já não fere, não é alvo e
        não colide (ver `_collision_radius`), então nenhum outro sistema muda de
        comportamento por causa dela.
        """
        if self._phase is _DYING:
            return
        self._phase = _DYING
        self._phase_t = 0.0
        self.health = 0
        self._sync_rect()

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        """Igual ao mixin, mas o "matou" é lido na TRANSIÇÃO, não em `dead`.

        O mixin decide pelo flag `dead`, que agora só sobe no fim da animação —
        sem este override o tiro que derruba a esfera devolveria "só acertei", e
        o jogador perderia a explosão e o som da morte no exato frame em que ela
        acontece.
        """
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        antes = self._phase
        self.take_damage(damage)
        if antes is not _DYING and self._phase is _DYING:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=int(self.radius * 1.6),
                sound=hit_sounds.EXPLOSION_ALIEN,
                drops=self._drop_do_premio(),
            )
        return HitResult(explosion_size=int(self.radius), sound=hit_sounds.BOSS_DAMAGE)

    def _drop_do_premio(self) -> tuple:
        """O power-up da esfera premiada — só quando ela é DESTRUÍDA a tiro.

        Não sai por contato com a nave (ali o jogador levou dano, não venceu a
        esfera) nem quando a Convergência a engole. A recompensa paga a decisão
        de gastar tiro na esfera certa; entregá-la de graça apagaria a decisão.

        Nasce na posição da esfera, e não no topo da tela como o power-up de
        spawner: o vínculo entre "atirei naquela ali" e "caiu isto" é o que faz
        o jogador aprender a procurar a esfera de cor diferente.
        """
        if not self.prize:
            return ()
        from ....core.config import PowerUpType
        from ...pickups.powerup import PowerUp

        pu = PowerUp(PowerUpType.SPREAD_SHOT)
        pu.x = self.x - pu.w * 0.5
        pu.y = self.y - pu.h * 0.5
        pu.rect.topleft = (int(pu.x), int(pu.y))
        return (pu,)

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.begin_death()
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        self._phase_t += dt

        if self._phase is _BIRTH:
            # Nascendo: não anda e não gasta vida útil. Só existe para ser vista.
            if self._phase_t >= self._birth_time:
                self._phase, self._phase_t = _LIVE, 0.0
            self._sync_rect()
            return

        if self._phase is _DYING:
            if self._phase_t >= _DEATH_TIME:
                self.dead = True
            return

        self.lifetime -= dt
        if self.lifetime <= 0.0:
            # Expirar também é morrer: a âncora que some no fim do prazo merece
            # o mesmo estouro de quem levou tiro.
            self.begin_death()
            return

        self._move(self, dt, ctx)
        self._sync_rect()

        # Fora da tela com folga: some. Sem animação, de propósito — ninguém
        # está olhando, e um estouro fora da tela é trabalho jogado fora.
        # A âncora é a exceção: nasce dentro da arena e some por tempo.
        if self.behavior is not OrbBehavior.ANCHOR:
            margin = scaled(90.0)
            if (
                self.x < -margin
                or self.x > Config.SCREEN_WIDTH + margin
                or self.y > Config.SCREEN_HEIGHT + margin
                or self.y < -Config.SCREEN_HEIGHT
            ):
                self.dead = True

    # ── Render ───────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        """Núcleo + raios circulando. `draw` não muta estado (§3).

        O `random` aqui é crepitar puramente cosmético — mesmo padrão já aceito
        nos drones da CITY. Posição e vida avançam só no `update`.
        """
        alpha_scale = 1.0

        if self.behavior is OrbBehavior.TETHER and self._is_tether_master and self.partner:
            self._draw_link(surface)

        cx, cy = int(self.x), int(self.y)
        # PULSAÇÃO: a esfera respira. É a assinatura do vocabulário — "energia
        # contida", não bolinha —, e é ela que dá vida ao anel do Pulso, onde
        # doze esferas idênticas em linha reta pareciam um objeto só. A fase é
        # própria de cada uma; em bloco, a cena inteira pisca e lê como erro de
        # render. O raio vira INTEIRO aqui, o que mantém o cache de halo fechado
        # em meia dúzia de entradas por cor.
        pulso = 1.0 + _PULSE_AMP * math.sin(self.anim * _PULSE_FREQ + self._pulse_phase)
        r = max(1, int(self.radius * pulso))
        core = self.color
        bright = (
            min(255, core[0] + 90), min(255, core[1] + 60), min(255, core[2] + 40)
        )

        if self._phase is _BIRTH:
            self._draw_birth(surface, cx, cy, bright)
            return
        if self._phase is _DYING:
            self._draw_death(surface, cx, cy, r, bright)
            return

        surface.blit(_halo_sprite(r, core, bright, alpha_scale), (cx - r * 2, cy - r * 2))
        self._draw_arcs(surface, cx, cy, r, bright, alpha_scale)

    def _draw_birth(
        self, surface: pygame.Surface, cx: int, cy: int, bright: Tuple[int, int, int]
    ) -> None:
        """Anel que se FECHA sobre um núcleo que cresce.

        A leitura tem que ser inequívoca: "vai nascer um projétil aqui, e ele
        vale quando o anel encostar". O anel é a barra de progresso — quanto ele
        ainda tem para percorrer é exatamente quanto tempo o jogador ainda tem.
        Por isso ele contrai LINEARMENTE: uma curva suavizada mentiria sobre o
        tempo restante bem no trecho final, que é o que importa.
        """
        p = min(1.0, self._phase_t / self._birth_time)
        r = self.radius
        anel = int(r * (3.4 - 2.4 * p))
        pygame.draw.circle(surface, self.color, (cx, cy), max(2, anel), 1)
        nucleo = int(r * p)
        if nucleo >= 1:
            surface.blit(
                _halo_sprite(nucleo, self.color, bright, 0.35 + 0.65 * p),
                (cx - nucleo * 2, cy - nucleo * 2),
            )
        # Quatro marcas convergindo com o anel: dão direção ao movimento do anel
        # em telas cheias, onde um círculo fino sozinho se perde no fundo.
        for i in range(4):
            a = self.anim * 2.0 + i * (math.tau / 4)
            px, py = cx + math.cos(a) * anel, cy + math.sin(a) * anel
            pygame.draw.circle(surface, bright, (int(px), int(py)), 2)

    def _draw_death(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        r: int,
        bright: Tuple[int, int, int],
    ) -> None:
        """Núcleo colapsa, anel se abre. O oposto exato do nascimento.

        Simetria de propósito: as duas animações são a mesma figura em sentidos
        contrários, então aprender uma ensina a outra.
        """
        p = min(1.0, self._phase_t / _DEATH_TIME)
        anel = int(r * (1.0 + 1.8 * p))
        fade = 1.0 - p
        if anel >= 2:
            pygame.draw.circle(surface, self.color, (cx, cy), anel, max(1, int(2 * fade)))
        nucleo = int(r * (1.0 - p))
        if nucleo >= 1:
            surface.blit(
                _halo_sprite(nucleo, self.color, bright, fade),
                (cx - nucleo * 2, cy - nucleo * 2),
            )

    def _draw_arcs(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        r: int,
        bright: Tuple[int, int, int],
        alpha_scale: float,
    ) -> None:
        """Os pequenos raios em volta. A DENSIDADE identifica o comportamento."""
        count = vq.particles(_ARC_COUNT.get(self.behavior, 4))
        if count <= 0:
            return
        # Âncora crepita parada e densa; seeker arrasta os raios para trás.
        drift = 0.0
        if self.behavior in (OrbBehavior.SEEKER, OrbBehavior.RING, OrbBehavior.ERRATIC):
            drift = math.atan2(self.vy, self.vx) + math.pi
        spin = self.anim * 3.4
        for i in range(count):
            base = spin + i * (math.tau / count)
            if drift:
                base = drift + math.sin(self.anim * 6.0 + i) * 0.9
            inner = r * 0.85
            outer = r * (1.45 + random.random() * 0.55)
            mid_a = base + random.uniform(-0.35, 0.35)
            pts = [
                (cx + math.cos(base) * inner, cy + math.sin(base) * inner),
                (
                    cx + math.cos(mid_a) * (inner + outer) * 0.5,
                    cy + math.sin(mid_a) * (inner + outer) * 0.5,
                ),
                (cx + math.cos(base) * outer, cy + math.sin(base) * outer),
            ]
            pygame.draw.lines(surface, bright, False, pts, 1)
        if alpha_scale < 1.0:
            return

    def _draw_link(self, surface: pygame.Surface) -> None:
        """Arco elétrico entre o par — é ele que causa dano, então tem que LER."""
        p = self.partner
        if p is None or p.dead:
            return
        segments = 7
        pts: List[Tuple[float, float]] = []
        dx, dy = p.x - self.x, p.y - self.y
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        for i in range(segments + 1):
            t = i / segments
            jitter = 0.0 if i in (0, segments) else random.uniform(-1.0, 1.0) * self.radius
            pts.append((self.x + dx * t + nx * jitter, self.y + dy * t + ny * jitter))
        bright = (min(255, self.color[0] + 90), min(255, self.color[1] + 60), min(255, self.color[2] + 40))
        pygame.draw.lines(surface, self.color, False, pts, max(2, int(self.radius * 0.5)))
        pygame.draw.lines(surface, bright, False, pts, 1)


# ── Movimentos ────────────────────────────────────────────────────────────────
# Funções livres, e não métodos, para o mapa `_MOVERS` ser a fonte única do
# despacho: comportamento novo entra aqui e em `OrbBehavior`, sem tocar na classe.


def _move_seeker(orb: TriadOrb, dt: float, ctx: "EnemyUpdateContext") -> None:
    """Persegue OSCILANDO, e desiste depois de `_SEEKER_HOMING_TIME`.

    Desistir é o que a torna justa: teleguiado eterno não tem esquiva, só
    atrito. Com prazo, o jogador aprende que basta sobreviver à curva.

    O serpenteio é perpendicular ao rumo, então não atrapalha a perseguição —
    muda só o ponto exato onde ela está em cada instante. Uma teleguiada em
    linha reta se resolve com um passo lateral e some da cabeça do jogador; com
    a oscilação ele precisa acompanhar a fase, que é a leitura que o ataque quer
    cobrar.
    """
    if orb._homing_left > 0.0:
        orb._homing_left -= dt
        desired = math.atan2(ctx.player_y - orb.y, ctx.player_x - orb.x)
        diff = (desired - orb.angle + math.pi) % math.tau - math.pi
        step = _SEEKER_TURN_RATE * dt
        orb.angle += max(-step, min(step, diff))
        orb.vx = math.cos(orb.angle) * orb.speed
        orb.vy = math.sin(orb.angle) * orb.speed
    else:
        # Desistiu: acelera e sai. O serpenteio some junto — ela deixou de
        # negociar espaço com o jogador e virou só um corpo indo embora.
        orb._commit = min(_SEEKER_COMMIT_SPEED, orb._commit + _SEEKER_COMMIT_ACCEL * dt)
    orb._wobble_phase += _SEEKER_WEAVE_FREQ * dt
    lateral = math.cos(orb._wobble_phase) * _SEEKER_WEAVE_AMP * gameplay_scale()
    lateral /= orb._commit
    nx, ny = -math.sin(orb.angle), math.cos(orb.angle)
    orb.x += (orb.vx * orb._commit + nx * lateral) * dt
    orb.y += (orb.vy * orb._commit + ny * lateral) * dt


def _move_lob(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """SOBE até o posto, ESTAGNA, depois DESCE devagar serpenteando.

    Os três tempos são por relógio, não por física: a subida é uma interpolação
    que desacelera até parar (`1-(1-p)²`), então a esfera *chega* ao posto em vez
    de passar por ele e voltar. Uma parábola faria a estagnação depender da
    gravidade acertar o ápice no lugar certo — frágil e impossível de compor em
    formação.

    O serpenteio existe só na queda, e como DESLOCAMENTO em torno da coluna do
    posto: somado à velocidade, ele iria acumulando desvio e a formação simétrica
    montada lá em cima se desfaria no caminho.
    """
    orb._lob_t += dt
    px, py = orb.target if orb.target is not None else (orb.x, orb.y)
    fx, fy = orb._lob_from

    if orb._lob_t < _LOB_RISE_TIME:
        p = orb._lob_t / _LOB_RISE_TIME
        suave = 1.0 - (1.0 - p) * (1.0 - p)      # desacelera até parar
        orb.x = fx + (px - fx) * suave
        orb.y = fy + (py - fy) * suave
        return

    if orb._lob_t < _LOB_RISE_TIME + _LOB_HOLD_TIME:
        orb.x, orb.y = px, py                    # estagnada: a janela de leitura
        return

    caindo = orb._lob_t - _LOB_RISE_TIME - _LOB_HOLD_TIME
    sc = gameplay_scale()
    # Smoothstep, e não `min(1, c/ramp)`: a rampa linear tem um JOELHO no fim —
    # a derivada dela cai de 1/0,45 para zero de um frame para o outro, e isso
    # devolvia 75 px/s de degrau lateral bem quando a amplitude satura (medido:
    # 101 px/s em t=+0,52 da virada, contra ~34 dos frames vizinhos). O
    # smoothstep chega em 1 com derivada zero, então a entrada do serpenteio é
    # suave nas DUAS pontas.
    p = min(1.0, caindo / _LOB_FALL_RAMP)
    rampa = p * p * (3.0 - 2.0 * p)

    # Vertical: acelera durante a rampa e segue constante. A distância é a
    # integral da velocidade, então posição E velocidade saem contínuas na
    # virada — parar de cair de repente ou começar de repente lê igual de mal.
    if caindo < _LOB_FALL_RAMP:
        percorrido = _LOB_FALL_SPEED * caindo * caindo / (2.0 * _LOB_FALL_RAMP)
    else:
        percorrido = _LOB_FALL_SPEED * (caindo - _LOB_FALL_RAMP * 0.5)
    orb.y = py + percorrido * sc

    # Lateral: a fase conta do INÍCIO DA QUEDA (não do construtor), então o
    # primeiro frame tem `sin(0) = 0` e a esfera sai exatamente de onde estava.
    # A amplitude entra na mesma rampa, o que zera também a velocidade lateral
    # inicial — só `sin(0)=0` deixaria a esfera partir de lado a ~300 px/s.
    #
    # `_weave_dir` espelha os pares: o posto da esquerda serpenteia para o lado
    # oposto ao da direita, e a formação mantém a simetria enquanto desce. Com
    # todas no mesmo sentido a formação inteira escorrega junto e a simetria,
    # que é o ponto do ataque, se perde no meio da queda.
    lateral = math.sin(_LOB_WEAVE_FREQ * caindo) * _LOB_WEAVE_AMP * rampa
    orb.x = px + orb._weave_dir * lateral * sc


def _move_erratic(orb: TriadOrb, dt: float, ctx: "EnemyUpdateContext") -> None:
    """Míssil BURRO: deriva senoidal + correção em espasmos discretos.

    A correção acontece em passos de `_ERRATIC_TURN_STEP` a cada meio segundo,
    não continuamente — é o que faz ele parecer errático em vez de teleguiado.
    """
    orb._correction_timer -= dt
    if orb._correction_timer <= 0.0:
        orb._correction_timer = _ERRATIC_CORRECTION_INTERVAL
        desired = math.atan2(ctx.player_y - orb.y, ctx.player_x - orb.x)
        diff = (desired - orb.angle + math.pi) % math.tau - math.pi
        orb.angle += max(-_ERRATIC_TURN_STEP, min(_ERRATIC_TURN_STEP, diff))
    orb._wobble_phase += _ERRATIC_WOBBLE_FREQ * dt
    wobble = math.sin(orb._wobble_phase) * _ERRATIC_WOBBLE_AMP * gameplay_scale()
    nx, ny = -math.sin(orb.angle), math.cos(orb.angle)
    orb.x += (math.cos(orb.angle) * orb.speed + nx * wobble) * dt
    orb.y += (math.sin(orb.angle) * orb.speed + ny * wobble) * dt


def _move_anchor(_orb: TriadOrb, _dt: float, _ctx: "EnemyUpdateContext") -> None:
    """Não anda. Só ocupa espaço — e é esse o ataque.

    A âncora é a melhor ferramenta de dificuldade sem volume do chefe: ela torna
    todo o resto mais difícil sem colocar um projétil em movimento a mais.
    """
    return


def _move_tether(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """As duas pontas seguem reto; a distância entre elas respira.

    O par morre junto: um arco com uma ponta só não é nada, e deixar a órfã viva
    daria um projétil invisível (o hitbox mora no arco).
    """
    p = orb.partner
    if p is not None and (p.dead or not p.causes_damage):
        orb.begin_death()
        return
    orb.x += orb.vx * dt
    orb.y += orb.vy * dt


def _move_ring(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """Radial, velocidade constante. Leitura puramente posicional."""
    orb.x += orb.vx * dt
    orb.y += orb.vy * dt


def _move_vacuum(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """Puxada para o núcleo em tempo fixo, acelerando. Some ao chegar.

    Interpolação com `p²` (parte devagar, chega rápido): é a leitura de "está
    sendo ENGOLIDA", não de "está viajando até lá". Uma velocidade constante
    pareceria a esfera decidindo voltar por conta própria.
    """
    orb._vac_t += dt
    p = min(1.0, orb._vac_t / VACUUM_TIME)
    fx, fy = orb._vac_from
    tx, ty = orb.target if orb.target is not None else (fx, fy)
    puxa = p * p
    orb.x = fx + (tx - fx) * puxa
    orb.y = fy + (ty - fy) * puxa
    if p >= 1.0:
        orb.begin_death()


_MOVERS: Dict[OrbBehavior, Callable[[TriadOrb, float, "EnemyUpdateContext"], None]] = {
    OrbBehavior.SEEKER: _move_seeker,
    OrbBehavior.LOB: _move_lob,
    OrbBehavior.ERRATIC: _move_erratic,
    OrbBehavior.ANCHOR: _move_anchor,
    OrbBehavior.TETHER: _move_tether,
    OrbBehavior.RING: _move_ring,
    OrbBehavior.VACUUM: _move_vacuum,
}

# Quantidade de raios por comportamento — a densidade é o "sotaque" de cada um.
_ARC_COUNT: Dict[OrbBehavior, int] = {
    OrbBehavior.SEEKER: 4,
    OrbBehavior.LOB: 3,
    OrbBehavior.ERRATIC: 5,
    OrbBehavior.ANCHOR: 8,  # crepita denso e parado: "não chegue perto"
    OrbBehavior.TETHER: 3,
    OrbBehavior.RING: 3,
    OrbBehavior.VACUUM: 6,  # crepita denso ao ser engolida
}


def make_rain(
    x: float,
    y: float,
    posto: Tuple[float, float],
    color: Tuple[int, int, int],
    birth: float | None = None,
) -> TriadOrb:
    """Esfera da Chuva: sobe até `posto`, estagna e desce serpenteando.

    `posto` é o lugar no alto onde ela vai PARAR. Quem escolhe os postos é quem
    dispara, em formação simétrica — é a formação montada e imóvel que dá ao
    jogador a leitura da salva inteira antes de ela começar a cair.
    """
    orb = TriadOrb(x, y, OrbBehavior.LOB, color=color, lifetime=16.0, birth=birth)
    orb.target = posto
    orb._lob_from = (x, y)
    # Espelhado pelo lado do posto: a formação continua simétrica na descida.
    orb._weave_dir = -1.0 if posto[0] < Config.SCREEN_WIDTH * 0.5 else 1.0
    return orb
