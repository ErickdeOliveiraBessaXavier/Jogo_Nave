"""Transição de cena — fonte ÚNICA de fade in/out do jogo.

Antes desta classe cada tela tinha o próprio fade: `FadeTransitionMixin` +
`render_with_fade` (Settings/Statistics), um crossfade de view-stack no
`MainMenu`, uma cópia manual dos campos do mixin em `UpgradesSelection`,
`start_fade_*` na `PlayingScene`, uma rampa por timer no `GameOver`, outra na
`WorldTransition` — e nada em Paused/ControlsModal/P2ShipSelect/Language. Sete
implementações, durações diferentes, e telas que simplesmente cortavam seco.

O router inverte a responsabilidade: a cena **pede** a navegação
(`app.go_to(...)`) e quem desenha o fade e decide QUANDO trocar é o `GameApp`.
Uma tela nova não tem como esquecer o fade — ela não participa dele.

Dois estilos, porque há duas situações visualmente distintas:

``BLACK``
    Troca de tela de verdade (menu → config, menu → jogo, game over → menu).
    Escurece até o preto, troca a cena no pico e clareia. O corte fica
    escondido no preto.

``DIM``
    A cena que entra **continua mostrando** o que a anterior mostrava — pausa
    e game over desenham o mundo do jogo por baixo. Aqui um preto no meio seria
    pior que o corte: pisca. O router não desenha nada, só empresta o relógio
    (`overlay_progress`) para a cena animar o próprio overlay — na entrada
    subindo 0→1 e na saída caindo 1→0.

Fica no `core/` e não em `scenes/` porque o `GameApp` o instancia e as cenas
não precisam se conhecer para usá-lo.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Optional

import pygame


class TransitionStyle(Enum):
    """Como a troca é encoberta. Ver o docstring do módulo."""

    BLACK = auto()
    DIM = auto()


class _Phase(Enum):
    IDLE = auto()
    OUT = auto()  # escurecendo; a cena antiga ainda está no topo
    IN = auto()   # clareando; a cena nova já entrou


# Duração padrão de cada metade (out e in). O total percebido é ~2×.
DEFAULT_DURATION: float = 0.28

# Com "Animações da Interface" desligado a transição vira instantânea (um
# frame), sem varrer a tela inteira com um overlay por vários frames. Não é 0.0
# para a divisão do progresso não estourar.
_INSTANT_DURATION: float = 0.0001


def _ease_in_out(t: float) -> float:
    """Suaviza as pontas (smoothstep). Linear faz o começo e o fim do fade
    parecerem estalos; isto é o que dá a sensação de 'suave'."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


class SceneTransition:
    """Máquina de estados do fade global. Uma instância por `GameApp`.

    Ciclo: `request()` → fase OUT → **a navegação roda no fim da OUT** → fase
    IN → IDLE. Cada metade é opcional (ver `request`), mas a ordem é fixa: a
    troca nunca acontece antes da saída terminar.
    """

    def __init__(self) -> None:
        self._phase = _Phase.IDLE
        self._elapsed = 0.0
        self._duration = DEFAULT_DURATION
        self._style = TransitionStyle.BLACK
        self._pending: Optional[Callable[[], None]] = None
        self._fade_in = True
        # Boot: o primeiro frame já entra clareando, para o jogo não aparecer
        # do nada. Sem isto a primeira tela seria o único corte seco restante.
        self._begin_in()

    # ── Consulta ─────────────────────────────────────────────────────────────

    @property
    def busy(self) -> bool:
        """True enquanto a troca está pendente (fase OUT).

        O `GameApp` usa isto para **engolir input**: sem isso um segundo clique
        durante o escurecimento enfileira outra navegação e o jogador pula uma
        tela. Só a OUT bloqueia — na IN a cena nova já é a real e deve responder.
        """
        return self._phase is _Phase.OUT

    @property
    def active(self) -> bool:
        return self._phase is not _Phase.IDLE

    @property
    def overlay_progress(self) -> float:
        """Quão "presente" a cena do topo deve se desenhar neste frame.

        Sobe 0→1 enquanto ela entra, cai 1→0 enquanto ela sai, e vale 1.0 em
        repouso — então `alpha * overlay_progress` é seguro em qualquer frame.

        É o relógio que as cenas de estilo ``DIM`` (pausa, modal do P2) leem
        para animar o próprio overlay em vez de manter um timer. Cobrir as DUAS
        metades é o que faz a saída existir: a versão anterior só tinha a
        subida, então a pausa entrava animada e sumia de um frame para o outro.
        """
        if self._phase is _Phase.IDLE:
            return 1.0
        p = _ease_in_out(self._elapsed / self._duration)
        return 1.0 - p if self._phase is _Phase.OUT else p

    @property
    def black_alpha(self) -> int:
        """Alpha do véu preto neste frame (0–255). 0 fora do estilo BLACK."""
        if self._style is not TransitionStyle.BLACK or self._phase is _Phase.IDLE:
            return 0
        p = _ease_in_out(self._elapsed / self._duration)
        # OUT escurece (0→255); IN clareia (255→0).
        return int(255 * (p if self._phase is _Phase.OUT else 1.0 - p))

    # ── Comando ──────────────────────────────────────────────────────────────

    def request(
        self,
        action: Callable[[], None],
        *,
        style: TransitionStyle = TransitionStyle.BLACK,
        fade_out: bool = True,
        fade_in: bool = True,
        duration: Optional[float] = None,
    ) -> bool:
        """Agenda `action` (a troca de cena) para rodar encoberta pelo fade.

        As duas metades são independentes porque nem toda navegação precisa das
        duas — e é exatamente aí que a pausa quebrava:

        - **Abrir** um overlay: `fade_out=False`. Não há o que despedir; a cena
          de baixo continua visível. Só a nova entra (fase IN).
        - **Fechar** um overlay: `fade_in=False`. A que sai precisa da despedida
          (fase OUT, e o `pop` só acontece no fim dela); a de baixo já estava na
          tela e não tem por que "entrar".
        - Troca de tela normal (`BLACK`): as duas.

        Devolve False só durante a fase OUT — aí o pedido é **descartado**, não
        enfileirado: dois cliques rápidos em botões diferentes não devem levar
        o jogador a duas telas em sequência. Durante a fase IN o pedido é
        ACEITO: a cena nova já é a real e precisa responder na hora (apertar P
        duas vezes rápido tem de pausar e despausar, não engolir a segunda).
        """
        if self.busy:
            return False

        interrompendo_entrada = self._phase is _Phase.IN
        fracao_entrada = self._elapsed / self._duration if interrompendo_entrada else 0.0

        self._style = style
        self._duration = self._resolve_duration(duration)
        self._pending = action
        self._fade_in = fade_in

        if fade_out:
            self._phase = _Phase.OUT
            # Do zero no caso normal. Mas ao interromper uma entrada pela
            # metade, a saída começa de onde a entrada parou em vez de saltar
            # para "cheio" e piscar: vale a simetria do smoothstep
            # — ease(1-x) == 1-ease(x) —, então espelhar a fração dá
            # continuidade exata, não aproximada.
            self._elapsed = (
                (1.0 - fracao_entrada) * self._duration
                if interrompendo_entrada
                else 0.0
            )
        else:
            # Nada a despedir: comita já e emenda na entrada.
            self._commit()
        return True

    @staticmethod
    def _resolve_duration(duration: Optional[float]) -> float:
        from .visual_quality import visual_quality

        if not visual_quality.ui_animations:
            return _INSTANT_DURATION
        return DEFAULT_DURATION if duration is None else max(_INSTANT_DURATION, duration)

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Avança o fade. A troca de cena acontece AQUI, nunca no draw (§3)."""
        if self._phase is _Phase.IDLE:
            return

        self._elapsed += dt
        if self._elapsed < self._duration:
            return

        if self._phase is _Phase.OUT:
            self._commit()
        else:
            self._phase = _Phase.IDLE
            self._elapsed = 0.0

    def _commit(self) -> None:
        """Executa a navegação (troca de fato) e decide se ainda há entrada.

        Só chega aqui no FIM da fase OUT — é isso que garante que a cena que
        sai só é desempilhada depois da animação de saída terminar, e não no
        instante do clique.
        """
        action, self._pending = self._pending, None
        if action is not None:
            action()
        if self._fade_in:
            self._begin_in()
        else:
            self._phase = _Phase.IDLE
            self._elapsed = 0.0

    def _begin_in(self) -> None:
        self._phase = _Phase.IN
        self._elapsed = 0.0

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o véu por cima da cena. Chamado pelo `GameApp` depois do
        render da cena e antes da pixelização."""
        alpha = self.black_alpha
        if alpha <= 0:
            return
        # `fill` com uma cor sólida numa surface sem SRCALPHA + set_alpha é o
        # caminho mais barato para um véu de tela cheia: evita o blend por
        # pixel de uma SRCALPHA do tamanho da tela a cada frame.
        from ..scenes.ui_helpers import get_fade_scratch

        veil = get_fade_scratch(surface.get_size(), per_pixel_alpha=False)
        veil.fill((0, 0, 0))
        veil.set_alpha(alpha)
        surface.blit(veil, (0, 0))
