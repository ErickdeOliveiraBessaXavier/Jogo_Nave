"""A partitura da SENTENÇA — quem dispara, de onde, para onde e quando.

Dado puro e funções puras: nada aqui importa o boss, toca som ou desenha. É o
que permite testar a coreografia inteira (duração, densidade, saída) sem
instanciar o jogo (§16). O boss lê `build_schedule` e executa.

## O roteiro é DADO, não código espalhado

`SCORE` é a partitura: `(instante, construtor)`. Cada construtor devolve uma
lista de `Shot` — uma cabeça, uma mira, um feixe. O motor não conhece o nome de
padrão nenhum; padrão novo é uma função e uma linha na partitura (§5). O FIM é
**derivado** da partitura, nunca digitado: enquanto foi constante à parte, mudar
um tempo deixava a coreografia terminando depois do fim do estado.

## Por que os padrões são estes

Um feixe aqui é uma RETA INTEIRA da arena, e isso descarta metade do vocabulário
óbvio. "Parede de feixes paralelos com uma brecha" **não funciona**: N retas
paralelas cortam a tela em N+1 faixas e *todas* são seguras, então o jogador só
precisa parar em qualquer vão — o padrão parece denso e não pede nada. O que
funciona com retas é:

  * **FECHAR** — feixes que se aproximam e param antes de encostar (TESOURA,
    GAIOLA). A região sobrevivente encolhe, e é o encolhimento que exige leitura.
  * **GIRAR** — a reta varre em ângulo (LEQUE, CERCO) e as fatias giram junto.
    Ficar parado deixa de ser opção sem nenhum feixe precisar ser injusto.
  * **PISCAR** — feixes curtos em sequência (ONDA, CRUZADO), onde a brecha é no
    TEMPO e não no espaço: passa-se por onde o feixe acabou de sair.

As sete entradas alternam esses três eixos de propósito. Repetir o mesmo eixo com
posições diferentes é a definição de padrão sem variedade.

## A cabeça leva o feixe

`path`/`swing` recebem o progresso normalizado da janela LETAL. O caster lê os
dois todo frame e o feixe lê o caster — então a cabeça nunca fica parada num
lugar disparando de outro, que era o defeito da versão anterior (o feixe varria a
arena de 0,20 a 0,43 da altura enquanto a cabeça ficava fixa em 0,45).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .triad_resonance import LEFT, RIGHT

# Chamada: o boss se desmonta e ninguém dispara ainda.
INTRO: float = 1.10
# Depois do último feixe morrer, antes de a fase nova começar.
TAIL: float = 0.90
# Fator da 2ª ocorrência: mais RÁPIDA, nunca mais densa. Multiplica os instantes
# E as durações, então a coreografia acelera inteira em vez de comprimir os
# intervalos e deixar os feixes se acumulando.
SPEEDUP: float = 0.8

# ── Folga entre salvas, por dificuldade ───────────────────────────────────────
# A troca de uma formação para a seguinte é o momento mais difícil da coreografia:
# o jogador ainda está saindo da anterior quando a nova acende. Os tempos escritos
# na partitura são os de HARDCORE — é o que o playtest aprovou como limite. Nas
# dificuldades menores, cada salva entra um pouco mais tarde que a anterior, o que
# ALARGA o intervalo sem mexer no interior de salva nenhuma (as durações, as
# cargas e as varreduras continuam idênticas — só a arena tem mais tempo de
# esvaziar entre uma e outra).
#
# Escalonado por `aggressiveness_multiplier`, que é o eixo que o jogo já usa para
# "quão rápido o inimigo aperta": 1,20 (Hardcore) e acima não ganham folga; 0,85
# (Casual) ganha a folga cheia; Normal (1,00) fica no meio.
FOLGA_MAX: float = 0.70
_AGG_DURO = 1.20
_AGG_FACIL = 0.85


def folga_por_agressividade(aggressiveness: float) -> float:
    """Segundos extras acumulados por salva, a partir da agressividade."""
    faixa = _AGG_DURO - _AGG_FACIL
    p = (_AGG_DURO - aggressiveness) / faixa if faixa > 0 else 0.0
    return FOLGA_MAX * max(0.0, min(1.0, p))

Ponto = Tuple[float, float]


@dataclass(frozen=True)
class Shot:
    """Uma cabeça que aparece, mira e dispara UM feixe.

    `voice` amarra o tiro a uma das duas Vozes reais em vez de a um eco: é o que
    mantém a ficção de que a coreografia abre e fecha com as cabeças do próprio
    boss. Sem ele, todo tiro é um eco descartável.
    """

    delay: float
    charge: float
    lethal: float
    aim: float = 0.0
    x: float = 0.0
    y: float = 0.0
    part: str = "right"
    voice: Optional[int] = None
    path: Optional[Callable[[float], Ponto]] = None
    swing: Optional[Callable[[float], float]] = None

    def end(self) -> float:
        """Instante (relativo ao início da salva) em que este feixe para de ferir."""
        return self.delay + self.charge + self.lethal


# ── Cargas: a janela de reação ────────────────────────────────────────────────
# A carga é o TELÉGRAFO — o tempo entre "aparece" e "machuca". Reação humana a um
# estímulo visual novo é ~0,25s, e depois ainda é preciso ANDAR até um lugar
# seguro. Uma carga de 0,45s (o valor da primeira versão) deixava ~0,20s de
# caminhada, ou 40px na nave mais lenta do elenco — menos que o corpo dela.
#
# Dois patamares, e o motivo de haver dois: quem varre a arena inteira precisa de
# mais aviso que quem pisca num lugar só.
_CARGA_PESADA = 0.95         # varreduras longas: tesoura, leque, gaiola, cerco
_CARGA_RAPIDA = 0.85         # cascatas curtas: onda, cruzado

# ── Teto de velocidade de varredura ───────────────────────────────────────────
# **Nenhum feixe pode varrer mais rápido do que a nave anda.** Um feixe é uma
# reta inteira da arena: não dá para deixá-lo passar nem contorná-lo, só sair da
# frente. Se ele se desloca mais rápido que o jogador, quem estiver do lado
# errado está morto no instante em que ele nasce, tenha jogado como tenha.
#
# Era o defeito de fundo do primeiro corte, e ele não aparecia olhando o padrão
# — só simulando. Medido na versão anterior: a cruz do uníssono corria a
# 404 px/s e o giro do cruzado varria a ponta do feixe a ~995 px/s, contra os
# 200 px/s da nave mais lenta do elenco (`speed_mult` 0,80).
#
# 110 px/s = 55% da nave mais lenta. A folga não é luxo: o jogador também está
# desviando de OUTRA coisa enquanto sai da frente desta, e raramente pode gastar
# o vetor de movimento inteiro num feixe só.
#
# Vale para os dois tipos de varredura. Para um giro, o que conta é a velocidade
# TANGENCIAL na ponta útil do feixe — girar devagar perto do pivô ainda chicoteia
# longe dele. Cobrado por `test_nenhum_feixe_varre_mais_rapido_que_a_nave`.
SWEEP_CAP: float = 110.0


def varre(
    de: float, para: float, charge: float, lethal: float
) -> Callable[[float], float]:
    """Percurso cujo trecho LETAL vai exatamente de `de` a `para`.

    A partitura declara **onde o feixe fere**; o trecho da carga é extrapolado
    para trás, na mesma velocidade. É esse pedaço extrapolado que resolve o
    "impossível de escapar": durante a carga o feixe já está em movimento, então
    a direção e a velocidade da varredura são informação pública antes de
    qualquer dano. Antes, o telégrafo mostrava só a posição inicial — o jogador
    se julgava seguro a 80px dali e era varrido por uma trajetória que não tinha
    como conhecer.

    **Linear de propósito**, e não suavizado: velocidade constante é
    extrapolável a olho. Um feixe que acelera no meio do percurso não dá para
    prever, e prever é o que se pede ao jogador aqui.
    """
    fracao = charge / (charge + lethal)
    inicio = de - (para - de) * fracao / (1.0 - fracao)
    return lambda p: inicio + (para - inicio) * p


# ── Os padrões ────────────────────────────────────────────────────────────────
def tesoura(sw: float, sh: float) -> List[Shot]:
    """FECHAR — as duas Vozes varrem uma contra a outra e PARAM antes de encostar.

    Abertura com as cabeças do próprio boss: é ele se desmontando no espaço. A
    faixa que sobra entre os dois feixes é o corredor. Convergir até o encontro
    não deixaria saída, e ataque sem saída não é dificuldade, é morte agendada.
    """
    carga, letal = _CARGA_PESADA, 2.10
    alto = varre(0.16, 0.47, carga, letal)
    baixo = varre(0.96, 0.65, carga, letal)
    return [
        Shot(
            delay=0.0, charge=carga, lethal=letal, aim=0.0, voice=LEFT,
            path=lambda p: (sw * 0.085, sh * alto(p)),
        ),
        Shot(
            delay=0.0, charge=carga, lethal=letal, aim=math.pi, voice=RIGHT,
            path=lambda p: (sw * 0.915, sh * baixo(p)),
        ),
    ]


def onda(sw: float, sh: float) -> List[Shot]:
    """PISCAR — oito ecos no alto disparando para baixo em cascata.

    A brecha é no TEMPO: cada feixe vive pouco e a cascata anda para a direita.
    Atravessa-se por onde ela já passou, ou correndo à frente dela. É a salva que
    ensina o vocabulário do eco — muitas cabeças, uma ideia.
    """
    # Oito faixas com o passo escolhido para NENHUMA cair em 0,5 da largura: uma
    # cabeça bem no meio pousa em cima do halo do boss e as duas viram uma
    # mancha só. Variedade de padrão não pode custar legibilidade de sprite.
    #
    # **Cada faixa VARRE**, e todas para o MESMO lado. Sem varrer, a salva é um
    # pente de retas paralelas, e um pente de retas não pede nada: os vãos entre
    # elas são todos seguros e o jogador atravessa a salva inteira parado.
    #
    # O sentido uniforme é a parte que custou uma rodada de simulação. Com as
    # faixas varrendo em sentidos ALTERNADOS os pares vizinhos viravam PINÇAS
    # que fecham até zero — e a pinça mais externa fechava contra a parede da
    # arena, com a única saída sendo uma fresta colada na borda. Quem tivesse
    # fugido da cascata para aquele lado (que é o instinto certo) morria sem ter
    # jogado errado. Varrendo todas juntas, o pente inteiro TRANSLADA: os vãos
    # não mudam de largura, e o jogador desliza com o dele.
    #
    # O pente anda para a ESQUERDA enquanto a cascata acende para a direita —
    # os dois sentidos opostos são o que impede a resposta preguiçosa de correr
    # junto com a onda.
    carga, letal = _CARGA_RAPIDA, 0.70
    faixa = sw * 0.1257
    tiros: List[Shot] = []
    for i in range(8):
        x0 = sw * 0.06 + i * faixa
        desliza = varre(x0, x0 - faixa * 0.45, carga, letal)
        tiros.append(
            Shot(
                delay=i * 0.19, charge=carga, lethal=letal, aim=math.pi / 2,
                x=x0, y=sh * 0.14,
                part="left" if i % 2 else "right",
                path=(lambda p, f=desliza: (f(p), sh * 0.14)),
            )
        )
    return tiros


def leque(sw: float, sh: float) -> List[Shot]:
    """GIRAR — seis ecos num pivô alto, abertos em leque e varrendo juntos.

    As fatias entre os feixes são o abrigo, e elas giram. Perto do pivô a fatia é
    estreita e longe é larga, então o padrão empurra o jogador para baixo — que é
    exatamente para onde ele já quer ir. Dificuldade que concorda com o instinto.
    """
    # O raio é grande de propósito. Com o pivô apertado as cabeças se empilhavam
    # numa mancha laranja sobre o corpo do boss — o padrão funcionava e não dava
    # para LER quem estava atirando de onde. Aqui a corda entre cabeças vizinhas
    # passa de 100px, então cada rosto se distingue.
    carga, letal = _CARGA_PESADA, 1.70
    px, py = sw * 0.5, sh * 0.19
    raio = sw * 0.17
    tiros: List[Shot] = []
    for i in range(6):
        # Seis braços, e não cinco: com cinco o do meio cai exatamente na
        # vertical, e a fatia mais óbvia da tela vira a única resposta.
        base = math.pi * (0.12 + i * 0.152)
        giro = varre(base - math.pi * 0.029, base + math.pi * 0.029, carga, letal)
        tiros.append(
            Shot(
                delay=0.0, charge=carga, lethal=letal, aim=base,
                part="left" if i % 2 else "right",
                swing=giro,
                path=(
                    lambda p, g=giro: (
                        px + math.cos(g(p)) * raio,
                        py + math.sin(g(p)) * raio,
                    )
                ),
            )
        )
    return tiros


def gaiola(sw: float, sh: float) -> List[Shot]:
    """FECHAR — quatro ecos fecham uma caixa e param, deixando-a habitável.

    Não é a tesoura de novo: ali a região sobrevivente é uma FAIXA e aqui é uma
    CAIXA, e o jogador tem que decidir cedo se fica dentro ou fora. As duas
    escolhas são válidas — a decisão é que é o conteúdo.
    """
    carga, letal = _CARGA_PESADA, 2.00
    cima = varre(0.16, 0.44, carga, letal)
    baixo = varre(0.96, 0.68, carga, letal)
    esquerda = varre(0.05, 0.22, carga, letal)
    direita = varre(0.95, 0.78, carga, letal)
    return [
        Shot(
            delay=0.0, charge=carga, lethal=letal, aim=0.0, part="right",
            path=lambda p: (sw * 0.05, sh * cima(p)),
        ),
        Shot(
            delay=0.0, charge=carga, lethal=letal, aim=math.pi, part="left",
            path=lambda p: (sw * 0.95, sh * baixo(p)),
        ),
        Shot(
            delay=0.12, charge=carga, lethal=letal, aim=math.pi / 2, part="left",
            path=lambda p: (sw * esquerda(p), sh * 0.06),
        ),
        Shot(
            delay=0.12, charge=carga, lethal=letal, aim=-math.pi / 2, part="right",
            path=lambda p: (sw * direita(p), sh * 0.96),
        ),
    ]


def cerco(sw: float, sh: float) -> List[Shot]:
    """GIRAR — oito ecos em anel mirando o centro, com o anel inteiro girando.

    As oito não miram o centro: miram TANGENTE a um círculo pequeno em volta
    dele, todas no mesmo sentido. O desenho vira um catavento com um OLHO no
    meio — e o olho é seguro.

    A versão que mirava o centro exato tinha o defeito oposto ao pretendido: oito
    retas por um mesmo ponto fatiam a arena em dezesseis setores de 22,5°, o
    ponto de encontro é o lugar mais letal da tela, e ele fica bem no meio da
    arena. Simulado, era a única salva que ainda matava — o jogador era espremido
    entre duas retas convergentes sem largura para caber. Tangenciando, os
    setores lá fora dobram de largura (as retas deixam de ser concorrentes) e o
    centro passa de armadilha a abrigo. O anel ainda gira, e a leitura fica mais
    clara, não menos.
    """
    carga, letal = 1.00, 1.70
    cx, cy = sw * 0.5, sh * 0.58
    raio = sh * 0.36
    olho = sh * 0.13          # raio do círculo tangente — o abrigo do meio
    desvio = math.asin(max(-1.0, min(1.0, olho / raio)))
    tiros: List[Shot] = []
    for i in range(8):
        base = i * math.tau / 8
        giro = varre(base, base + math.pi * 0.055, carga, letal)
        tiros.append(
            Shot(
                delay=0.0, charge=carga, lethal=letal, aim=base + math.pi + desvio,
                part="left" if i % 2 else "right",
                swing=(lambda p, g=giro: g(p) + math.pi + desvio),
                path=(
                    lambda p, g=giro: (
                        cx + math.cos(g(p)) * raio,
                        cy + math.sin(g(p)) * raio,
                    )
                ),
            )
        )
    return tiros


def cruzado(sw: float, sh: float) -> List[Shot]:
    """PISCAR — cascata diagonal dos DOIS lados, intercalada.

    A onda outra vez, mas em diagonal e vindo de dois sentidos que se cruzam. É o
    trecho mais frenético de propósito: vem logo antes do fecho.

    **Sem giro, e a razão é geométrica.** Um giro de meio segundo perto do bocal
    é um chicote na outra ponta: os feixes nascem na borda da arena, e ±0,22 rad
    em 0,65s varriam a ponta útil a ~995 px/s — cinco vezes a nave. Aqui a mordida
    tem que vir do TEMPO, que é a identidade da salva: as duas diagonais formam
    uma treliça cujas células abrem e fecham conforme os feixes acendem e apagam,
    e o jogador atravessa pela célula certa no instante certo. Reta parada com
    ritmo é justa; reta rápida não tem resposta.
    """
    carga, letal = _CARGA_RAPIDA, 0.55
    passo = 0.19
    esq = math.pi * 0.22
    dir_ = math.pi * 0.78
    tiros: List[Shot] = []
    for i in range(4):
        tiros.append(
            Shot(
                delay=i * passo, charge=carga, lethal=letal, aim=esq,
                x=sw * 0.05, y=sh * (0.18 + i * 0.20), part="right",
            )
        )
        tiros.append(
            Shot(
                delay=passo * 0.5 + i * passo, charge=carga, lethal=letal, aim=dir_,
                x=sw * 0.95, y=sh * (0.28 + i * 0.20), part="left",
            )
        )
    return tiros


def unissono(sw: float, sh: float) -> List[Shot]:
    """FECHAR + GIRAR — a cruz móvel das Vozes mais dois ecos negando as diagonais.

    O fecho devolve o palco às cabeças do boss: elas viram uma cruz que caminha
    pela arena enquanto dois ecos fecham os cantos de baixo. Denso, curto e com
    saída — a última coisa que o jogador vê antes da fase nova.
    """
    carga, letal = _CARGA_PESADA, 1.90
    coluna = varre(0.34, 0.50, carga, letal)
    linha = varre(0.82, 0.53, carga, letal)
    return [
        Shot(
            delay=0.0, charge=carga, lethal=letal, aim=math.pi / 2, voice=LEFT,
            path=lambda p: (sw * coluna(p), sh * 0.06),
        ),
        Shot(
            delay=0.0, charge=carga, lethal=letal, aim=0.0, voice=RIGHT,
            path=lambda p: (sw * 0.05, sh * linha(p)),
        ),
        Shot(
            delay=0.30, charge=carga, lethal=letal * 0.75, aim=-math.pi * 0.30,
            x=sw * 0.10, y=sh * 0.95, part="right",
        ),
        Shot(
            delay=0.30, charge=carga, lethal=letal * 0.75, aim=-math.pi * 0.70,
            x=sw * 0.90, y=sh * 0.95, part="left",
        ),
    ]


# A partitura: sete salvas alternando FECHAR / PISCAR / GIRAR.
#
# Os instantes deixam o telégrafo da salva seguinte acender ~0,5s antes de a
# anterior parar de ferir, e nunca menos: o jogador precisa de um trecho de
# aviso com a arena já limpa. Encavalar mais que isso é o que fazia a sequência
# parecer "rápida demais" — havia sempre algo novo nascendo enquanto ele ainda
# desviava do anterior, e o aviso virava ruído.
SCORE: Tuple[Tuple[float, Callable[[float, float], List[Shot]]], ...] = (
    (0.00, tesoura),
    (2.55, onda),
    (4.95, leque),
    (7.10, gaiola),
    (9.70, cerco),
    (11.90, cruzado),
    (13.50, unissono),
)


def build_schedule(
    sw: float, sh: float, escala: float = 1.0, folga: float = 0.0
) -> Tuple[List[Tuple[float, Shot]], float]:
    """Achata a partitura em `(instante_real, Shot)` ordenado, mais o FIM.

    `escala` multiplica instantes **e** durações. É o que faz a 2ª Sentença ser
    mais rápida sem ficar mais densa: escalar só os instantes aproximaria as
    salvas mantendo os feixes longos, e elas passariam a se sobrepor — que é
    exatamente o que a assinatura não pode fazer.

    O FIM sai do último feixe a parar de ferir, mais a dissolução e o rabo. Um
    número digitado à parte diverge da partitura na primeira vez que alguém mexe
    num tempo, e a coreografia termina depois do estado que a hospeda.
    """
    agenda: List[Tuple[float, Shot]] = []
    ultimo = 0.0
    for ordem, (inicio, construir) in enumerate(SCORE):
        # `ordem * folga` empurra cada salva um pouco mais que a anterior: o
        # efeito é somar `folga` a CADA intervalo, sem alterar nada dentro das
        # salvas. Aplicado antes da escala, então a 2ª Sentença acelera a folga
        # junto com o resto e continua sendo "mais rápida, nunca mais densa".
        atraso = inicio + ordem * folga
        for tiro in construir(sw, sh):
            quando = (INTRO + atraso + tiro.delay) * escala
            agenda.append((quando, tiro))
            ultimo = max(ultimo, (INTRO + atraso + tiro.end()) * escala)
    agenda.sort(key=lambda par: par[0])
    return agenda, ultimo + TAIL * escala


def max_sweep_speed(tiro: Shot, sw: float, sh: float) -> float:
    """Maior velocidade com que este feixe varre a arena, em px/s.

    Mora aqui, junto da partitura, para a regra e o dado não divergirem: é esta
    função que `SWEEP_CAP` limita e que o teste de convenção cobra.

    Dois modos de varrer, e os dois contam:

    * **translação** — o quanto a origem anda por segundo;
    * **giro** — a velocidade TANGENCIAL na ponta ÚTIL do feixe, que é o canto
      da arena mais distante da origem. Um giro lento no bocal é um chicote a
      600px dali, e é a ponta que alcança o jogador.

    Só o trecho LETAL é medido. A varredura da carga corre na mesma velocidade
    (é a mesma reta), mas ali ela não fere — é o telégrafo.
    """
    span = tiro.charge + tiro.lethal
    fracao = tiro.charge / span
    pior = 0.0
    passos = 60
    for k in range(passos):
        p0 = fracao + (1.0 - fracao) * k / passos
        p1 = fracao + (1.0 - fracao) * (k + 1) / passos
        dt = (p1 - p0) * span
        if dt <= 0.0:
            continue
        if tiro.path is not None:
            x0, y0 = tiro.path(p0)
            x1, y1 = tiro.path(p1)
            pior = max(pior, math.hypot(x1 - x0, y1 - y0) / dt)
        if tiro.swing is not None:
            origem = tiro.path(p0) if tiro.path is not None else (tiro.x, tiro.y)
            alcance = max(
                math.hypot(origem[0] - cx, origem[1] - cy)
                for cx in (0.0, sw)
                for cy in (0.0, sh)
            )
            pior = max(pior, abs(tiro.swing(p1) - tiro.swing(p0)) / dt * alcance)
    return pior


def scaled_shot(tiro: Shot, escala: float) -> Tuple[float, float]:
    """Carga e janela letal deste tiro no relógio real."""
    return tiro.charge * escala, tiro.lethal * escala


__all__ = [
    "INTRO",
    "TAIL",
    "SPEEDUP",
    "FOLGA_MAX",
    "folga_por_agressividade",
    "Shot",
    "SCORE",
    "build_schedule",
    "scaled_shot",
    "varre",
    "SWEEP_CAP",
    "max_sweep_speed",
]
