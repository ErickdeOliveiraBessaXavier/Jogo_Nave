"""Sistema de RESSONÂNCIA da Tríade — o portão que abre a cabeça principal.

Módulo de **lógica pura**: sem pygame, sem entidade, sem cena. Só ints, floats e
enums. Isso é deliberado — a regra aqui é a que decide se a luta é tensa ou
impossível (ver invariante abaixo), e ela precisa de teste direto (§16), não de
um boss instanciado.

O boss é dono das cabeças (`TriadHead`); este objeto é dono do **tempo e da
regra**, e as duas partes se falam por índice (0/1) e por eventos retornados do
`update` — nunca por referência cruzada (§1).

## A máquina

Cada cabeça lateral está em um de três estados:

    SOLID  — viva e sólida; fecha o portão
    DOWN   — destruída, soquete vazio
    REMAT  — brasa remontando (frágil, e o portão SEGUE aberto)

    A Coroa é vulnerável  ⟺  NENHUMA lateral está SOLID.

## A invariante que faz a luta ser possível

> **O relógio de regeneração só corre quando as DUAS estão fora.**

Sem isso o boss é matematicamente impossível abaixo de um limiar de DPS: o
jogador mata a primeira, e ela volta enquanto ele ainda trabalha na segunda —
as duas nunca caem juntas, o portão nunca abre, e nada na tela explica que a
luta é invencível. Com a regra, uma cabeça derrubada **espera** a irmã cair.
Isto é invariante, não tuning: não afrouxar por dificuldade.

## Suprimir a brasa

Durante o REMAT a Coroa continua exposta, então atirar na brasa custa DPS mas
compra janela. Derrubar UMA brasa devolve só aquela ao DOWN — a irmã completa e
o portão fecha, mas a derrubada fica "no banco" e o jogador só precisa rematar
uma para reabrir. Derrubar as DUAS mantém a janela aberta e reinicia o relógio.
Dois níveis de investimento, dois níveis de retorno.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List

# Índices das duas cabeças laterais. São dois e sempre dois — a arte tem duas.
LEFT: int = 0
RIGHT: int = 1
_SLOTS: tuple[int, int] = (LEFT, RIGHT)


class HeadState(Enum):
    SOLID = auto()
    DOWN = auto()
    REMAT = auto()


class ResonanceEvent(Enum):
    """O que aconteceu neste tick — o boss traduz em som/efeito/evento de bus."""

    REMAT_STARTED = auto()  # as brasas começaram a remontar
    WINDOW_OPENED = auto()  # a Coroa acabou de ficar vulnerável
    WINDOW_CLOSED = auto()  # a Coroa acabou de ficar intangível


class ResonanceGate:
    """Relógios e regra do portão. Não conhece pygame nem a entidade cabeça."""

    def __init__(
        self,
        regen_delay: float = 6.0,
        remat_duration: float = 3.0,
        min_window: float = 4.0,
        return_hp_base: float = 0.75,
        return_hp_decay: float = 0.15,
        return_hp_floor: float = 0.40,
    ) -> None:
        self.regen_delay = regen_delay
        self.remat_duration = remat_duration
        self.min_window = min_window
        self.return_hp_base = return_hp_base
        self.return_hp_decay = return_hp_decay
        self.return_hp_floor = return_hp_floor

        self._state: List[HeadState] = [HeadState.SOLID, HeadState.SOLID]
        self._remat_t: List[float] = [0.0, 0.0]
        self._returns: List[int] = [0, 0]
        self._return_hp: List[float] = [return_hp_base, return_hp_base]
        self._delay_left: float = 0.0
        self._window_left: float = 0.0
        # Armado é DIFERENTE de "tem tempo sobrando": o disparo do REMAT depende
        # do relógio E da janela mínima, e a janela pode ser a última a zerar. Um
        # gate escrito só sobre `_delay_left > 0` deixaria de disparar para
        # sempre no frame em que o delay chega a zero antes da janela.
        self._clock_armed: bool = False
        self._disabled: bool = False
        # Só para detectar a BORDA de abertura/fechamento e emitir o evento uma
        # vez — o estado em si é sempre derivado de `_state` (fonte única).
        self._was_open: bool = False

    # ── Consultas ────────────────────────────────────────────────────────────
    @property
    def crown_vulnerable(self) -> bool:
        """A Coroa é atacável? Verdadeiro enquanto nenhuma lateral estiver sólida."""
        return all(s is not HeadState.SOLID for s in self._state)

    def state(self, index: int) -> HeadState:
        return self._state[index]

    def is_solid(self, index: int) -> bool:
        return self._state[index] is HeadState.SOLID

    def is_rematerializing(self, index: int) -> bool:
        return self._state[index] is HeadState.REMAT

    def remat_progress(self, index: int) -> float:
        """0.0 → 1.0 ao longo do REMAT; 0.0 fora dele. Alimenta o alpha do sprite."""
        if self._state[index] is not HeadState.REMAT:
            return 0.0
        if self.remat_duration <= 0.0:
            return 1.0
        return min(1.0, self._remat_t[index] / self.remat_duration)

    def return_hp_fraction(self, index: int) -> float:
        """Fração do HP máximo com que a cabeça acabou de voltar.

        Publicada pelo portão no instante da transição REMAT→SOLID, e não
        calculada sob demanda: o contador de retornos já foi incrementado por
        essa mesma transição, então derivar daqui devolveria o valor do PRÓXIMO
        retorno — a cabeça voltava com 60% já na primeira volta, e o único
        sintoma era um boss um pouco mais fácil do que o projetado.
        """
        return self._return_hp[index]

    def _compute_return_fraction(self, completed_returns: int) -> float:
        """0.75 no 1º retorno, 0.60 no 2º, 0.45 no 3º, piso 0.40.

        É o que faz a luta CONVERGIR: cada volta é mais barata de derrubar que a
        anterior, então repetir o ciclo não é andar em círculo.
        """
        value = self.return_hp_base - self.return_hp_decay * completed_returns
        return max(self.return_hp_floor, value)

    # ── Transições ───────────────────────────────────────────────────────────
    def head_died(self, index: int) -> None:
        """A cabeça lateral `index` foi destruída (estava SOLID ou REMAT)."""
        self._state[index] = HeadState.DOWN
        self._remat_t[index] = 0.0
        self._sync_shared_clock()

    def head_remat_interrupted(self, index: int) -> None:
        """A brasa `index` levou tiro suficiente durante o REMAT e voltou ao DOWN.

        Semanticamente é o mesmo desfecho de `head_died`; existe como método
        próprio para o boss não precisar decidir qual chamar, e para o log de
        eventos futuro poder distinguir "matou a cabeça" de "suprimiu a brasa".
        """
        self.head_died(index)

    def _sync_shared_clock(self) -> None:
        """(Re)arma o relógio compartilhado quando — e só quando — as duas caem.

        Esta é a invariante do módulo. Uma cabeça sozinha no DOWN não tem
        relógio: ela espera a irmã.
        """
        if self._disabled:
            return
        if all(s is HeadState.DOWN for s in self._state):
            self._delay_left = self.regen_delay
            self._clock_armed = True
            # A janela mínima conta da queda da SEGUNDA — é a partir daí que o
            # jogador tem alvo, então é daí que o piso de justiça vale.
            self._window_left = max(self._window_left, self.min_window)
        else:
            self._delay_left = 0.0
            self._clock_armed = False

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update(self, dt: float) -> List[ResonanceEvent]:
        events: List[ResonanceEvent] = []

        if self._window_left > 0.0:
            self._window_left = max(0.0, self._window_left - dt)

        # 1) Espera compartilhada → as duas brasas começam a remontar juntas.
        if self._clock_armed and all(s is HeadState.DOWN for s in self._state):
            self._delay_left = max(0.0, self._delay_left - dt)
            if self._delay_left <= 0.0 and self._window_left <= 0.0:
                for i in _SLOTS:
                    self._state[i] = HeadState.REMAT
                    self._remat_t[i] = 0.0
                self._clock_armed = False
                events.append(ResonanceEvent.REMAT_STARTED)

        # 2) Avanço das brasas. Começaram juntas e têm a mesma duração, então
        #    completam no mesmo frame — salvo se uma foi suprimida no meio.
        for i in _SLOTS:
            if self._state[i] is not HeadState.REMAT:
                continue
            self._remat_t[i] += dt
            if self._remat_t[i] >= self.remat_duration:
                self._state[i] = HeadState.SOLID
                self._remat_t[i] = 0.0
                # Publica a fração ANTES de incrementar: este retorno usa a
                # contagem de retornos ANTERIORES a ele.
                self._return_hp[i] = self._compute_return_fraction(self._returns[i])
                self._returns[i] += 1

        # 3) Borda da janela — emitida DEPOIS das transições, para refletir o
        #    estado final do tick e nunca um intermediário.
        is_open = self.crown_vulnerable
        if is_open != self._was_open:
            events.append(
                ResonanceEvent.WINDOW_OPENED if is_open else ResonanceEvent.WINDOW_CLOSED
            )
            self._was_open = is_open

        return events

    # ── Fase 3: o portão cai de vez ──────────────────────────────────────────
    def disable(self) -> None:
        """Desliga o portão: a Coroa passa a ser sempre atacável (Fase 3).

        As laterais continuam existindo e atacando — o que acaba é o papel delas
        de escudo. Chamado uma vez na virada; o relógio compartilhado para junto.
        """
        self._disabled = True
        self._delay_left = 0.0
        self._window_left = 0.0
        self._clock_armed = False
        for i in _SLOTS:
            self._state[i] = HeadState.DOWN
        self._was_open = True
