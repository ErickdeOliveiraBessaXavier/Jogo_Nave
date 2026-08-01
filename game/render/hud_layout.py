"""Geometria do HUD que quem DESENHA e quem TOCA precisam concordar.

Enquanto o HUD era só desenho, calcular a posição dos slots dentro do próprio
`_render_upgrades_hud` estava certo: um leitor, uma fonte. Com o toque, passam a
existir DOIS leitores — o renderer, que pinta, e o input handler, que descobre
em qual slot o dedo caiu. Recalcular a mesma geometria dos dois lados é o tipo
de duplicação que não quebra hoje e diverge em silêncio no dia em que alguém
mexer no `gap`: o slot passa a ser desenhado num lugar e acionado em outro, sem
erro nenhum para denunciar.

Mesma ideia do `RenderFrame` (§1): calcula uma vez, os dois consomem.

**Por que o layout de toque é diferente, e não só "os mesmos rects clicáveis".**
No desktop a fileira fica embaixo, no centro — o lugar mais confortável da tela,
porque o mouse chega em qualquer canto de graça. No celular esse é exatamente o
pior lugar possível: num shmup vertical a nave vive embaixo, o polegar que
pilota fica em cima dela, e a fileira ficaria debaixo da mão. O dedo cobriria os
botões que precisa ver E encostaria neles ao pilotar.

No toque a fileira vira COLUNA na borda direita, na meia-altura: fora da zona
onde o polegar de pilotagem mora, e alcançável pelo outro polegar sem soltar a
nave.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from ..core.config import config as Config

# ── Linguagem de cantos ────────────────────────────────────────────────────
#
# DOIS raios, e só dois: `PANEL` para tudo que é caixa/botão (container de
# upgrades, pausa, girar) e `SLOT` para o que mora DENTRO de um painel. Antes
# eram quatro números soltos espalhados pelo renderer — container 15, slot 8,
# pausa 12, girar 12 — e a diferença entre 12 e 15 não comunicava nada: era só
# ninguém ter olhado as peças lado a lado.
#
# O par não é arbitrário. O slot é menor porque um canto interno com o MESMO
# raio do painel que o contém lê como desalinhado: a curva de dentro parece
# maior que a de fora, já que percorre um arco menor.
PANEL_RADIUS: float = 14.0
SLOT_RADIUS: float = 8.0

# Medidas do design base (1280×720), escaladas por `ui_scale` no cálculo.
SLOT_SIZE: float = 50.0
SLOT_GAP: float = 10.0
PAD_X: float = 15.0
PAD_Y: float = 10.0
# Respiro entre a coluna de toque e a borda da tela. Encostado na borda o dedo
# escorrega para fora do canvas no meio do gesto.
TOUCH_EDGE_MARGIN: float = 14.0
# Lado do botão de pausa no toque. Maior que um slot: é o único caminho para
# pausar sem teclado, e errá-lo custa uma vida.
PAUSE_BUTTON_SIZE: float = 56.0
PAUSE_BUTTON_MARGIN: float = 16.0


@dataclass(frozen=True)
class UpgradeHudLayout:
    """Onde a fileira/coluna de upgrades cai nesta resolução e neste modo.

    `slots` vem na ordem de EXIBIÇÃO. O índice real de cada slot no loadout é
    responsabilidade de quem chama — os dois lados derivam da mesma lista
    (`upgrade_slots`), então basta percorrerem na mesma ordem.
    """

    container: pygame.Rect
    slots: tuple[pygame.Rect, ...]
    vertical: bool


def upgrade_hud_layout(
    count: int, ui_scale: float, touch_mode: bool = False
) -> UpgradeHudLayout:
    """Geometria de `count` slots de upgrade.

    Serve tanto a fileira cheia quanto os contornos do estado vazio: as duas
    ocupam a mesma posição de propósito, para serem lidas como a mesma peça de
    HUD quando o jogador enfim equipar algo.
    """

    def s(value: float) -> int:
        return int(value * ui_scale)

    slot, gap = s(SLOT_SIZE), s(SLOT_GAP)
    pad_x, pad_y = s(PAD_X), s(PAD_Y)

    if count <= 0:
        empty = pygame.Rect(0, 0, 0, 0)
        return UpgradeHudLayout(container=empty, slots=(), vertical=touch_mode)

    if touch_mode:
        container_w = slot + pad_x * 2
        container_h = count * slot + (count - 1) * gap + pad_y * 2
        container = pygame.Rect(
            Config.SCREEN_WIDTH - container_w - s(TOUCH_EDGE_MARGIN),
            (Config.SCREEN_HEIGHT - container_h) // 2,
            container_w,
            container_h,
        )
        slots = tuple(
            pygame.Rect(
                container.left + pad_x,
                container.top + pad_y + i * (slot + gap),
                slot,
                slot,
            )
            for i in range(count)
        )
        return UpgradeHudLayout(container=container, slots=slots, vertical=True)

    container_w = count * slot + (count - 1) * gap + pad_x * 2
    container_h = slot + pad_y * 2
    container = pygame.Rect(
        (Config.SCREEN_WIDTH - container_w) // 2,
        Config.SCREEN_HEIGHT - container_h,
        container_w,
        container_h,
    )
    slots = tuple(
        pygame.Rect(
            container.left + pad_x + i * (slot + gap),
            container.top + pad_y,
            slot,
            slot,
        )
        for i in range(count)
    )
    return UpgradeHudLayout(container=container, slots=slots, vertical=False)


def panel_radius(ui_scale: float) -> int:
    """Raio de caixa/botão do HUD. Fonte única — ver `PANEL_RADIUS`."""
    return int(PANEL_RADIUS * ui_scale)


def slot_radius(ui_scale: float) -> int:
    """Raio de peça DENTRO de um painel. Fonte única — ver `SLOT_RADIUS`."""
    return int(SLOT_RADIUS * ui_scale)


def container_corners(ui_scale: float, floating: bool) -> dict[str, int]:
    """Kwargs de canto do container de upgrades, conforme ONDE ele está.

    A fileira do desktop nasce colada no rodapé (`bottom == SCREEN_HEIGHT`), e
    ali arredondar embaixo é desenhar uma curva fora da tela: os dois cantos de
    baixo não existem para o jogador. Por isso o desenho original arredondava só
    em cima — estava certo para aquela âncora.

    A coluna do modo toque **flutua** a `TOUCH_EDGE_MARGIN` da borda direita, no
    meio da altura. Os quatro cantos ficam visíveis, e manter dois retos deixa a
    peça com aparência de recortada — o resto do HUD de toque (pausa, girar) é
    todo arredondado.

    Devolve kwargs em vez de um número porque é isso que `pygame.draw.rect`
    aceita para arredondar por canto, e assim o call site não precisa saber qual
    dos dois casos está em jogo.
    """
    r = panel_radius(ui_scale)
    if floating:
        return {"border_radius": r}
    return {
        "border_radius": r,
        "border_bottom_left_radius": 0,
        "border_bottom_right_radius": 0,
    }


def pause_button_rect(ui_scale: float, joystick: bool = False) -> pygame.Rect:
    """Botão de pausa do modo toque, no canto inferior ESQUERDO.

    Os outros três cantos já têm dono (score em cima à esquerda, vidas em cima à
    direita, combo embaixo à direita) e a coluna de upgrades ocupa a borda
    direita. Sobra este — que também é o canto mais longe da coluna, então errar
    a pausa não ativa um upgrade e vice-versa.

    **Com o joystick ligado, ele sobe para a borda esquerda na meia-altura.** O
    direcional toma o canto inferior esquerdo, e sobrepor os dois seria trocar
    "pausei sem querer" por "parei de pilotar sem querer" — os dois no meio de
    uma esquiva.
    """
    size = int(PAUSE_BUTTON_SIZE * ui_scale)
    margin = int(PAUSE_BUTTON_MARGIN * ui_scale)
    if joystick:
        return pygame.Rect(
            margin, (Config.SCREEN_HEIGHT - size) // 2, size, size
        )
    return pygame.Rect(
        margin, Config.SCREEN_HEIGHT - size - margin, size, size
    )


# ── Joystick virtual (modo celular) ────────────────────────────────────────
#
# Raio do desenho e do knob, em px do design base. 68 dá um disco de 136px —
# grande o bastante para o polegar não precisar de pontaria, pequeno o bastante
# para não comer o canto da arena onde inimigos aparecem.
JOYSTICK_RADIUS: float = 68.0
JOYSTICK_KNOB_RADIUS: float = 30.0
JOYSTICK_MARGIN: float = 24.0
# A ZONA DE TOQUE é maior que o desenho. Errar o direcional por poucos pixels e
# a nave não responder é a pior falha possível num controle de toque, e com alvo
# do tamanho exato do desenho isso acontece o tempo todo — o dedo cobre a peça
# que ele está tentando acertar.
JOYSTICK_ACTIVATION_SCALE: float = 1.45

# Botão de girar a nave (o `Ctrl` do teclado, que no celular não existe).
ROTATE_BUTTON_SIZE: float = 64.0
ROTATE_BUTTON_MARGIN: float = 20.0


def joystick_center(ui_scale: float) -> tuple[int, int]:
    """Centro do direcional: canto inferior ESQUERDO."""
    r = int(JOYSTICK_RADIUS * ui_scale)
    m = int(JOYSTICK_MARGIN * ui_scale)
    return (m + r, Config.SCREEN_HEIGHT - m - r)


def joystick_radius(ui_scale: float) -> int:
    """Raio do DESENHO (o knob percorre este raio)."""
    return int(JOYSTICK_RADIUS * ui_scale)


def joystick_activation_radius(ui_scale: float) -> int:
    """Raio que CAPTURA o toque — maior que o desenho, ver a constante."""
    return int(JOYSTICK_RADIUS * JOYSTICK_ACTIVATION_SCALE * ui_scale)


def joystick_knob_radius(ui_scale: float) -> int:
    return int(JOYSTICK_KNOB_RADIUS * ui_scale)


def rotate_button_rect(ui_scale: float) -> pygame.Rect:
    """Botão de girar, no canto inferior DIREITO — diagonal ao joystick.

    Diagonal e não ao lado: com um ponteiro só não há gesto simultâneo a
    proteger, mas há o gesto ACIDENTAL. O polegar que sai do direcional passa
    por perto de tudo que estiver à direita dele, e girar a nave no meio de uma
    esquiva troca a direção do tiro sem o jogador pedir.
    """
    size = int(ROTATE_BUTTON_SIZE * ui_scale)
    margin = int(ROTATE_BUTTON_MARGIN * ui_scale)
    return pygame.Rect(
        Config.SCREEN_WIDTH - size - margin,
        Config.SCREEN_HEIGHT - size - margin,
        size,
        size,
    )
