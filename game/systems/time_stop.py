"""Estado da parada do tempo (power-up TIME_STOP).

Lógica pura: sem pygame, sem cena, sem entidades. A `PlayingScene` alimenta
`update(dt)` e lê as propriedades; quem aplica o efeito é o `EntityManager`
(escala de tempo e tremor) e o `GameRenderer` (aviso no HUD).

O efeito tem TRÊS fases, e a do meio é o que o jogador enxerga como "vai
acabar":

    FROZEN ──────────────┬── WARNING ──┬── RECOVERING ──────────┬── ocioso
    escala 0             │  escala 0   │  escala 0 → 1          │  escala 1
    (sem aviso)          │  HUD pulsa  │  inimigos acelerando   │
                         │  + tremor   │                        │

`WARNING` ainda é congelamento — a escala continua em zero. A diferença é só
de feedback: é o aviso de que a paralisia está no fim.
"""

from __future__ import annotations

import math
from enum import Enum, auto

from ..core.config import config as Config


class TimeStopPhase(Enum):
    """Fase corrente do efeito, para quem precisa reagir à VIRADA.

    `is_frozen`/`is_recovering` respondem "como está agora"; a fase existe para
    a cena detectar a transição (idle→frozen, frozen→recovering) e disparar os
    cues de áudio uma única vez. `WARNING` não é fase própria: ainda é
    congelamento, só com feedback diferente (ver `warning_ratio`).
    """

    IDLE = auto()
    FROZEN = auto()
    RECOVERING = auto()

# ── Envelope de música ──────────────────────────────────────────────────────
# Tudo aqui é AMPLITUDE, porque é o único eixo que `pygame.mixer.music` expõe
# (sem pitch, sem taxa, sem filtro). Ver `TimeStopState.music_factor`.

# Volume da música durante o congelamento. Não é zero de propósito: um leito
# tênue soa melhor que silêncio digital e dá de onde a rampa de volta subir.
# Também não usamos `mixer.music.pause()`, porque o flag `music_paused` é
# compartilhado com a tela de pausa de verdade e as duas colidiriam.
_MUSIC_FROZEN_LEVEL: float = 0.08

# Tempo da queda inicial. Curto o bastante para ler como "corte", longo o
# bastante para não estalar — um degrau de volume vira clique audível.
_MUSIC_DUCK_IN: float = 0.12

# Tremolo da volta. A 60fps dá para modular limpo até ~10Hz (Nyquist em 30);
# acima disso a modulação alia e vira chiado em vez de oscilação.
_MUSIC_TREMOLO_HZ: float = 8.0
_MUSIC_TREMOLO_DEPTH: float = 0.55

# ── Sincronia do feedback visual com os SFX ─────────────────────────────────
# O congelamento em si é instantâneo (é o ponto do power-up); o que tem rampa é
# só a MOLDURA da HUD, e ela é cronometrada pelos efeitos sonoros
# `Efeito_Desacelerando` / `Efeito_Acelerando` — o olho e o ouvido têm de
# chegar juntos.
#
# Medido nos próprios arquivos (não estimado): ambos têm 1,480s, mas o GESTO
# audível de cada um dura 1,01s, e eles são espelhados —
#
#   Desacelerando |=== gesto 1,01s ===|···· silêncio 0,47s ····|
#   Acelerando    |···· silêncio 0,47s ····|=== gesto 1,01s ===|
#
# Por isso a entrada é uma rampa simples de 1,01s, e a saída SEGURA durante o
# silêncio inicial antes de dissolver. Usar a duração do arquivo (1,48s) nos
# dois casos deixaria a moldura ainda se mexendo depois de o som calar na
# entrada, e já quase apagada antes de o som começar na saída.
_VISUAL_ENTRY_RAMP: float = 1.01
_VISUAL_EXIT_HOLD: float = 0.47
_VISUAL_EXIT_RAMP: float = 1.01


class TimeStopState:
    """Máquina de tempo do power-up. Um por partida, vive na `PlayingScene`."""

    def __init__(self) -> None:
        self._frozen_left: float = 0.0
        self._frozen_total: float = 0.0
        self._recovery_left: float = 0.0

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def trigger(self, duration: float | None = None) -> None:
        """(Re)inicia a parada do tempo.

        Renova em vez de somar — dois pickups seguidos não acumulam 16s. Se já
        havia uma recuperação em curso, ela é cancelada: o novo congelamento
        manda, e reaproveitar o resto da rampa antiga deixaria os inimigos
        saindo mais rápido do segundo freeze que do primeiro.
        """
        total = Config.TIME_STOP_DURATION if duration is None else duration
        self._frozen_left = max(self._frozen_left, total)
        # Guarda o total para o envelope de música saber HÁ QUANTO TEMPO o
        # congelamento começou (a queda inicial dura `_MUSIC_DUCK_IN`).
        self._frozen_total = self._frozen_left
        self._recovery_left = 0.0

    def update(self, dt: float) -> None:
        if self._frozen_left > 0.0:
            self._frozen_left = max(0.0, self._frozen_left - dt)
            if self._frozen_left == 0.0:
                # Acabou de descongelar: entra na rampa de volta.
                self._recovery_left = Config.TIME_STOP_RECOVERY_DURATION
            return

        if self._recovery_left > 0.0:
            self._recovery_left = max(0.0, self._recovery_left - dt)

    def reset(self) -> None:
        """Zera tudo (troca de fase, game over) — sem rampa residual."""
        self._frozen_left = 0.0
        self._frozen_total = 0.0
        self._recovery_left = 0.0

    # ------------------------------------------------------------------
    # Saída — consumida por EntityManager e HUD
    # ------------------------------------------------------------------

    @property
    def enemy_time_scale(self) -> float:
        """Multiplicador do delta-time dos inimigos. 0 = parado, 1 = normal.

        Substituiu o booleano `freeze_enemies`. Como TODO o lado inimigo
        (inimigos, boss, projéteis, ambiente) já derivava de um único
        `enemy_dt`, escalar aqui alcança tudo sem tocar em entidade nenhuma.
        """
        if self._frozen_left > 0.0:
            return 0.0
        if self._recovery_left <= 0.0:
            return 1.0

        total = Config.TIME_STOP_RECOVERY_DURATION
        if total <= 0.0:
            return 1.0
        elapsed = 1.0 - (self._recovery_left / total)
        # Ease-IN quadrático: começa quase parado e vai ganhando velocidade.
        # Uma rampa linear já se lê como "normal" na primeira metade; o
        # quadrático é o que dá a leitura de "recuperando as forças".
        return max(0.0, min(1.0, elapsed * elapsed))

    @property
    def is_frozen(self) -> bool:
        return self._frozen_left > 0.0

    @property
    def is_recovering(self) -> bool:
        return not self.is_frozen and self._recovery_left > 0.0

    @property
    def is_active(self) -> bool:
        """Congelado OU se recuperando — o efeito ainda tem algo na tela."""
        return self.is_frozen or self.is_recovering

    @property
    def phase(self) -> TimeStopPhase:
        """Fase corrente. Derivada, não armazenada — não pode dessincronizar."""
        if self.is_frozen:
            return TimeStopPhase.FROZEN
        if self.is_recovering:
            return TimeStopPhase.RECOVERING
        return TimeStopPhase.IDLE

    @property
    def frozen_time_left(self) -> float:
        return self._frozen_left

    @property
    def warning_ratio(self) -> float:
        """0 fora da janela de aviso; sobe a 1 no instante do descongelamento.

        É a intensidade do "vai acabar": alimenta a pulsação do HUD e o tremor.
        Cresce (em vez de ser um liga/desliga) para o aviso entrar suave e ir
        ficando mais aflito.
        """
        if not self.is_frozen:
            return 0.0
        janela = Config.TIME_STOP_WARNING_TIME
        if janela <= 0.0 or self._frozen_left >= janela:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (self._frozen_left / janela)))

    @property
    def tremor_pixels(self) -> float:
        """Amplitude do tremor dos congelados, em pixels."""
        return self.warning_ratio * Config.TIME_STOP_TREMOR_PIXELS

    @property
    def entry_ratio(self) -> float:
        """0→1 na abertura do congelamento; 1 pelo resto do efeito.

        Só o feedback VISUAL usa isto — o congelamento em si não tem rampa. É o
        que faz a moldura crescer para dentro da tela ao ativar, em vez de
        piscar pronta. Dura o gesto do `Efeito_Desacelerando` (1,01s), então a
        moldura assenta no instante em que o som cala. Vale 1.0 durante a
        recuperação (já entrou; ali quem manda é `exit_ratio`) e 0.0 sem efeito.
        """
        if not self.is_frozen:
            return 1.0 if self.is_recovering else 0.0
        if _VISUAL_ENTRY_RAMP <= 0.0:
            return 1.0
        return max(0.0, min(1.0, self._elapsed_frozen() / _VISUAL_ENTRY_RAMP))

    @property
    def exit_ratio(self) -> float:
        """1→0 no fechamento visual, casado com o `Efeito_Acelerando`.

        Segura em 1.0 durante os 0,47s de silêncio do arquivo e só então
        dissolve, ao longo dos 1,01s do gesto: a moldura some no mesmo instante
        em que o som termina. Uma dissolução linear desde o descongelamento
        correria à frente do áudio — a borda estaria quase apagada antes de o
        som sequer começar.

        **Não** acompanha `recovery_ratio`. A rampa dos inimigos dura
        `TIME_STOP_RECOVERY_DURATION` (3s), o dobro do áudio; amarrar a moldura
        a ela é o que a deixava fora de sincronia com o efeito sonoro.
        """
        if self.is_frozen:
            return 1.0
        if not self.is_recovering:
            return 0.0
        decorrido = Config.TIME_STOP_RECOVERY_DURATION - self._recovery_left
        if decorrido <= _VISUAL_EXIT_HOLD:
            return 1.0
        if _VISUAL_EXIT_RAMP <= 0.0:
            return 0.0
        return max(0.0, 1.0 - (decorrido - _VISUAL_EXIT_HOLD) / _VISUAL_EXIT_RAMP)

    @property
    def hud_openness(self) -> float:
        """Abertura da moldura: 0 → 1 → 0. **Único** parâmetro das duas pontas.

        Sobe pela `entry_ratio`, fica em 1.0 enquanto o poder está ativo, e
        desce pela `exit_ratio` — que tem a MESMA duração de rampa. Como as duas
        pontas são o mesmo número lido em sentidos opostos, a saída é
        literalmente a entrada rebobinada, e não uma segunda animação que
        recomeça do zero.
        """
        return self.entry_ratio if self.is_frozen else self.exit_ratio

    @property
    def hud_warning(self) -> float:
        """`warning_ratio` para a MOLDURA, contínuo na virada do descongelamento.

        `warning_ratio` despenca de ~1 para 0 de um frame para o outro quando o
        congelamento acaba. Isso é correto para o TREMOR, que tem de parar na
        hora (senão os inimigos vibrariam enquanto voltam a andar), e errado
        para a moldura: a banda encolhia de estalo e o pisca rápido voltava à
        respiração calma no mesmo frame. Era esse duplo salto que fazia a saída
        parecer uma animação nova em vez da continuação da permanência.

        Na recuperação acompanha `hud_openness`, que vale exatamente 1.0 no
        instante da virada — então não há degrau — e depois libera junto com a
        dissolução da moldura.
        """
        return self.warning_ratio if self.is_frozen else self.hud_openness

    @property
    def recovery_ratio(self) -> float:
        """0 → 1 ao longo da rampa de volta (0 quando não está se recuperando)."""
        if not self.is_recovering:
            return 0.0
        total = Config.TIME_STOP_RECOVERY_DURATION
        if total <= 0.0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - (self._recovery_left / total)))

    # ------------------------------------------------------------------
    # Áudio
    # ------------------------------------------------------------------

    def music_factor(self, elapsed: float) -> float:
        """Multiplicador de volume da música (0–1) para este instante.

        Sai da MESMA máquina de fases que `enemy_time_scale`, então o áudio fica
        em fase com o visual de graça — a música desaba junto com o
        congelamento e volta junto com os inimigos.

        `elapsed` é o relógio da partida em segundos, usado só pelo tremolo.

        **Por que só volume:** `pygame.mixer.music` não expõe pitch, taxa de
        reprodução nem filtro — nem ele nem o SDL_mixer por baixo. Desacelerar
        ou abafar de verdade exigiria decodificar a faixa inteira para a RAM com
        `sndarray` (≈42 MB por faixa de 4 min) e reamostrar a cada frame, o que
        não cabe no orçamento e quebraria o build empacotado, que hoje não
        inclui numpy. Amplitude é o único eixo disponível — e dá para vender a
        sensação com ele.
        """
        if self.is_frozen:
            # Queda rápida em vez de corte seco: um degrau de volume estala.
            queda = min(1.0, self._elapsed_frozen() / _MUSIC_DUCK_IN)
            return 1.0 + (_MUSIC_FROZEN_LEVEL - 1.0) * queda

        if not self.is_recovering:
            return 1.0

        # Volta em ease-in, igual à dos inimigos.
        r = self.recovery_ratio
        nivel = _MUSIC_FROZEN_LEVEL + (1.0 - _MUSIC_FROZEN_LEVEL) * (r * r)

        # Tremolo: a única "distorção" possível só com amplitude. Lido como
        # wow-and-flutter de fita — o som cambaleando de volta à vida. A
        # profundidade decai a zero junto com a rampa, senão sobraria um
        # trêmulo audível na música já normalizada.
        profundidade = _MUSIC_TREMOLO_DEPTH * (1.0 - r)
        if profundidade > 0.0:
            onda = math.sin(elapsed * _MUSIC_TREMOLO_HZ * math.tau)
            nivel *= 1.0 - profundidade * (0.5 - 0.5 * onda)

        return max(0.0, min(1.0, nivel))

    def _elapsed_frozen(self) -> float:
        """Há quanto tempo este congelamento começou."""
        return max(0.0, self._frozen_total - self._frozen_left)
