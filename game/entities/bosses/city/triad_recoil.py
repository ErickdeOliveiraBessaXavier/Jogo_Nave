"""Recuo da parte da Tríade que leva tiro — o "peso" do acerto.

Módulo de **lógica pura**: só floats, sem pygame e sem entidade. A cabeça e a
Coroa compõem um `HitRecoil` cada e o consultam no desenho; a regra de acúmulo e
de retorno fica testável sem instanciar o boss (§16), como o `ResonanceGate`.

## Por que o recuo NÃO move a parte de verdade

A tentação é somar o recuo em `TriadHead.offset_x/offset_y` — eles já existem,
já são mutáveis e já voltam sozinhos pelo `_ease_heads_home`. Não dá: o limiar de
`at_home` é de UM pixel, e cabeça fora de casa **sai da máscara combinada** do
boss (`_mask_key` e `_hit_mask` só unem as partes que estão no soquete). O recuo
empurraria a Voz para fora da própria hitbox, e o resultado seria um boss que
desvia da bala POR ter sido acertado: quanto mais rápido o jogador atirasse,
menos ele acertaria — e o sintoma apareceria como "as balas atravessam o boss às
vezes", sem nada apontando para o recuo.

Logo isto é offset de **desenho**. Hitbox, origem de feixe, roteamento de dano e
cache de máscara não enxergam nada daqui.

## A direção

`on_hit(damage, hit_x, hit_y)` não carrega a velocidade do projétil, então a
direção sai da geometria: do ponto de impacto PARA o centro da parte, ou seja, a
parte foge de onde apanhou. Isso acerta em qualquer ângulo (inclusive dano em
área vindo de cima) sem o roteador de dano ter que passar mais nada.

## O teto

O impulso ACUMULA, mas com o módulo limitado. Sem teto, fogo automático somaria
um empurrão por bala e a peça derivaria para longe do corpo enquanto o jogador
segurasse o gatilho — o boss se desmontaria sozinho sob pressão. Com teto, tiro
sustentado mantém a peça deslocada (que é a leitura certa: pressão contínua) sem
nunca sair do desenho.
"""

from __future__ import annotations

import math

# Pixels de TELA, dimensionados contra o sprite do boss (64 × PIXEL_SCALE 5 =
# 320px de lado). ~8px é o recuo de um tiro isolado: visível no impacto, longe
# de descolar a peça do corpo. O teto em 14px é onde o fogo sustentado satura.
IMPULSE: float = 8.0
MAX_OFFSET: float = 14.0
# Retorno exponencial, em "e-folds por segundo". A 16/s o recuo cai a 4% do pico
# em 0,2s — o soco é seco e a peça já está de volta antes do tiro seguinte de uma
# arma normal, então cada acerto tem o próprio impacto em vez de virar tremor.
RETURN_RATE: float = 16.0


class HitRecoil:
    """Deslocamento de desenho de UMA parte, decaindo de volta para o lugar."""

    __slots__ = ("x", "y")

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0

    def kick(
        self, center_x: float, center_y: float, hit_x: float, hit_y: float
    ) -> None:
        """Empurra a parte para LONGE do ponto de impacto."""
        dx, dy = center_x - hit_x, center_y - hit_y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            # Impacto no centro exato (ou dano em área ancorado nele): não há
            # direção a extrair. Para cima, porque é de baixo que o jogador
            # atira — o palpite erra pouco e nunca fica parado.
            dx, dy = 0.0, -1.0
        else:
            dx, dy = dx / dist, dy / dist

        self.x += dx * IMPULSE
        self.y += dy * IMPULSE

        excess = math.hypot(self.x, self.y)
        if excess > MAX_OFFSET:
            escala = MAX_OFFSET / excess
            self.x *= escala
            self.y *= escala

    def update(self, dt: float) -> None:
        """Volta ao repouso. Exponencial para ser independente de frame rate.

        Decaimento por fator constante POR SEGUNDO — não `x -= vel * dt`, que
        passa do zero num frame longo e faz a peça oscilar em vez de assentar.
        """
        if self.x == 0.0 and self.y == 0.0:
            return
        fator = math.exp(-RETURN_RATE * dt)
        self.x *= fator
        self.y *= fator
        # Piso: abaixo de meio pixel não há o que desenhar, e zerar de vez livra
        # os frames seguintes da conta (o `update` roda para as três partes,
        # todo frame, durante a luta inteira).
        if abs(self.x) < 0.5 and abs(self.y) < 0.5:
            self.x = 0.0
            self.y = 0.0

    @property
    def offset(self) -> tuple[int, int]:
        """Deslocamento em pixels inteiros, pronto para somar na origem do blit."""
        return int(self.x), int(self.y)


# ── Tremor da morte ───────────────────────────────────────────────────────────
# A Voz não se desfaz parada: ela ESTREMECE enquanto a desintegração corre. Sem
# isso os 8 frames de `Morrendo` tocam num sprite imóvel, e a queda lê como uma
# troca de imagem em vez de uma estrutura cedendo.
#
# Amplitude em pixels de ARTE, não de tela: o tremor é quantizado ao mesmo passo
# do sprite (`PIXEL_SCALE`), então ele salta de pixel inteiro em pixel inteiro,
# como pixel art faz. Um deslocamento sub-pixel viraria um borrão trêmulo — o
# efeito de "sprite mal ancorado", que é o oposto de um impacto.
# DOIS pixels de arte, não um: com amplitude de 1 a quantização só sabe dizer
# "±1 ou 0", então o decaimento vira RAREFAÇÃO (o tremor pisca cada vez menos)
# em vez de amplitude — lê como engasgo. Com 2 ele decai 2 → 1 → 0, que é uma
# rampa de verdade dentro da grade do pixel art.
DEATH_SHAKE_ART_PIXELS: float = 2.0
# Rápido o bastante para ler como vibração e não como balanço. Os dois eixos usam
# frequências INCOMENSURÁVEIS (razão 0,73) de propósito: com a mesma frequência o
# tremor vira uma oscilação diagonal limpa, que lê como a peça deslizando.
DEATH_SHAKE_HZ: float = 24.0


def death_shake(elapsed: float, duration: float, art_scale: int) -> tuple[int, int]:
    """Deslocamento do tremor de morte, em pixels de tela.

    A amplitude DECAI ao longo da animação: a cabeça treme forte quando ainda é
    uma estrutura e para de tremer quando já virou poeira — no fim não sobra
    nada rígido para vibrar, e um tremor constante até o último frame faria as
    faíscas dispersas pularem juntas, como se ainda fossem um corpo só.

    Função pura de `elapsed`, sem estado e sem aleatório: o `draw` a consulta e
    não muta nada (§3), e o resultado é o mesmo em qualquer frame rate.
    """
    if duration <= 0.0 or elapsed >= duration:
        return 0, 0
    restante = 1.0 - max(0.0, elapsed) / duration
    amplitude = DEATH_SHAKE_ART_PIXELS * art_scale * restante
    if amplitude < 1.0:
        return 0, 0
    fase = elapsed * DEATH_SHAKE_HZ * math.tau
    dx = math.sin(fase) * amplitude
    dy = math.sin(fase * 0.73 + 1.7) * amplitude
    # Quantiza ao passo do sprite: o tremor anda em pixels de arte inteiros.
    passo = float(art_scale)
    return (
        int(round(dx / passo) * passo),
        int(round(dy / passo) * passo),
    )
