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

from ..core.config import config as Config

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
