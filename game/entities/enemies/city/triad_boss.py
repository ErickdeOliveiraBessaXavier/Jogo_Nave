"""A Tríade — chefe nativo da CITY (nível 34).

Uma mente com três vozes: uma cabeça principal ("a Coroa", que carrega o HP real
do boss) e duas laterais ("as Vozes") que existem para PROTEGÊ-LA. Enquanto uma
lateral estiver sólida, a Coroa é intangível; derrubar as duas abre a JANELA DE
RESSONÂNCIA, a única fonte de dano real da luta. As laterais voltam depois de um
tempo, mas o dano na Coroa é permanente — o jogador perde tempo, nunca progresso.

Ver `PLANO_BOSS_TRIADE.md` (local, §13) para o desenho completo do encontro.

## O que existe neste arquivo

O encontro completo: as três fases, a SENTENÇA (a transição entre elas) e a
morte. Esta classe é a fachada — FSM, hitboxes, roteamento de dano e render —, e
tudo que dá para separar em lógica pura mora ao lado (§9).

## Repartição

    triad_pixel_map   geometria e sprites (fonte única das medidas), incluindo
                      a ÂNCORA e a BOCA derivadas do desenho e o cache de giro
    triad_head        o CORPO de uma lateral (HP, sprite, flash, pose de mira)
    triad_resonance   o TEMPO e a REGRA do portão (lógica pura, testável)
    triad_orb         as esferas: uma classe, seis comportamentos
    triad_beam        o feixe, com origem e ângulo lidos por callback
    triad_caster      a cabeça que MIRA e dispara — Voz real ou eco temporário
    triad_score       a partitura da Sentença: dado puro, sem pygame nem boss
    triad_boss        esta fachada: FSM, hitboxes, roteamento de dano, render

O portão não conhece as cabeças e as cabeças não conhecem o portão (§1); esta
classe é o único ponto que lê um e empurra para o outro.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Dict, List

import pygame

from ....core.assets import get_font
from ....core.config import config as Config
from ....core.events import EventBus
from ...bosses.boss_hit_mixin import BossHitMixin
from . import triad_pixel_map as pmap
from .triad_head import TriadHead
from .triad_beam import TriadBeam
from .triad_caster import TriadCaster
from . import triad_score as score
from .triad_orb import OrbBehavior, TriadOrb, make_rain
from .triad_resonance import LEFT, RIGHT, HeadState, ResonanceEvent, ResonanceGate

if TYPE_CHECKING:
    from ....systems.boss_context import BossUpdateContext, BossUpdateResult
    from ....systems.hit_result import HitResult

# ── Estados ───────────────────────────────────────────────────────────────────
# FSM mínima desta etapa. As fases (CORO / CONTRAPONTO / UNÍSSONO) e a SENTENÇA
# entram nas etapas 4-7 do plano; o gate de fase já é lido aqui só para o boss
# não precisar de reescrita quando elas chegarem.
_ENTERING = "entering"
_ACTIVE = "active"
_SENTENCA = "sentenca"

# ── Ciclo de ATAQUE da Fase 1 ("O Coro") ──────────────────────────────────────
# Uma cabeça de cada vez, sempre. É a fase que ensina o vocabulário, e ela só
# ensina se cada ataque puder ser observado isolado.
_ACT_BREATHER = "breather"  # respiro: todas cianas, nada acontece
_ACT_WINDUP = "windup"      # a cabeça da vez fica LARANJA — o telégrafo
_ACT_SUSTAIN = "sustain"    # o Pulso batendo: mais anéis, no compasso

# Wind-up CONSTANTE nas três fases (§7 do plano): o jogador calibra o tempo de
# reação uma vez e ele vale até o fim. Só a recuperação encurta com a fase.
_WINDUP_TIME = 0.5
_BREATHER_PHASE1 = 1.2
# Piso do respiro: nem a agressividade máxima pode colar dois ataques.
_BREATHER_FLOOR = 0.45

# Ataques da Fase 1.
_ATK_CADENCIA = "cadencia"   # leque de 3 teleguiadas fracas (lateral)
_ATK_CHUVA = "chuva"         # arco para cima, queda irregular (lateral)
_ATK_PULSO = "pulso"         # anel radial com UMA brecha (Coroa)

# ── Cadência: chegam UMA A UMA, de qualquer canto ─────────────────────────────
# Deixou de ser um leque saindo da cabeça. Cada esfera nasce num ponto próprio da
# arena e só então começa a perseguir, oscilando. O ganho é a janela de leitura:
# o jogador vê "está surgindo um ali" e reage a uma coisa de cada vez, em vez de
# receber três de uma vez e ter que resolver as três no mesmo instante.
_CADENCIA_COUNT = 4
_CADENCIA_STAGGER = 0.42     # atraso de nascimento entre esferas vizinhas
_CADENCIA_FIRST = 0.55       # aviso da primeira — a mais importante
# Zona de nascimento, em fração da tela. Longe das bordas para a esfera não
# nascer meio fora, e sem o topo, que é onde o boss está.
_CADENCIA_BAND_X = (0.10, 0.90)
_CADENCIA_BAND_Y = (0.22, 0.80)
# Nenhuma nasce colada no jogador: uma esfera que materializa em cima dele não
# tem esquiva, só dano. Fração da diagonal da tela.
_CADENCIA_CLEARANCE = 0.18
_CHUVA_COUNT = 6             # PAR: a formação é montada em espelho, aos pares
# Fração da largura da arena que a Chuva cobre, e o quanto cada faixa pode
# tremer dentro da sua. O jitter existe para o padrão não virar uma grade
# perfeita; ele é FRAÇÃO da faixa, então nunca invade a vizinha.
_CHUVA_SPAN = (0.08, 0.92)   # extremos da formação, em fração da largura
_CHUVA_TOPO = (0.15, 0.33)   # faixa de altura onde a formação estagna
_CHUVA_STAGGER = 0.09        # atraso de nascimento entre esferas vizinhas
_LANE_JITTER = 0.34
# ── Pulso: anel FECHADO, batendo em compasso ──────────────────────────────────
# Sem brecha. Um anel radial completo é atravessável por construção: as esferas
# são discretas e o vão ENTRE elas cresce com o raio, então o jogador passa por
# onde quiser desde que leia o espaçamento. Uma brecha reservada transformava a
# leitura numa só ("ache o buraco") e desperdiçava o que o padrão tem de melhor.
#
# Dez direções: a 200px do núcleo isso dá ~126px de vão entre esferas vizinhas —
# folga confortável para a nave, e apertando conforme ela sobe em direção à
# Coroa, que é a pressão certa.
_PULSO_SLOTS = 10            # direções do anel (sem brecha)
_PULSO_WAVES = 3             # anéis por ataque
_PULSO_BEAT = 0.85           # segundos entre anéis — o compasso
_PULSO_BIRTH = 0.22          # nascimento curto: a pulsação da Coroa já avisou

_CROWN_ACTOR = -1            # "quem age" quando é a cabeça principal
# Teto de segurança. Subiu de 40 porque as âncoras agora são PERMANENTES (até 8
# ocupando vaga o tempo todo) e o Pulso passou a bater três anéis fechados. O
# custo de render foi medido depois da otimização do halo: 38 esferas + o chefe
# custam 1,1 ms/frame, então a folga é de tempo, não de sorte.
_MAX_LIVE_ORBS = 52

# ── Fase 2 — "Contraponto" ────────────────────────────────────────────────────
# A dificuldade nova vem de SOBREPOSIÇÃO de padrões conhecidos, não de mais
# projéteis. A fase quase não introduz movimento novo: ela combina o que a Fase 1
# ensinou, e a combinação é o conteúdo.
_ATK_PAREDE = "parede"       # linha de esferas lentas atravessando a arena
_ATK_ANCORA = "ancora"       # esferas PARADAS que só ocupam espaço
_ATK_CORRENTE = "corrente"   # par ligado por arco — o arco é o hitbox
_ATK_ERRATICO = "erratico"   # mísseis burros

# ── Parede: duas frentes INTERCALADAS, uma de cada lado ───────────────────────
# Ímpar de um lado, par do outro, alternando na altura:
#
#     .        ← esquerda, indo para a direita
#        .     ← direita, indo para a esquerda
#     .
#        .
#     .
#
# É a intercalação que faz o padrão pedir alguma coisa. Duas paredes alinhadas
# se cancelam (basta um corredor livre nas duas); desencontradas, o corredor da
# esquerda é justamente onde a frente da direita vai passar, e o jogador tem que
# trocar de faixa no meio do caminho.
_PAREDE_ESQ = 5              # esferas na frente que vem da esquerda
_PAREDE_DIR = 4              # e na que vem da direita
_PAREDE_SPEED = 95.0
_PAREDE_SPAN = (0.12, 0.88)  # fração da altura coberta pelas duas frentes

# ── Âncoras (minas): terreno, não projétil ────────────────────────────────────
# Não expiram (ver `triad_orb`): só somem a tiro ou quando o chefe morre. O teto
# em tela é o que impede a arena de entupir ao longo de uma luta longa — são
# pequenas, então 8 já negam bastante espaço sem fechar rota nenhuma.
_ANCORA_COUNT = 3            # quantas o chefe planta de cada vez
_ANCORA_MAX = 8              # teto em tela
# Banda de plantio, em fração da tela. Larga de propósito: o campo tem que
# espalhar pela arena, não formar um aglomerado no meio.
_ANCORA_BAND_X = (0.08, 0.92)
_ANCORA_BAND_Y = (0.26, 0.86)
# Distância mínima entre duas minas, em fração da largura da tela. Sem ela o
# sorteio juntava minas quase encostadas: o par ocupava o espaço de uma e
# desperdiçava uma vaga do teto, e o campo lia como bagunça em vez de terreno.
# 0,15 dá ~192px em 720p — mais que o dobro do diâmetro da nave.
_ANCORA_SPACING = 0.15
# E nenhuma nasce colada no jogador, pela mesma razão da Cadência.
_ANCORA_CLEARANCE = 0.14
_ERRATICO_COUNT = 4
_ERRATICO_SPREAD = 1.15      # rad entre as pontas do leque inicial
# A "Inspiração": respiro maior que o da Fase 1, e é ele que avisa que vem combo.
# Subiu de 1,5 para 2,1 — com dois ataques por turno mais o campo de minas
# permanente, 1,5s não dava tempo de a arena esvaziar entre um turno e o
# seguinte, e a fase virava uma parede contínua de projéteis.
_BREATHER_PHASE2 = 2.1

# Combos: cada um é uma lista de (ator, ataque). Dois ou três agindo JUNTOS.
# Três combos, montados só com CHUVA, PULSO e PAREDE — o vocabulário que a Fase
# 1 ensinou. A dificuldade nova vem da SOBREPOSIÇÃO, não de padrões novos: o
# jogador já sabe ler cada peça, e o que ele aprende aqui é a combinação.
#
# A Chuva fica sempre com a Coroa (é a assinatura dela); a Parede sai das
# laterais, então telegrafa numa Voz.
# **Chuva e Parede nunca saem juntas.** As duas são padrões de ÁREA — uma nega a
# largura caindo, a outra nega as faixas atravessando — e sobrepostas não somam
# leitura, somam volume: a arena fica cheia sem que o jogador tenha uma pergunta
# nova para responder. Cada uma delas pareia com o Pulso, que é radial e negocia
# espaço de outro jeito.
#
# Os dois turnos SOLO existem por causa disso também: alternando pesado e leve, a
# fase respira. Como um combo nunca repete o anterior, sair de um par sempre cai
# num solo ou no outro par — o ritmo se alterna sozinho, sem regra extra.
_COMBOS = (
    ("coro", ((RIGHT, _ATK_PAREDE), (_CROWN_ACTOR, _ATK_PULSO))),
    ("tempestade", ((_CROWN_ACTOR, _ATK_CHUVA), (_CROWN_ACTOR, _ATK_PULSO))),
    ("mare", ((_CROWN_ACTOR, _ATK_CHUVA),)),
    ("muralha", ((LEFT, _ATK_PAREDE),)),
)

# ── Fase 3 — "Uníssono" ───────────────────────────────────────────────────────
# O portão CAI: as Vozes param de proteger a Coroa e viram atacantes puras. A
# pergunta muda de "consigo abrir a janela?" para "aguento a pressão?".
_ATK_UNISSONO = "unissono"       # três anéis com as brechas DESALINHADAS
# A brecha é da FASE 3, não do Pulso. Aqui ela existe porque são TRÊS anéis
# simultâneos e desalinhados: sem brecha nenhuma, três frentes concorrentes não
# deixariam corredor. O Pulso da Fase 1 é um anel só e por isso pode ser fechado.
_UNISSONO_GAP = 3
_ATK_DILUVIO = "diluvio"         # chuva de tela cheia com faixa segura
_ATK_CONVERGENCIA = "convergencia"  # recolhe as esferas soltas e devolve

# ── O tom de cada ataque ──────────────────────────────────────────────────────
# Deslocamento de MATIZ sobre a cor da família (ciano até a Fase 2, laranja na 3).
# Curto de propósito: o jogador tem que reconhecer "é da Tríade" antes de
# reconhecer "é a Chuva". Passando de ~±20° o ciano vira verde ou azul e a
# identidade visual do chefe se perde; o laranja vira vermelho, que o jogo inteiro
# usa para dano.
#
# O Pulso fica no tom BASE por ser o ataque do núcleo — é dele que a paleta sai.
# As minas levam o maior desvio: são as únicas que FICAM na tela, e distingui-las
# de um projétil recém-chegado é a leitura mais útil que a cor pode dar.
_ATK_TINT: Dict[str, float] = {
    _ATK_PULSO: 0.000,
    _ATK_CHUVA: -0.030,
    _ATK_CADENCIA: +0.042,
    _ATK_PAREDE: +0.022,
    _ATK_ANCORA: -0.042,
    _ATK_CORRENTE: +0.030,
    _ATK_ERRATICO: -0.016,
    _ATK_UNISSONO: 0.000,
    _ATK_DILUVIO: -0.030,
    _ATK_CONVERGENCIA: +0.042,
}

_BREATHER_PHASE3 = 1.1
_ORBIT_RADIUS = 0.155            # fração da largura — raio da órbita das Vozes
_ORBIT_SPEED = 0.55              # rad/s
_ORBIT_BREATH = 0.18             # respiração do raio
_DILUVIO_COUNT = 9
_DILUVIO_SAFE_LANES = 2          # faixas deixadas livres (a "faixa segura")
_CONVERGENCIA_MIN = 8            # anel mínimo mesmo com a arena limpa
_DESPERATION = 0.10              # abaixo disto o respiro encurta ainda mais

# ── A SENTENÇA ────────────────────────────────────────────────────────────────
# A coreografia inteira — quem dispara, de onde, para onde e quando — mora em
# `triad_score`, como dado puro. Aqui fica só o motor que a executa. Ver o
# docstring de lá para por que os padrões são fechar/girar/piscar e não paredes.
_SENT_BOSS_Y = 0.10          # altura do corpo enquanto a coreografia roda

# ── Cadência de flutuação ─────────────────────────────────────────────────────
_DRIFT_SPEED = 0.35  # rad/s da deriva lateral
_DRIFT_AMPLITUDE = 0.16  # fração da largura da tela
_BOB_SPEED = 1.1  # rad/s do sobe-e-desce
_BOB_AMPLITUDE = 10.0  # px
_ENTER_SPEED = 2.0  # fator de lerp da descida de entrada


class TriadBoss(BossHitMixin):
    BOSS_TYPE_NAME: str = "energy_triad"

    DEFAULT_HEALTH: int = 1400
    # HP de cada Voz como fração do HP da Coroa. ~16% cada: caro o bastante para
    # a decisão de suprimir a brasa ter peso, barato o bastante para o ciclo não
    # virar uma segunda luta antes da luta.
    SIDE_HP_FRACTION: float = 0.16

    # Gates de fase (fração do HP da Coroa) — lidos, mas ainda sem efeito.
    PHASE2_THRESHOLD: float = 0.66
    PHASE3_THRESHOLD: float = 0.33

    _MISS_TIME: float = 0.75
    _HIT_FLASH_TIME: float = 0.08

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        difficulty_multiplier: float = 1.0,
        aggressiveness_multiplier: float = 1.0,
        event_bus: EventBus | None = None,
    ) -> None:
        self.w: float = float(pmap.CONTENT_W * pmap.PIXEL_SCALE)
        self.h: float = float(pmap.CONTENT_H * pmap.PIXEL_SCALE)

        self._home_x: float = Config.SCREEN_WIDTH / 2.0 - self.w / 2.0
        self._home_y: float = Config.SCREEN_HEIGHT * 0.13
        self.x: float = x if x is not None else self._home_x
        self.y: float = y if y is not None else -self.h - 40.0

        self.difficulty_multiplier = difficulty_multiplier
        self.aggressiveness_multiplier = aggressiveness_multiplier
        self._bus = event_bus

        self.max_health: int = int(self.DEFAULT_HEALTH * difficulty_multiplier)
        self.health: int = self.max_health
        self.dead: bool = False
        self.active: bool = False

        self._state: str = _ENTERING
        self._time: float = 0.0
        self._hit_flash: float = 0.0
        self._miss_timer: float = 0.0
        self._miss_pos: tuple[float, float] = (0.0, 0.0)

        # Sprite da Coroa (cabeça principal + tronco + halo — uma peça só na arte).
        self._crown = pmap.load_part("crown")
        self._crown_attacking: bool = False
        # Um índice de frame para as três partes: elas são uma criatura só.
        self._frame_index: int = 0
        self._mask_cache: dict[tuple, pygame.mask.Mask] = {}

        side_hp = max(1, int(self.max_health * self.SIDE_HP_FRACTION))
        # A âncora de cada Voz é DERIVADA do sprite (`part_anchor`), não digitada:
        # a cabeça lateral é um gancho e qualquer ponto "óbvio" — centro do bbox,
        # centroide da silhueta, centroide do blob — cai no vazio de dentro dele.
        self.heads: List[TriadHead] = [
            TriadHead(LEFT, "left", side_hp, pmap.part_anchor("left"), pmap.SIDE_HEAD_RADIUS),
            TriadHead(RIGHT, "right", side_hp, pmap.part_anchor("right"), pmap.SIDE_HEAD_RADIUS),
        ]

        # Pace inverso à dificuldade, como no Archmage: Casual espera mais pela
        # regeneração (janela mais generosa), Pesadelo menos. A JANELA MÍNIMA
        # fica fora dessa escala de propósito — é piso de justiça, não de
        # dificuldade, e encurtá-la reintroduz o modo impossível.
        pace = 1.0 / max(0.5, difficulty_multiplier)
        self.gate = ResonanceGate(regen_delay=6.0 * pace)

        self._ui_scale: float = Config.SCREEN_WIDTH / 1280.0

        # ── Ciclo de ataque (Fase 1) ──────────────────────────────────
        self._act_state: str = _ACT_BREATHER
        self._act_timer: float = _BREATHER_PHASE1
        self._actor: int = _CROWN_ACTOR
        self._attack: str = _ATK_PULSO
        self._last_actor: int | None = None
        self._last_side_attack: str = _ATK_CHUVA
        self._last_crown_attack: str = _ATK_CHUVA
        # Batida do Pulso: quantos anéis faltam e onde está a brecha. O
        # `_pulse_flash` é lido pelo `draw` para a Coroa pulsar no compasso —
        # o draw não avança nada (§3), só lê o que o update deixou.
        self._pulse_left: int = 0
        self._pulse_turn: int = 0
        # Relógio PRÓPRIO da deriva lateral: congela durante o Pulso.
        self._drift_t: float = 0.0
        self._pulse_flash: float = 0.0
        # O turno deixou de ser UM ator: da Fase 2 em diante várias cabeças agem
        # juntas, e é a combinação que é o conteúdo.
        self._turn: List[tuple[int, str]] = []
        self._last_combo: str | None = None
        self._orbit_t: float = 0.0
        # Esferas que ESTE boss soltou e ainda vivem. Serve ao teto de
        # segurança agora e à Convergência da Fase 3 depois (ela recolhe as
        # esferas soltas da arena). Lista com teto, então rebuild por
        # compreensão é aceitável aqui (§6).
        self._orbs: List[TriadOrb] = []
        # Feixes emitidos neste frame, drenados pelo `update_boss`.
        self._pending_beams: List[TriadBeam] = []
        self._sent_t: float = 0.0
        self._sent_count: int = 0        # quantas Sentenças já ocorreram
        self._sent_beams: List[TriadBeam] = []
        # Agenda achatada da coreografia e o índice do próximo tiro a vencer.
        # Montada em `_begin_sentenca` porque depende da resolução em vigor.
        self._sent_schedule: List[tuple[float, score.Shot]] = []
        self._sent_next: int = 0
        self._sent_fim: float = 0.0
        # Cabeças em cena durante a Sentença: as duas Vozes mais os ECOS, que são
        # aparições temporárias. É o que permite oito cabeças disparando sem o
        # boss ter oito Vozes.
        self._sent_casters: List[TriadCaster] = []
        self._home_offsets = [(h.offset_x, h.offset_y) for h in self.heads]
        self._phase: int = 1             # 1, 2 ou 3
        # Agressividade encurta o RESPIRO, nunca o wind-up: o telégrafo é
        # contrato com o jogador, não botão de dificuldade.
        self._breather: float = max(
            _BREATHER_FLOOR, _BREATHER_PHASE1 / max(0.5, aggressiveness_multiplier)
        )

    # ── Geometria ────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    def _crown_circle(self) -> tuple[float, float, float]:
        cx, cy = pmap.CROWN_HEAD_CENTER
        return self.x + cx, self.y + cy, pmap.CROWN_HEAD_RADIUS

    def collision_circle(self) -> tuple[float, float, float]:
        """Círculo do alvo VÁLIDO do momento — não o do corpo inteiro.

        Quem consome isto é mira automática/teleguiado (`systems.targeting`) e
        dano em área (`_aoe_into_boss`, que aplica o hit NO CENTRO deste
        círculo). Devolver o centro geométrico do corpo faria os dois mirarem
        uma região intangível durante a Fase 1 — o teleguiado gastaria carga em
        nada e o AoE bateria sempre num MISS.

        Com o portão fechado devolve a primeira lateral atacável em ordem de
        slot (escolha ESTÁVEL de propósito: mirar sempre "a de menos vida"
        faria o alvo pular entre as duas a cada hit).
        """
        if self.gate.crown_vulnerable:
            return self._crown_circle()
        for head in self.heads:
            if head.damageable:
                return head.collision_circle()
        return self._crown_circle()

    def collision_circles(self) -> List[tuple[float, float, float]]:
        """Silhueta real (§8): uma hitbox por cabeça que pode ser atingida.

        A Coroa entra na lista MESMO intangível — é o que permite o tiro parar
        nela e o "MISS" aparecer, em vez de o projétil atravessar em silêncio e
        o jogador não descobrir por que não fez dano.
        """
        circles: List[tuple[float, float, float]] = [self._crown_circle()]
        for head in self.heads:
            if head.damageable:
                circles.append(head.collision_circle())
        return circles

    def get_ship_contact_hitboxes(self) -> List[pygame.Rect]:
        """Rects por parte, para consumidores que pedem retângulo.

        Não é mais o caminho da colisão de tiro: com `get_collision_mask_data`
        presente, o `_rect_collides_with_enemy` resolve tudo por máscara e nem
        chega aqui.
        """
        cx, cy, r = self._crown_circle()
        ir = int(r)
        rects = [pygame.Rect(int(cx - ir), int(cy - ir), ir * 2, ir * 2)]
        for head in self.heads:
            if head.damageable:
                rects.append(head.contact_rect())
        return rects

    # ── Área de dano por PIXEL ───────────────────────────────────────────────
    def _blit_origin(self) -> tuple[int, int]:
        return (int(self.x) + pmap.BLIT_OFFSET_X, int(self.y) + pmap.BLIT_OFFSET_Y)

    def _mask_key(self) -> tuple:
        """Identidade do conjunto de máscaras em cena, para o cache.

        Espaço de chaves minúsculo (frames × cabeças presentes × flags de
        ataque), então o cache satura em poucos segundos de luta e nunca mais
        recombina — daí não precisar de despejo.
        """
        return (
            self._frame_index,
            self._crown_attacking,
            *[
                (h.damageable, h.attacking, h.body_state)
                for h in self.heads
            ],
        )

    def _combined_mask(self) -> pygame.mask.Mask | None:
        """União das máscaras das partes em cena — a área de dano do boss.

        A Coroa entra MESMO intangível: é o que faz o tiro parar nela e o "MISS"
        aparecer em vez de o projétil atravessar em silêncio. Cabeça no DOWN não
        entra, então o soquete vazio é atravessável.
        """
        key = self._mask_key()
        cached = self._mask_cache.get(key)
        if cached is not None:
            return cached

        crown_mask = self._crown.mask(self._frame_index, self._crown_attacking)
        if crown_mask is None:
            return None
        combined = crown_mask.copy()
        for head in self.heads:
            head_mask = head.current_mask()
            if head_mask is not None:
                # Todas as partes vivem na MESMA tela de 64×64 escalada, então a
                # união é offset (0, 0) — nenhum alinhamento a calcular.
                combined.draw(head_mask, (0, 0))

        self._mask_cache[key] = combined
        return combined

    def get_collision_mask_data(self) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        """Contrato de colisão por pixel (`collision_physics.get_enemy_collision_mask_data`).

        Devolver isto faz o `_rect_collides_with_enemy` usar a silhueta REAL do
        PNG e ignorar rect/círculos: o tiro só acerta onde há pixel desenhado.
        Vale para projéteis do jogador e para o contato da nave.
        """
        mask = self._combined_mask()
        if mask is None:
            return None
        return mask, self._blit_origin()

    def _part_at(self, px: float, py: float) -> "TriadHead | TriadBoss | None":
        """Qual parte tem PIXEL desenhado no ponto do impacto.

        As laterais são testadas primeiro: elas e o tronco se sobrepõem em 2
        pixels na arte, e nesse empate a Voz deve ganhar (é o alvo obrigatório).
        Devolve None quando o ponto não cai em pixel nenhum — caso do dano em
        área, que aplica o hit no centro de um círculo e não numa silhueta.
        """
        ox, oy = self._blit_origin()
        lx, ly = int(px - ox), int(py - oy)
        size = pmap.FRAME * pmap.PIXEL_SCALE
        if not (0 <= lx < size and 0 <= ly < size):
            return None

        for head in self.heads:
            head_mask = head.current_mask()
            if head_mask is not None and head_mask.get_at((lx, ly)):
                return head
        crown_mask = self._crown.mask(self._frame_index, self._crown_attacking)
        if crown_mask is not None and crown_mask.get_at((lx, ly)):
            return self
        return None

    # ── Dano ─────────────────────────────────────────────────────────────────
    def can_take_damage(self) -> bool:
        """Alguma parte pode receber dano agora?

        Falso na entrada, na morte e durante a SENTENÇA — nela o boss inteiro é
        intangível e o jogador só tem que sobreviver e desviar.
        """
        return self.active and not self.dead and self._state != _SENTENCA

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ....systems.hit_result import NO_HIT

        if not self.can_take_damage() or damage <= 0:
            return NO_HIT

        # Roteamento por PIXEL: quem levou o tiro é a parte que tem conteúdo
        # desenhado no ponto de impacto. O fallback por proximidade cobre o dano
        # em área, que não tem ponto de impacto real — ele aplica o hit no centro
        # do `collision_circle`, que pode cair num pixel vazio.
        target = self._part_at(hit_x, hit_y)
        if target is None:
            target = self._fallback_target(hit_x, hit_y)
        if target is None:
            return NO_HIT

        if target is self:
            if not self.gate.crown_vulnerable:
                self._trigger_miss(hit_x, hit_y)
                return NO_HIT
            return self._damage_crown(damage)
        return self._damage_head(target, damage)

    def _fallback_target(self, px: float, py: float) -> "TriadHead | TriadBoss | None":
        """Quem responde quando o impacto não caiu sobre parte nenhuma.

        DENTRO do corpo → é a Coroa. O tronco é desenho de LINHA e quase todo
        oco: o projétil encosta num traço (a colisão vale, é a máscara que manda)
        mas o centro dele cai num vão. Sem esta regra o tiro caía no "parte
        atacável mais próxima" e era creditado a uma Voz — tiro na base do torso,
        em y 52, virava dano numa cabeça que termina em y 37. Era o sintoma
        relatado em playtest, e o mais difícil de ver: só acontece nos VÃOS.

        A comparação é entre DISTÂNCIAS A SUPERFÍCIES, não a pontos:

          * o corpo é o `rect` inteiro — distância 0 em qualquer lugar dentro
            dele, e a distância à borda fora dele;
          * cada Voz é o CÍRCULO dela — distância ao centro menos o raio.

        Medir a Coroa por um ponto (o centro da cabeça dela) era o furo: um tiro
        na ponta de baixo do losango fica a ~35px do centro da Coroa e a ~24px do
        centro de uma Voz, então a Voz "ganhava" um impacto que aconteceu no
        torso. Pior, o jogador atira DE BAIXO: quando a ponta do projétil toca a
        base do corpo, o centro dele ainda está um pixel ABAIXO do rect — ou
        seja, o ponto mais atingido da luta inteira caía sempre fora e era
        creditado a uma cabeça.
        """
        r = self.rect
        dx = max(r.left - px, 0.0, px - r.right)
        dy = max(r.top - py, 0.0, py - r.bottom)
        dist_body = math.hypot(dx, dy)
        if dist_body <= 0.0:
            # DENTRO do corpo e sem parte sob o ponto: é vão do traço, e vão de
            # traço é da Coroa, sem disputa. Deixar as Vozes competirem aqui
            # devolveria o bug por outra porta — o círculo de uma Voz cobre o
            # oco entre o rosto e o filamento, que é território do corpo.
            return self

        best: "TriadHead | None" = None
        best_d = float("inf")
        for head in self.heads:
            if not head.damageable:
                continue
            d = math.hypot(px - head.center_x, py - head.center_y) - head.radius
            if d < best_d:
                best, best_d = head, d

        if best is not None and best_d < dist_body:
            return best
        return self

    def _nearest_damageable(self, px: float, py: float) -> "TriadHead | TriadBoss | None":
        """Parte atacável de centro mais próximo do impacto.

        Os círculos das cabeças NÃO se sobrepõem (ver `triad_pixel_map`), então
        um ponto dentro de um deles é necessariamente o mais próximo daquele
        centro — não há zona ambígua para um tiro. O caso de impacto fora de
        todos é o dano em área, que aplica no centro do `collision_circle` e
        cai naturalmente na parte certa.
        """
        best: "TriadHead | TriadBoss | None" = None
        best_d2 = float("inf")

        if self.gate.crown_vulnerable:
            cx, cy, _ = self._crown_circle()
            best, best_d2 = self, (px - cx) ** 2 + (py - cy) ** 2

        for head in self.heads:
            if not head.damageable:
                continue
            d2 = (px - head.center_x) ** 2 + (py - head.center_y) ** 2
            if d2 < best_d2:
                best, best_d2 = head, d2
        return best

    def _damage_crown(self, damage: int) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.health -= damage
        self._hit_flash = self._HIT_FLASH_TIME
        if self.health <= 0:
            self.health = 0
            self.dead = True
            self._clear_field()
            return HitResult(
                killed=True,
                points=Config.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)

    def _damage_head(self, head: TriadHead, damage: int) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        was_ember = self.gate.is_rematerializing(head.slot)
        if not head.take_damage(damage):
            return HitResult(explosion_size=12, sound=hit_sounds.BOSS_DAMAGE)

        # A cabeça caiu. Qual das duas quedas foi é leitura do PORTÃO (a cabeça
        # só sabe que o HP acabou), e as duas têm feedback diferente: derrubar a
        # cabeça sólida é uma conquista; suprimir a brasa é manutenção.
        if was_ember:
            self.gate.head_remat_interrupted(head.slot)
            head.enter_down()
            return HitResult(explosion_size=25, sound=hit_sounds.BOSS_DAMAGE)

        self.gate.head_died(head.slot)
        head.enter_down()
        return HitResult(explosion_size=60, sound=hit_sounds.EXPLOSION_BOSS)

    def take_damage(self, amount: int) -> None:
        """Dano SEM posição (cadeias, alguns AoE). Cobra do portão primeiro.

        Sem posição não dá para rotear por proximidade, e mandar direto para a
        Coroa furaria o portão — a regra da luta é que ela só é ferida com as
        duas laterais fora. Então: enquanto houver lateral atacável, o dano vai
        para ela; só com o portão aberto ele chega ao núcleo.
        """
        if not self.can_take_damage() or amount <= 0:
            return
        for head in self.heads:
            if head.damageable:
                if head.take_damage(amount):
                    if self.gate.is_rematerializing(head.slot):
                        self.gate.head_remat_interrupted(head.slot)
                    else:
                        self.gate.head_died(head.slot)
                    head.enter_down()
                return
        if self.gate.crown_vulnerable:
            self.health = max(0, self.health - amount)
            self._hit_flash = self._HIT_FLASH_TIME
            if self.health <= 0:
                self.dead = True
                self._clear_field()

    def _trigger_miss(self, hit_x: float, hit_y: float) -> None:
        self._miss_timer = self._MISS_TIME
        self._miss_pos = (hit_x, hit_y - 30.0)

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update_boss(self, dt: float, ctx: "BossUpdateContext") -> "BossUpdateResult":
        from ....systems.boss_context import BossUpdateResult

        py = ctx.player_y if ctx.player_y is not None else Config.SCREEN_HEIGHT * 0.8
        spawned = self.update(dt, (ctx.player_x, py))
        result = BossUpdateResult()
        if spawned:
            result.spawned_enemies = list(spawned)
        if self._pending_beams:
            result.new_lasers = list(self._pending_beams)
            self._pending_beams.clear()
        return result

    def update(
        self, dt: float, player_pos: tuple[float, float] | None = None
    ) -> List[TriadOrb]:
        if self.dead:
            return []

        self._time += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._miss_timer = max(0.0, self._miss_timer - dt)
        self._pulse_flash = max(0.0, self._pulse_flash - dt / _PULSO_BEAT)

        if self._state == _ENTERING:
            self._update_entering(dt)
        elif self._state == _SENTENCA:
            self._update_sentenca(dt)
        else:
            self._update_drift(dt)
            if self._phase >= 3:
                self._update_orbit(dt)
            self._check_phase_gate()

        # O portão PARA durante a Sentença. As cabeças estão destacadas, voando
        # para as bordas e disparando — elas não estão remontando em soquete
        # nenhum. Sem esta pausa, os ~10s da coreografia devolvem as duas Vozes
        # de graça, e o jogador termina a transição com o portão fechado sem ter
        # perdido a janela por mérito do boss.
        if self._state != _SENTENCA:
            self._update_gate(dt)

        self._frame_index = int(self._time * pmap.ANIM_FPS)
        for head in self.heads:
            head.update(
                dt,
                self.x,
                self.y,
                self.gate.remat_progress(head.slot),
                self._frame_index,
            )

        if self._state != _ACTIVE or player_pos is None:
            return []
        return self._update_attack_cycle(dt, player_pos)

    def _update_entering(self, dt: float) -> None:
        self.x += (self._home_x - self.x) * _ENTER_SPEED * dt
        self.y += (self._home_y - self.y) * _ENTER_SPEED * dt
        if abs(self.y - self._home_y) < 4.0:
            self.y = self._home_y
            self._state = _ACTIVE
            self.active = True
            # O relógio da deriva parte do zero na ativação para o boss não
            # entrar já no meio de uma oscilação (um salto lateral visível).
            self._time = 0.0

    @property
    def _pulsing(self) -> bool:
        """O chefe está no meio da batida do Pulso (wind-up incluso)."""
        if self._act_state == _ACT_SUSTAIN:
            return True
        return self._act_state == _ACT_WINDUP and any(
            atk == _ATK_PULSO for _ator, atk in self._turn
        )

    def _update_drift(self, dt: float) -> None:
        """Deriva lateral + sobe-e-desce. A LATERAL PARA durante o Pulso.

        Os anéis nascem do núcleo do peito, e o núcleo se move junto com o corpo:
        com a deriva ligada, cada batida saía de um x diferente e os três anéis
        ficavam descentrados uns dos outros. O padrão é radial — ele só lê como
        radial se as ondas forem concêntricas.

        Quem congela é o **relógio** da deriva, não a posição: parar de somar
        `dt` faz o seno retomar exatamente de onde estava quando a batida acaba.
        Congelar a posição e voltar a ler `self._time` daria um salto lateral no
        fim de todo Pulso — o defeito seria menor, mas seria visível.

        O sobe-e-desce continua: ele é a respiração do corpo, não muda a origem
        dos anéis o bastante para importar, e travar tudo faria o chefe parecer
        pausado em vez de concentrado.
        """
        if not self._pulsing:
            self._drift_t += dt
        span = Config.SCREEN_WIDTH * _DRIFT_AMPLITUDE
        self.x = self._home_x + math.sin(self._drift_t * _DRIFT_SPEED) * span
        self.y = self._home_y + math.sin(self._time * _BOB_SPEED) * _BOB_AMPLITUDE

    def _update_gate(self, dt: float) -> None:
        """Avança o portão e faz o corpo das cabeças seguir o estado dele."""
        for event in self.gate.update(dt):
            if event is ResonanceEvent.WINDOW_OPENED:
                self._emit_shake(0.25, 4)

        self._sync_heads()

    def _sync_heads(self) -> None:
        """O corpo das cabeças alcança o estado do portão.

        Comparação de estado, e não reação a evento, porque a transição
        REMAT→SOLID **não emite evento** — ela acontece dentro do `gate.update`
        quando a brasa completa. Um sync guiado só por eventos deixaria a cabeça
        em brasa para sempre, atacável e translúcida, com o portão já fechado.
        """
        if self._phase >= 3:
            # Portão derrubado: as Vozes são orbitais permanentes e o estado
            # delas não vem mais do portão. Sincronizar aqui as apagaria (o
            # `disable` deixa as duas em DOWN, que é o estado "fora do soquete").
            return
        for head in self.heads:
            target = self.gate.state(head.slot)
            if head.body_state is target:
                continue
            if target is HeadState.SOLID:
                head.restore(self.gate.return_hp_fraction(head.slot))
            elif target is HeadState.REMAT:
                head.enter_remat()
            else:
                head.enter_down()

    # ── Ciclo de ataque — Fase 1, "O Coro" ───────────────────────────────────
    def _update_attack_cycle(
        self, dt: float, player_pos: tuple[float, float]
    ) -> List[TriadOrb]:
        """Respiro → wind-up (laranja) → disparo → respiro. Uma cabeça por vez.

        FSM com sentinela, não cadência periódica: cada estado tem duração
        própria e o próximo é escolhido no fim. O §14 lista esse caso como um
        dos que NÃO migram para `FireTimer`. A sobra do frame é carregada para o
        estado seguinte mesmo assim — descartá-la faria o ciclo render um número
        inteiro de frames em vez do tempo configurado.
        """
        self._act_timer -= dt
        if self._act_timer > 0.0:
            return []
        if self._phase >= 3 and self.health <= self.max_health * _DESPERATION:
            # Desespero: o respiro encurta no trecho final. Nenhuma mecânica
            # nova — só o mesmo vocabulário chegando mais rápido.
            self._breather = _BREATHER_FLOOR

        sobra = -self._act_timer  # quanto o timer passou de zero neste frame

        if self._act_state == _ACT_BREATHER:
            self._begin_windup()
            self._act_timer = _WINDUP_TIME - sobra
            return []

        if self._act_state == _ACT_SUSTAIN:
            # Batida seguinte do Pulso. O laranja SEGUE ACESO: o ataque não
            # acabou, e apagar o telégrafo no meio dele mentiria (§7).
            orbs = self._fire_pulse_wave()
            self._pulse_left -= 1
            if self._pulse_left > 0:
                self._act_timer = _PULSO_BEAT - sobra
                return orbs
            self._clear_telegraph()
            self._act_state = _ACT_BREATHER
            self._act_timer = self._breather - sobra
            return orbs

        # Fim do wind-up: a cabeça laranja cumpre o que prometeu.
        orbs = self._fire_current_attack(player_pos)
        if self._pulse_left > 0:
            self._act_state = _ACT_SUSTAIN
            self._act_timer = _PULSO_BEAT - sobra
            return orbs
        self._clear_telegraph()
        self._act_state = _ACT_BREATHER
        self._act_timer = self._breather - sobra
        return orbs

    def _begin_windup(self) -> None:
        """Planeja o turno e acende o LARANJA em quem vai agir.

        Laranja nunca mente (§7), em fase nenhuma: quem acende, dispara. É por
        isso que a Fase 3 NÃO deixa o boss laranja permanente como o plano
        original sugeria — laranja é o telégrafo, e um telégrafo que fica sempre
        aceso deixa de informar. A identidade visual da Fase 3 vem das esferas
        (que ficam laranja) e da órbita das Vozes.
        """
        self._turn = self._plan_turn()
        self._actor, self._attack = self._turn[0]
        self._act_state = _ACT_WINDUP
        for actor, _atk in self._turn:
            if actor == _CROWN_ACTOR:
                self._crown_attacking = True
            else:
                self.heads[actor].attacking = True

    def _plan_turn(self) -> List[tuple[int, str]]:
        """Quem age neste turno e com quê. É aqui que as fases se distinguem."""
        if self._phase >= 3:
            return self._plan_unisono()
        if self._phase == 2:
            return self._plan_combo()
        actor = self._pick_actor()
        return [(actor, self._pick_attack(actor))]

    def _plan_combo(self) -> List[tuple[int, str]]:
        """Fase 2: um combo, sem repetir o anterior.

        Repetir o combo imediatamente anterior é a forma mais rápida de a fase
        parecer curta — o jogador vê quatro ideias e sente duas.
        """
        opcoes = [c for c in _COMBOS if c[0] != self._last_combo] or list(_COMBOS)
        nome, partes = random.choice(opcoes)
        self._last_combo = nome
        # Cabeça fora de cena não age; se sobrar só a Coroa, ela assume o pulso.
        turno = [
            (a, atk) for a, atk in partes
            if a == _CROWN_ACTOR or self.gate.is_solid(a)
        ]
        turno = turno or [(_CROWN_ACTOR, _ATK_PULSO)]
        # As minas não são um dos combos: são TERRENO, e o chefe as repõe até o
        # teto enquanto planta. Como não expiram, o campo se estabelece nos
        # primeiros turnos e só volta a crescer quando o jogador limpa alguma.
        if self._live_anchors() < _ANCORA_MAX:
            turno.append((_CROWN_ACTOR, _ATK_ANCORA))
        return turno

    def _plan_unisono(self) -> List[tuple[int, str]]:
        """Fase 3: as três agem como UMA. Sem turnos, sem revezamento."""
        escolha = random.random()
        if escolha < 0.34:
            return [(_CROWN_ACTOR, _ATK_UNISSONO)]
        if escolha < 0.67:
            return [(_CROWN_ACTOR, _ATK_DILUVIO)]
        return [(_CROWN_ACTOR, _ATK_CONVERGENCIA)]

    def _clear_telegraph(self) -> None:
        self._crown_attacking = False
        for head in self.heads:
            head.attacking = False

    def _pick_actor(self) -> int:
        """Round-robin entre quem PODE agir, sem repetir o ator anterior.

        Cabeça derrubada ou em brasa não ataca — ela não está lá. Com as duas
        fora, a Coroa fica sozinha em cena e age em todo turno, o que é a leitura
        certa: é o momento em que ela está exposta e pressionando sozinha.
        """
        candidatos = [h.slot for h in self.heads if self.gate.is_solid(h.slot)]
        candidatos.append(_CROWN_ACTOR)
        if len(candidatos) > 1 and self._last_actor in candidatos:
            candidatos.remove(self._last_actor)
        escolhido = candidatos[0] if len(candidatos) == 1 else random.choice(candidatos)
        self._last_actor = escolhido
        return escolhido

    def _pick_attack(self, actor: int) -> str:
        """Coroa alterna Pulso e Chuva; as Vozes fazem Cadência.

        A divisão é de IDENTIDADE, não de variedade: a Coroa semeia a arena
        (anéis do núcleo, chuva de tela cheia) e as Vozes fazem pressão direta
        (perseguidoras). O jogador aprende de quem esperar o quê, e é isso que
        torna o telégrafo laranja informativo — saber QUEM vai agir passa a
        dizer O QUE vem.
        """
        if actor == _CROWN_ACTOR:
            self._last_crown_attack = (
                _ATK_CHUVA if self._last_crown_attack == _ATK_PULSO else _ATK_PULSO
            )
            return self._last_crown_attack
        return _ATK_CADENCIA

    # ── Emissões ─────────────────────────────────────────────────────────────
    def _fire_current_attack(self, player_pos: tuple[float, float]) -> List[TriadOrb]:
        self._prune_orbs()
        livres = _MAX_LIVE_ORBS - len(self._orbs)
        if livres <= 0:
            return []

        # Zerado ANTES do despacho: só o ataque deste turno pode armar a
        # sustentação. Sem isto, um `_pulse_left` sobrando de um Pulso
        # interrompido (pela Sentença, por exemplo) faria o ataque SEGUINTE —
        # qualquer um — sair batendo anéis que ninguém pediu.
        self._pulse_left = 0
        orbs: List[TriadOrb] = []
        for actor, ataque in self._turn or [(self._actor, self._attack)]:
            self._actor, self._attack = actor, ataque
            orbs.extend(self._fire_one(ataque, player_pos))

        orbs = orbs[:livres]
        self._orbs.extend(orbs)
        return orbs

    def _fire_one(self, ataque: str, player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Despacho por MAPA, não por cascata de `if` (§5).

        Ataque novo entra em `_FIRE_TABLE` e na constante do nome; este método
        não muda.
        """
        fn = _FIRE_TABLE.get(ataque)
        return fn(self, player_pos) if fn else []

    def _prune_orbs(self) -> None:
        self._orbs = [o for o in self._orbs if not o.dead]

    def _actor_origin(self) -> tuple[float, float]:
        if self._actor == _CROWN_ACTOR:
            cx, cy = pmap.CORE_CENTER  # as esferas nascem do núcleo do peito
            return self.x + cx, self.y + cy
        head = self.heads[self._actor]
        return head.center_x, head.center_y

    @staticmethod
    def _lanes(count: int, lo: float, hi: float, jitter: float) -> List[float]:
        """`count` posições espaçadas entre `lo` e `hi`, com folga garantida.

        Cada uma fica no centro da sua faixa e só treme dentro dela (`jitter` é
        fração da largura da faixa). Assim o espaçamento mínimo é conhecido antes
        do sorteio — nenhuma esfera pode cair em cima da vizinha.
        """
        if count <= 0:
            return []
        if count == 1:
            return [(lo + hi) * 0.5]
        largura = (hi - lo) / count
        folga = largura * jitter * 0.5
        return [
            lo + largura * (i + 0.5) + random.uniform(-folga, folga)
            for i in range(count)
        ]

    def _fire_cadencia(self, player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Perseguidoras que MATERIALIZAM pela arena, uma a uma.

        Antes era um leque de três saindo da cabeça no mesmo frame: o jogador
        recebia as três de uma vez e resolvia com um passo lateral só. Agora cada
        uma nasce num ponto próprio, com o anel de nascimento anunciando o lugar,
        e o escalonamento faz o ataque chegar em conta-gotas — a pressão vira
        sustentada em vez de instantânea.

        Nenhuma nasce perto do jogador (`_CADENCIA_CLEARANCE`). Materializar em
        cima dele não seria dificuldade, seria dano sem esquiva — e é justamente
        o que a animação de nascimento existe para evitar.
        """
        sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
        minima = math.hypot(sw, sh) * _CADENCIA_CLEARANCE
        cor = self._palette(_ATK_CADENCIA)
        orbs: List[TriadOrb] = []
        for i in range(_CADENCIA_COUNT):
            px, py = self._spawn_longe_do_jogador(player_pos, minima, sw, sh)
            orbs.append(
                TriadOrb(
                    px, py, OrbBehavior.SEEKER,
                    angle=math.atan2(player_pos[1] - py, player_pos[0] - px),
                    color=cor,
                    birth=_CADENCIA_FIRST + i * _CADENCIA_STAGGER,
                )
            )
        return orbs

    @staticmethod
    def _spawn_longe_do_jogador(
        player_pos: tuple[float, float], minima: float, sw: float, sh: float
    ) -> tuple[float, float]:
        """Ponto na banda de nascimento, o mais longe possível do jogador.

        Sorteia candidatos e devolve o primeiro que respeita `minima`; se nenhum
        respeitar, devolve **o mais distante que apareceu**.

        O fallback óbvio — empurrar o ponto para longe pelo vetor jogador→ponto e
        depois grampeá-lo na banda — parece certo e não é: o grampo desfaz o
        empurrão sempre que a direção aponta para fora da banda, e a esfera
        reaparece perto do jogador. Foi exatamente assim que uma nasceu a 231px
        de um mínimo de 352px. Escolher o melhor candidato não tem esse buraco e
        também sempre termina.
        """
        lo_x, hi_x = sw * _CADENCIA_BAND_X[0], sw * _CADENCIA_BAND_X[1]
        lo_y, hi_y = sh * _CADENCIA_BAND_Y[0], sh * _CADENCIA_BAND_Y[1]
        melhor = (lo_x, lo_y)
        melhor_d = -1.0
        for _ in range(12):
            px = random.uniform(lo_x, hi_x)
            py = random.uniform(lo_y, hi_y)
            d = math.hypot(px - player_pos[0], py - player_pos[1])
            if d >= minima:
                return px, py
            if d > melhor_d:
                melhor, melhor_d = (px, py), d
        return melhor

    def _fire_chuva(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Ataque de assinatura da COROA: arco para cima e queda serpenteando.

        Sai sempre do núcleo do peito, e não de quem estiver de turno. A Chuva é
        a identidade dela em combate — é a Coroa que semeia a arena inteira,
        enquanto as Vozes fazem pressão direta. Amarrar o ataque ao núcleo (e não
        ao ator) é o que deixa isso legível sem uma linha de texto.

        As faixas são distribuídas pela arena antes de a primeira esfera existir
        (`_lanes`), e cada esfera recebe a deriva que a leva à sua. Antes a
        deriva era sorteada e várias caíam quase no mesmo ponto: a "chuva" virava
        um jato, e um jato não nega área — só ocupa uma coluna. A queda é em "S"
        (`_move_lob`), com a oscilação somada POR CIMA da parábola, então o ponto
        de queda continua sendo o da faixa.

        A Chuva não persegue. Ela nega espaço; perseguir seria a Cadência de novo
        com outra aparência.
        """
        cx, cy = pmap.CORE_CENTER
        ox, oy = self.x + cx, self.y + cy
        cor = self._palette(_ATK_CHUVA)
        postos = self._postos_da_chuva()
        # O escalonamento é por PAR (`i // 2`), não por esfera: os postos vêm em
        # espelho, e nascimentos diferentes entre os dois lados quebravam a
        # simetria durante a subida inteira — a formação só ficava simétrica
        # depois de montada, que é tarde demais para a leitura que ela existe
        # para dar. Com o par saindo junto, a subida também é simétrica.
        return [
            make_rain(ox, oy, posto, cor, birth=0.30 + (i // 2) * _CHUVA_STAGGER)
            for i, posto in enumerate(postos)
        ]

    @staticmethod
    def _postos_da_chuva() -> List[tuple[float, float]]:
        """Formação SIMÉTRICA no alto: pares espelhados no eixo vertical.

        Simetria é o que faz a formação ler como formação. Posições sorteadas
        independentes viram uma nuvem, e nuvem não se lê — o jogador não
        consegue prever por onde vai passar antes de a queda começar.

        Os pares abrem em leque (o de fora mais alto que o de dentro), o que
        espalha as colunas de queda pela largura toda sem empilhar esferas na
        mesma altura.
        """
        sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
        meio = sw * 0.5
        pares = _CHUVA_COUNT // 2
        postos: List[tuple[float, float]] = []
        for k in range(pares):
            # k=0 é o par mais próximo do centro.
            t = (k + 1) / pares
            dx = (sw * _CHUVA_SPAN[1] - meio) * t
            ty = _CHUVA_TOPO[0] + (_CHUVA_TOPO[1] - _CHUVA_TOPO[0]) * (1.0 - t)
            postos.append((meio - dx, sh * ty))
            postos.append((meio + dx, sh * ty))
        if _CHUVA_COUNT % 2:
            postos.append((meio, sh * _CHUVA_TOPO[1]))
        return postos

    def _fire_pulso_arg(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Primeira batida do Pulso, e arma as seguintes.

        Cada batida gira o anel meio passo em relação à anterior: as esferas da
        onda seguinte saem ENTRE as vagas da onda de antes, então o corredor que
        o jogador escolheu fecha e ele precisa escolher outro. É a única coisa
        que impede o anel fechado de virar "achou um vão, ficou nele".
        """
        self._pulse_turn = 0
        self._pulse_left = _PULSO_WAVES - 1
        return self._emit_pulse_ring()

    def _fire_pulse_wave(self) -> List[TriadOrb]:
        """Batida seguinte: o anel sai defasado meio passo."""
        self._pulse_turn += 1
        anel = self._emit_pulse_ring()
        self._prune_orbs()
        self._orbs.extend(anel)
        return anel

    def _emit_pulse_ring(self) -> List[TriadOrb]:
        """O anel em si. A pulsação da Coroa é acesa aqui — é o mesmo evento."""
        cx, cy = pmap.CORE_CENTER
        ox, oy = self.x + cx, self.y + cy
        passo = math.tau / _PULSO_SLOTS
        defasagem = passo * 0.5 * (self._pulse_turn % 2)
        cor = self._palette(_ATK_PULSO)
        self._pulse_flash = 1.0
        return [
            TriadOrb(
                ox, oy, OrbBehavior.RING, angle=i * passo + defasagem, color=cor,
                birth=_PULSO_BIRTH,
            )
            for i in range(_PULSO_SLOTS)
        ]

    # ── Ataques da Fase 2 ────────────────────────────────────────────────────
    def _fire_parede(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Duas frentes lentas, uma de cada lado, com as alturas INTERCALADAS.

        Cinco vindo da esquerda nas faixas pares, quatro da direita nas ímpares.
        Alinhadas elas se cancelariam — bastaria achar uma faixa livre nas duas e
        ficar nela. Desencontradas, a faixa livre da esquerda é exatamente por
        onde a frente da direita vai passar: o jogador entra num corredor e tem
        que trocar de faixa antes de ele fechar.

        Lentas de propósito (95 px/s, menos da metade da nave): o conteúdo é a
        rota, não o reflexo.
        """
        sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
        total = _PAREDE_ESQ + _PAREDE_DIR
        faixas = self._lanes(
            total, sh * _PAREDE_SPAN[0], sh * _PAREDE_SPAN[1], _LANE_JITTER
        )
        cor = self._palette(_ATK_PAREDE)
        margem = sw * 0.04
        orbs: List[TriadOrb] = []
        for i, alt in enumerate(faixas):
            da_esquerda = i % 2 == 0
            orbs.append(
                TriadOrb(
                    -margem if da_esquerda else sw + margem,
                    alt,
                    OrbBehavior.RING,
                    angle=0.0 if da_esquerda else math.pi,
                    speed=_PAREDE_SPEED,
                    lifetime=22.0,
                    color=cor,
                    # Escalonado por faixa: a parede se MONTA de cima para baixo
                    # em vez de aparecer inteira, o que dá tempo de ler a
                    # intercalação antes de ela chegar.
                    birth=0.35 + i * 0.07,
                )
            )
        return orbs

    def _fire_ancora(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Minas PARADAS e PERMANENTES. Não perseguem, não atiram — negam espaço.

        Não expiram: só somem a tiro ou quando o chefe morre. Isso as tira da
        categoria "projétil" e as põe na de TERRENO — o jogador decide se gasta
        tiro abrindo caminho ou se convive com a arena menor. É a ferramenta de
        dificuldade mais barata do chefe: torna todo o resto mais difícil sem
        colocar um projétil em movimento a mais.

        O teto (`_ANCORA_MAX`) é cobrado aqui e não na esfera, porque é o chefe
        que sabe quantas já plantou. Sem ele uma luta longa entope a arena.
        """
        vagas = _ANCORA_MAX - self._live_anchors()
        if vagas <= 0:
            return []
        cor = self._palette(_ATK_ANCORA)
        # Ocupadas: as minas que JÁ estão em campo. O espaçamento é cobrado
        # contra elas também, não só dentro desta leva — sem isso a leva nova
        # cai em cima da anterior e o campo se aglomera ao longo da luta.
        ocupadas = [
            (o.x, o.y)
            for o in self._orbs
            if o.behavior is OrbBehavior.ANCHOR and not o.dead
        ]
        novas: List[TriadOrb] = []
        for _ in range(min(_ANCORA_COUNT, vagas)):
            ponto = self._ponto_para_mina(ocupadas, _player_pos)
            if ponto is None:
                break
            ocupadas.append(ponto)
            novas.append(
                TriadOrb(
                    ponto[0], ponto[1], OrbBehavior.ANCHOR, color=cor, birth=0.45
                )
            )
        return novas

    @staticmethod
    def _ponto_para_mina(
        ocupadas: List[tuple[float, float]], player_pos: tuple[float, float]
    ) -> "tuple[float, float] | None":
        """Ponto para uma mina nova, longe das outras e do jogador.

        Sorteio com rejeição: tenta pontos na banda até achar um que respeite o
        espaçamento e a folga do jogador. Se em muitas tentativas nenhum servir,
        devolve `None` e o chefe simplesmente planta menos naquela leva — melhor
        ter sete minas bem distribuídas do que oito com duas coladas, que é o que
        um fallback "aceita o menos ruim" produziria.
        """
        sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
        minimo = sw * _ANCORA_SPACING
        folga = math.hypot(sw, sh) * _ANCORA_CLEARANCE
        lo_x, hi_x = sw * _ANCORA_BAND_X[0], sw * _ANCORA_BAND_X[1]
        lo_y, hi_y = sh * _ANCORA_BAND_Y[0], sh * _ANCORA_BAND_Y[1]
        for _ in range(40):
            px = random.uniform(lo_x, hi_x)
            py = random.uniform(lo_y, hi_y)
            if math.hypot(px - player_pos[0], py - player_pos[1]) < folga:
                continue
            if any(math.hypot(px - ox, py - oy) < minimo for ox, oy in ocupadas):
                continue
            return px, py
        return None

    def _clear_field(self) -> None:
        """Morte do chefe: tudo que ele deixou na arena morre junto.

        As minas não expiram — é justamente por isso que precisam disto. Sem o
        varrimento, um campo de oito ficaria ferindo o jogador depois de a luta
        ter acabado, o que lê como bug mesmo sendo consequência da regra.
        """
        for orb in self._orbs:
            if not orb.dead:
                orb.begin_death()
        self._orbs.clear()

    def _live_anchors(self) -> int:
        self._prune_orbs()
        return sum(
            1
            for o in self._orbs
            if o.behavior is OrbBehavior.ANCHOR and o.causes_damage
        )

    def _fire_corrente(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Duas esferas ligadas por um arco — e o ARCO é o hitbox.

        Dois projéteis viram uma LINHA móvel: o melhor retorno de complexidade
        por projétil no kit inteiro do boss.
        """
        sw = float(Config.SCREEN_WIDTH)
        _ox, oy = self._actor_origin()
        cor = self._palette(_ATK_CORRENTE)
        largura = sw * random.uniform(0.22, 0.34)
        centro = random.uniform(sw * 0.30, sw * 0.70)
        desce = math.pi / 2
        a = TriadOrb(centro - largura / 2, oy, OrbBehavior.TETHER,
                     angle=desce, speed=_PAREDE_SPEED, lifetime=14.0, color=cor)
        b = TriadOrb(centro + largura / 2, oy, OrbBehavior.TETHER,
                     angle=desce, speed=_PAREDE_SPEED, lifetime=14.0, color=cor)
        TriadOrb.link_pair(a, b)
        return [a, b]

    def _fire_erratico(self, player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Mísseis BURROS, em leque aberto.

        Os ângulos iniciais saem do mesmo `_lanes` da Chuva: espalhamento é
        regra do encontro, não de um ataque. Sem isso os quatro saem quase
        juntos e a correção em espasmos os mantém agrupados o caminho todo.
        """
        ox, oy = self._actor_origin()
        base = math.atan2(player_pos[1] - oy, player_pos[0] - ox)
        angulos = self._lanes(
            _ERRATICO_COUNT,
            base - _ERRATICO_SPREAD / 2,
            base + _ERRATICO_SPREAD / 2,
            _LANE_JITTER,
        )
        cor = self._palette(_ATK_ERRATICO)
        return [
            TriadOrb(ox, oy, OrbBehavior.ERRATIC, angle=a, lifetime=7.0, color=cor)
            for a in angulos
        ]

    # ── Ataques da Fase 3 ────────────────────────────────────────────────────
    def _fire_unissono(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Três anéis ao mesmo tempo, com as brechas DESALINHADAS.

        Vira um canal em rotação que o jogador atravessa. Difícil e
        completamente determinístico: nenhuma esquiva depende de sorte.
        """
        orbs: List[TriadOrb] = []
        origens = [self._actor_origin_of(_CROWN_ACTOR)]
        origens += [(h.center_x, h.center_y) for h in self.heads]
        passo = math.tau / _PULSO_SLOTS
        cor = self._palette(_ATK_UNISSONO)
        base = random.randrange(_PULSO_SLOTS)
        for i, (ox, oy) in enumerate(origens):
            # Desalinhamento deliberado: cada anel abre a brecha noutro setor.
            inicio = (base + i * (_PULSO_SLOTS // 3)) % _PULSO_SLOTS
            brecha = {(inicio + k) % _PULSO_SLOTS for k in range(_UNISSONO_GAP)}
            orbs.extend(
                TriadOrb(ox, oy, OrbBehavior.RING, angle=j * passo, color=cor)
                for j in range(_PULSO_SLOTS)
                if j not in brecha
            )
        return orbs

    def _fire_diluvio(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Chuva de tela cheia com uma FAIXA SEGURA — a saída é anunciada pela
        própria ausência de esferas, e ela desliza a cada uso."""
        ox, oy = self._actor_origin_of(_CROWN_ACTOR)
        sw, sh = float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT)
        faixas = self._lanes(_DILUVIO_COUNT, sw * 0.08, sw * 0.92, _LANE_JITTER)
        # Janela contígua de faixas livres: contígua para ser um CORREDOR, não
        # buracos espalhados que o jogador não consegue ligar em uma rota.
        inicio = random.randrange(0, max(1, _DILUVIO_COUNT - _DILUVIO_SAFE_LANES))
        livres = set(range(inicio, inicio + _DILUVIO_SAFE_LANES))
        cor = self._palette(_ATK_DILUVIO)
        topo = sh * _CHUVA_TOPO[0]
        return [
            make_rain(ox, oy, (alvo, topo), cor, birth=0.30 + i * 0.04)
            for i, alvo in enumerate(faixas)
            if i not in livres
        ]

    def _fire_convergencia(self, _player_pos: tuple[float, float]) -> List[TriadOrb]:
        """Recolhe as esferas soltas da arena e as devolve num estouro radial.

        **Recompensa retroativa:** quem limpou as âncoras leva um estouro fraco.
        O ataque cobra pelo que o jogador deixou vivo, então limpar a arena deixa
        de ser opcional e vira leitura de risco.
        """
        recolhidas = 0
        for orb in self._orbs:
            if not orb.dead:
                orb.begin_death()
                recolhidas += 1
        self._orbs.clear()

        total = max(_CONVERGENCIA_MIN, min(_PULSO_SLOTS + 6, _CONVERGENCIA_MIN + recolhidas))
        ox, oy = self._actor_origin_of(_CROWN_ACTOR)
        passo = math.tau / total
        giro = random.uniform(0.0, passo)
        cor = self._palette(_ATK_CONVERGENCIA)
        self._emit_shake(0.25, 5)
        return [
            TriadOrb(ox, oy, OrbBehavior.RING, angle=giro + i * passo, color=cor)
            for i in range(total)
        ]

    def _actor_origin_of(self, actor: int) -> tuple[float, float]:
        if actor == _CROWN_ACTOR:
            cx, cy = pmap.CORE_CENTER
            return self.x + cx, self.y + cy
        head = self.heads[actor]
        return head.center_x, head.center_y

    def _palette(self, ataque: str | None = None) -> tuple[int, int, int]:
        """Cor das esferas: ciano até a Fase 2, LARANJA na 3 — com o tom do ataque.

        É aqui que a virada da Fase 3 se anuncia. O corpo do boss NÃO fica
        laranja permanente (como o plano original sugeria) porque laranja é o
        telégrafo do wind-up — deixá-lo sempre aceso apagaria a informação. A
        fase muda a cor do que ELE produz, não do que ele é.

        Sobre essa base, cada ataque desloca o MATIZ um pouco (`_ATK_TINT`), e o
        mesmo deslocamento vale para o laranja da Fase 3 — o vocabulário de cor é
        um só, a família é que muda. Sem `ataque`, devolve a cor da família pura:
        é o que a Sentença usa, porque ali a coreografia é a assinatura e ela não
        pertence a nenhum dos dez ataques.
        """
        base = pmap.ORANGE if self._phase >= 3 else pmap.CYAN
        return pmap.tinted(base, _ATK_TINT.get(ataque or "", 0.0))

    def _apply_phase(self) -> None:
        """Liga o que muda ao entrar numa fase. Chamado UMA vez, na virada.

        Fase 2 aperta a regeneração e alonga o respiro (a "Inspiração", que é
        respiro E aviso de combo). Fase 3 DERRUBA o portão: as Vozes deixam de
        ser alvo e passam a orbitar como atacantes puras.
        """
        pace = 1.0 / max(0.5, self.difficulty_multiplier)
        agg = max(0.5, self.aggressiveness_multiplier)
        if self._phase == 2:
            self.gate.regen_delay = 4.5 * pace
            self._breather = max(_BREATHER_FLOOR, _BREATHER_PHASE2 / agg)
        elif self._phase >= 3:
            self.gate.disable()
            self._breather = max(_BREATHER_FLOOR, _BREATHER_PHASE3 / agg)
            for head in self.heads:
                head.enter_orbiting()

    def _update_orbit(self, dt: float) -> None:
        """Fase 3: as Vozes orbitam a Coroa, respirando o raio.

        Reusa a ideia do `SegmentNetwork` do Overlord — giro e respiração
        acoplados, tudo lendo o mesmo relógio, para o conjunto parecer uma
        máquina só e não três peças soltas.
        """
        self._orbit_t += dt
        raio = Config.SCREEN_WIDTH * _ORBIT_RADIUS
        raio *= 1.0 + _ORBIT_BREATH * math.sin(self._orbit_t * 0.9)
        base_x, base_y = pmap.CROWN_HEAD_CENTER
        for i, head in enumerate(self.heads):
            ang = self._orbit_t * _ORBIT_SPEED + i * math.pi
            head.offset_x = base_x + math.cos(ang) * raio
            head.offset_y = base_y + math.sin(ang) * raio * 0.62

    # ── A SENTENÇA ───────────────────────────────────────────────────────────
    def _check_phase_gate(self) -> None:
        """Dispara a Sentença nos 66% e 33% do HP da Coroa.

        Gate de HP, não de tempo: é o JOGADOR quem provoca a virada, e é isso que
        faz a transição parecer consequência em vez de um relógio arbitrário.
        """
        if self._sent_count >= 2 or self.max_health <= 0:
            return
        ratio = self.health / self.max_health
        limiar = self.PHASE2_THRESHOLD if self._sent_count == 0 else self.PHASE3_THRESHOLD
        if ratio <= limiar:
            self._begin_sentenca()

    def _begin_sentenca(self) -> None:
        """A Sentença REMONTA o boss antes de executar a coreografia.

        As Vozes voltam ao corpo mesmo destruídas. Duas razões:

        * **Ficção.** É o momento em que o chefe se desmonta no espaço e volta
          numa postura nova — remontar inteiro é o que a transição significa.
        * **Mecânica.** Sem isso, um jogador que chegou ao gate com as duas
          derrubadas assiste a uma coreografia com feixes saindo de cabeças que
          não estão lá (visto em playtest: "as cabeças não apareceram"), e a
          assinatura do boss degrada justo no momento em que ela deveria
          impressionar.

        A convergência da luta é preservada: `restore_all` conta como retorno
        normal, então o HP devolvido segue a mesma escada decrescente.
        """
        self.gate.restore_all()
        self._sync_heads()
        self._state = _SENTENCA
        self._sent_t = 0.0
        self._sent_casters.clear()
        self._sent_beams.clear()
        self._pulse_left = 0
        self._pulse_flash = 0.0
        self._clear_telegraph()
        # A agenda é montada AQUI, e não no import, porque depende da resolução
        # lógica em vigor (§12 — o jogo roda de 576p a 1080p) e da escala desta
        # ocorrência. São duas montagens por luta: custo irrelevante.
        escala = self._sent_scale()
        self._sent_schedule, self._sent_fim = score.build_schedule(
            float(Config.SCREEN_WIDTH), float(Config.SCREEN_HEIGHT), escala
        )
        self._sent_next = 0
        self._act_state = _ACT_BREATHER
        self._act_timer = self._breather
        self._emit_shake(0.5, 7)

    def _sent_scale(self) -> float:
        """A 2ª ocorrência roda mais RÁPIDA — nunca mais densa."""
        return score.SPEEDUP if self._sent_count >= 1 else 1.0

    def _update_sentenca(self, dt: float) -> None:
        self._sent_t += dt
        sh = float(Config.SCREEN_HEIGHT)

        # O corpo sobe ao topo-centro e fica lá: durante a coreografia ele é
        # cenário intangível, e as cabeças é que ocupam a arena.
        alvo_x, alvo_y = self._home_x, sh * _SENT_BOSS_Y
        self.x += (alvo_x - self.x) * min(1.0, 3.0 * dt)
        self.y += (alvo_y - self.y) * min(1.0, 3.0 * dt)

        self._launch_due()
        self._advance_casters(dt)

        if self._sent_t >= self._sent_fim:
            self._end_sentenca()

    def _launch_due(self) -> None:
        """Dispara os tiros cujo instante venceu. A agenda é ordenada, então um
        índice basta de sentinela — nada de varrer a lista inteira por frame."""
        agenda = self._sent_schedule
        escala = self._sent_scale()
        while self._sent_next < len(agenda) and agenda[self._sent_next][0] <= self._sent_t:
            self._launch_shot(agenda[self._sent_next][1], escala)
            self._sent_next += 1

    def _launch_shot(self, shot: "score.Shot", escala: float) -> None:
        """Materializa a cabeça e amarra o feixe a ela.

        A origem e o ângulo do feixe são os MÉTODOS do caster, não valores: é
        assim que a cabeça leva o feixe quando desliza ou gira, em vez de os dois
        andarem em relógios separados. A boca (`muzzle`) sai da arte, então o
        feixe nasce na frente do rosto e não no meio do espaço negativo do PNG.
        """
        carga, letal = score.scaled_shot(shot, escala)
        head = self.heads[shot.voice] if shot.voice is not None else None
        caster = TriadCaster(
            head.part_key if head is not None else shot.part,
            shot.x,
            shot.y,
            shot.aim,
            carga,
            letal,
            path=shot.path,
            swing=shot.swing,
            head=head,
        )
        self._sent_casters.append(caster)
        self._emit_beam(
            TriadBeam(
                caster.muzzle,
                caster.angle,
                charge_time=carga,
                active_time=letal,
                color=self._palette(),
            )
        )

    def _advance_casters(self, dt: float) -> None:
        """Avança os casters, copia a pose para as Vozes e recolhe os mortos."""
        ocupadas: set[int] = set()
        i = 0
        while i < len(self._sent_casters):
            caster = self._sent_casters[i]
            caster.update(dt)
            head = caster.head
            if head is not None and not caster.dead:
                # A conversão mundo→offset é do boss, que é quem conhece o (x, y)
                # dele; o caster não escreve no estado de um objeto irmão (§1).
                head.place(caster.x, caster.y, self.x, self.y)
                head.aim = caster.aim
                ocupadas.add(head.slot)
            if caster.dead:
                self._sent_casters[i] = self._sent_casters[-1]
                self._sent_casters.pop()
                continue
            i += 1

        # Voz sem tiro em curso volta para o soquete e desfaz a pose de mira. Ela
        # fica ali de espectadora enquanto os ecos trabalham — voltar ao corpo é
        # o que faz a reabertura do fecho ler como "as cabeças voltaram".
        for i, head in enumerate(self.heads):
            if head.slot in ocupadas:
                continue
            head.rest_pose()
            head.attacking = False
            casa = self._home_offsets[i]
            vel = min(1.0, 4.2 * dt)
            head.offset_x += (casa[0] - head.offset_x) * vel
            head.offset_y += (casa[1] - head.offset_y) * vel

    def _emit_beam(self, beam: TriadBeam) -> None:
        self._pending_beams.append(beam)
        self._sent_beams.append(beam)

    def _fade_beams(self) -> None:
        for beam in self._sent_beams:
            beam.begin_fade()
        self._sent_beams.clear()

    def _end_sentenca(self) -> None:
        self._fade_beams()
        self._sent_casters.clear()
        self._sent_count += 1
        self._phase = min(3, self._phase + 1)
        self._apply_phase()
        self._state = _ACTIVE
        for i, head in enumerate(self.heads):
            head.offset_x, head.offset_y = self._home_offsets[i]
            head.rest_pose()
            head.attacking = False
        # Entra na fase nova por um RESPIRO, nunca por um ataque imediato: a
        # virada precisa de um instante de silêncio para ser lida como virada.
        self._act_state = _ACT_BREATHER
        self._act_timer = self._breather
        self._emit_shake(0.3, 5)

    def _emit_shake(self, duration: float, intensity: int) -> None:
        if self._bus is None:
            return
        from ....events import game_events as events

        self._bus.emit(events.ScreenShake(intensity=intensity, duration=duration))

    # ── Render ───────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o boss. Sem efeito colateral (§3): só lê estado montado no update."""
        if self.dead:
            return

        origin = self._blit_origin()

        # ORDEM DE CAMADAS: tronco/Coroa primeiro (embaixo), depois as laterais.
        # Medido: as partes só se sobrepõem em 2 pixels, e as duas ordens
        # reproduzem o `Imagem_Boss_Completo_Exemplo.png` com ZERO divergência
        # visível — a arte foi desenhada para não depender de empilhamento. A
        # ordem fica fixa aqui mesmo assim, porque as fases seguintes deslocam as
        # cabeças (a Sentença manda as laterais para as bordas) e aí a
        # sobreposição passa a existir de verdade.
        white = self._hit_flash > 0.0
        crown_frame = self._crown.frame(
            self._frame_index, self._crown_attacking, white=white
        )
        if crown_frame is not None:
            surface.blit(crown_frame, origin)

        for head in self.heads:
            head.draw(surface, origin)

        self._draw_pulse(surface)

        for caster in self._sent_casters:
            caster.draw(surface)
        self._draw_health_bar(surface)
        self._draw_miss_indicator(surface)

    def _draw_pulse(self, surface: pygame.Surface) -> None:
        """A batida do Pulso, vista no núcleo do peito. `draw` só lê (§3).

        É o metrônomo do ataque: um anel sai do núcleo a cada batida e o próprio
        núcleo acende junto. Sem isso o Pulso contínuo lia como "anéis chegando
        sem motivo"; com isso o jogador vê a fonte pulsar e antecipa o compasso
        em vez de reagir a cada anel do zero.

        O `_pulse_flash` decai no update entre 1 e 0 ao longo de uma batida, e é
        ele que dá o raio e o brilho — então a animação acompanha o compasso
        real, e não um relógio próprio que poderia dessincronizar dele (§14).
        """
        if self._pulse_flash <= 0.01:
            return
        cx, cy = pmap.CORE_CENTER
        px, py = int(self.x + cx), int(self.y + cy)
        p = 1.0 - self._pulse_flash          # 0 no instante da batida
        # No tom do Pulso: a pulsação do núcleo e os anéis que saem dele são o
        # mesmo evento, e cores diferentes os leriam como coisas distintas.
        cor = self._palette(_ATK_PULSO)
        raio = int(pmap.SIDE_HEAD_RADIUS * (0.35 + 1.5 * p))
        if raio >= 2:
            pygame.draw.circle(
                surface, cor, (px, py), raio, max(1, int(3 * self._pulse_flash))
            )
        nucleo = int(pmap.SIDE_HEAD_RADIUS * 0.55 * self._pulse_flash)
        if nucleo >= 1:
            pygame.draw.circle(surface, pmap.GEM_WHITE, (px, py), nucleo)

    def _s(self, value: float) -> int:
        return int(value * self._ui_scale)

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        """Barra da Coroa ladeada por um pip por Voz.

        Os pips são o tutorial da luta: eles esvaziam quando a lateral cai e
        VOLTAM A ENCHER durante a rematerialização. É assim que o jogador
        descobre sozinho que a brasa é atacável e que o portão está fechando —
        sem uma linha de texto.
        """
        if self._state == _ENTERING or self.health <= 0:
            return

        bar_w, bar_h = self._s(260), self._s(9)
        pip_w = self._s(14)
        pip_gap = self._s(6)
        total_w = bar_w + 2 * (pip_w + pip_gap)
        bx = int(Config.SCREEN_WIDTH / 2 - total_w / 2) + pip_w + pip_gap
        by = self._s(24)

        # Barra da Coroa. Acesa quando a janela está aberta, dessaturada quando
        # não — vulnerabilidade lida de relance, sem ler os pips.
        vulnerable = self.gate.crown_vulnerable
        hp_ratio = max(0.0, self.health / self.max_health)
        fill = pmap.CYAN if vulnerable else pmap.CYAN_DIM
        pygame.draw.rect(surface, pmap.CYAN_DARK, (bx, by, bar_w, bar_h))
        pygame.draw.rect(surface, fill, (bx, by, int(bar_w * hp_ratio), bar_h))
        border = pmap.CYAN if vulnerable else pmap.CYAN_DIM
        pygame.draw.rect(surface, border, (bx, by, bar_w, bar_h), 1)

        for slot, side in ((LEFT, -1), (RIGHT, 1)):
            px = bx - pip_w - pip_gap if side < 0 else bx + bar_w + pip_gap
            self._draw_pip(surface, px, by, pip_w, bar_h, slot)

    def _draw_pip(
        self, surface: pygame.Surface, px: int, py: int, w: int, h: int, slot: int
    ) -> None:
        head = self.heads[slot]
        pygame.draw.rect(surface, pmap.CYAN_DARK, (px, py, w, h))

        if self.gate.is_solid(slot):
            level, color = head.hp_ratio, pmap.CYAN
        elif self.gate.is_rematerializing(slot):
            # Enchendo: é o portão se fechando, e o aviso para suprimir a brasa.
            level, color = self.gate.remat_progress(slot), pmap.ORANGE
        else:
            level, color = 0.0, pmap.CYAN_DIM

        if level > 0.0:
            filled = max(1, int(h * level))
            pygame.draw.rect(surface, color, (px, py + h - filled, w, filled))
        pygame.draw.rect(surface, color, (px, py, w, h), 1)

    def _draw_miss_indicator(self, surface: pygame.Surface) -> None:
        if self._miss_timer <= 0.0:
            return
        alpha = int(255 * (self._miss_timer / self._MISS_TIME))
        font = get_font(max(8, self._s(18)))
        label = font.render("MISS", True, pmap.CYAN)
        label.set_alpha(alpha)
        surface.blit(label, label.get_rect(center=(int(self._miss_pos[0]), int(self._miss_pos[1]))))


# Despacho de ataque por MAPA (§5): nome → método. Ataque novo entra aqui e na
# constante do nome; o `_fire_one` não muda.
_FIRE_TABLE = {
    _ATK_CADENCIA: TriadBoss._fire_cadencia,
    _ATK_CHUVA: TriadBoss._fire_chuva,
    _ATK_PULSO: TriadBoss._fire_pulso_arg,
    _ATK_PAREDE: TriadBoss._fire_parede,
    _ATK_ANCORA: TriadBoss._fire_ancora,
    _ATK_CORRENTE: TriadBoss._fire_corrente,
    _ATK_ERRATICO: TriadBoss._fire_erratico,
    _ATK_UNISSONO: TriadBoss._fire_unissono,
    _ATK_DILUVIO: TriadBoss._fire_diluvio,
    _ATK_CONVERGENCIA: TriadBoss._fire_convergencia,
}
