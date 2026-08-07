"""upgrade_selector.py — Cursor de seleção de upgrade por gamepad (§1, §9).

Extraído de `PlayingScene`. Cuida só da navegação do cursor sobre os slots de
upgrade equipados: ligar/desligar o modo de seleção, mover entre slots
(priorizando os que estão fora de cooldown) e confirmar. A ativação em si (o
efeito do upgrade) fica na cena — aqui só se decide *qual* slot.

Não referencia `PlayingScene` (§1). Dependências pelo construtor:

- `get_slots()` — devolve a lista atual de slots (`ActiveUpgrade | None`). É um
  getter, não a lista: a cena **reatribui** `upgrade_slots` a cada fase, então
  guardar a referência apontaria para uma lista velha.
- `activate(idx)` — callback que dispara o upgrade do slot escolhido.

O estado do cursor (`mode`, `index`) vive aqui e é lido pela cena ao montar o
`RenderFrame` (o HUD destaca o slot selecionado). A cena expõe fachadas finas
para o input handler, que já chama `toggle/navigate/confirm` (§9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:
    from ..core.upgrades import ActiveUpgrade


class UpgradeSelector:
    """Estado e navegação do cursor de seleção de upgrade."""

    def __init__(
        self,
        get_slots: Callable[[], List[Optional["ActiveUpgrade"]]],
        activate: Callable[[int], None],
    ) -> None:
        self._get_slots = get_slots
        self._activate = activate
        self.mode: bool = False
        self.index: int = 0

    def toggle(self) -> None:
        """Liga/desliga o modo. Ao ligar, alinha o cursor a um slot válido,
        priorizando upgrades fora de cooldown."""
        if self.mode:
            self.mode = False
            return
        if not any(s is not None for s in self._get_slots()):
            return  # Sem upgrades equipados — nada para selecionar.
        self.mode = True
        self._snap_to_valid()

    def navigate(self, delta: int) -> None:
        """Move o cursor entre slots ocupados, priorizando os prontos."""
        order = self._order()
        if not order:
            return
        try:
            current_pos = order.index(self.index)
        except ValueError:
            self.index = order[0]
            return
        self.index = order[(current_pos + delta) % len(order)]

    def confirm(self) -> None:
        """Ativa o slot destacado e sai do modo."""
        idx = self.index
        self.mode = False
        slots = self._get_slots()
        if 0 <= idx < len(slots) and slots[idx] is not None:
            self._activate(idx)

    def cancel(self) -> None:
        """Sai do modo sem ativar nada (pausa, botão B)."""
        self.mode = False

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    @staticmethod
    def _is_ready(upg: Optional["ActiveUpgrade"]) -> bool:
        """Disponibilidade REAL — a mesma que a ativação consulta.

        Era `cooldown_left <= 0.0`, e isso mentia na janela mais importante: o
        cooldown só parte quando o efeito TERMINA, então o upgrade recém-usado
        passava a duração inteira contando como pronto. O cursor então parava
        nele — justo o único que não responde — em vez de pular para o próximo
        disponível, que é o serviço que a seleção rápida presta.
        """
        return upg is not None and upg.is_ready

    def _order(self) -> List[int]:
        """Índices dos slots ocupados: prontos primeiro, em cooldown depois."""
        slots = self._get_slots()
        ready = [i for i, upg in enumerate(slots) if self._is_ready(upg)]
        cooling = [
            i
            for i, upg in enumerate(slots)
            if upg is not None and not self._is_ready(upg)
        ]
        return ready + cooling

    def _snap_to_valid(self) -> None:
        order = self._order()
        if order:
            self.index = order[0]
