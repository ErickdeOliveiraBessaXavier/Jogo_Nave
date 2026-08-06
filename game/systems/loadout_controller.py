"""loadout_controller.py — as regras de equipar upgrade e escolher nave.

Extraído da `UpgradesSelectionScene` seguindo o padrão de §1/§9 (referências:
`RevivalSystem`, `UpgradeSelector`): **não referencia a cena**, não desenha, não
toca em som. Recebe o perfil e a lista de upgrades pelo construtor e devolve um
`LoadoutResult` tipado dizendo o que aconteceu.

O retorno tipado (em vez de callbacks de som/mensagem) é o mesmo desenho do
`HitResult` no roteador de dano (§8): quem decide **o que aconteceu** é este
módulo, quem decide **como isso soa e aparece** é a tela. Foi o que tornou estas
regras testáveis — antes elas moravam entre um `sound_manager.play_*` e um
`self.floating_messages.append`, e não dava para exercitá-las sem pygame.

Regras que vivem aqui, e que o jogador sente diretamente:

- clicar num upgrade equipa no primeiro slot livre; clicar de novo desequipa;
- clicar num slot equipado devolve o upgrade à lista;
- clicar num slot travado tenta comprá-lo com estrelas;
- clicar na nave seleciona (se já é sua) ou compra (se dá para pagar).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, List, Optional, Sequence

from ..core.upgrades_config import UPGRADE_SLOT_COUNT

if TYPE_CHECKING:
    from ..core.meta_progression import PlayerProfile
    from ..core.ship_types import ShipProfile
    from ..core.upgrades import UpgradeMeta, UpgradeRole, UpgradeType


class LoadoutAction(Enum):
    """O que a interação produziu. `DENIED_*` são recusas com motivo."""

    NOTHING = auto()
    EQUIPPED = auto()
    UNEQUIPPED = auto()
    SLOT_UNLOCKED = auto()
    SHIP_SELECTED = auto()
    SHIP_PURCHASED = auto()
    DENIED_UPGRADE_LOCKED = auto()  # upgrade ainda não desbloqueado
    DENIED_NO_FREE_SLOT = auto()  # todos os slots destravados estão ocupados
    DENIED_SLOT_COST = auto()  # estrelas insuficientes para destravar o slot
    DENIED_SHIP_COST = auto()  # estrelas insuficientes para comprar a nave


@dataclass(frozen=True)
class LoadoutResult:
    """Resultado de uma interação. `slot_index` ancora o feedback visual."""

    action: LoadoutAction
    slot_index: Optional[int] = None
    meta: Optional["UpgradeMeta"] = None
    ship_name: str = ""

    @property
    def denied(self) -> bool:
        return self.action.name.startswith("DENIED_")


class LoadoutController:
    """Dono das regras de loadout. Sem render, sem som, sem cena."""

    def __init__(
        self, profile: "PlayerProfile", upgrades: Sequence["UpgradeMeta"]
    ) -> None:
        self.profile = profile
        self.upgrades: List["UpgradeMeta"] = list(upgrades)
        self._ensure_slot_count()

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def _ensure_slot_count(self) -> None:
        """Ajusta o loadout salvo ao número de slots do build atual.

        Perfil vindo de uma versão com mais slots chega com a lista maior; a
        carga já trunca, mas a tela não pode depender disso para indexar."""
        loadout = self.profile.upgrade_loadout
        while len(loadout) < UPGRADE_SLOT_COUNT:
            loadout.append(None)
        if len(loadout) > UPGRADE_SLOT_COUNT:
            self.profile.upgrade_loadout = loadout[:UPGRADE_SLOT_COUNT]

    def meta_for(self, upgrade_type: "UpgradeType") -> Optional["UpgradeMeta"]:
        return next((u for u in self.upgrades if u.type == upgrade_type), None)

    def upgrades_for_role(self, role: Optional["UpgradeRole"]) -> List["UpgradeMeta"]:
        """Upgrades de um papel. ``None`` devolve todos (a aba "Todos")."""
        if role is None:
            return list(self.upgrades)
        return [u for u in self.upgrades if u.role is role]

    def first_free_slot(self, meta: "UpgradeMeta") -> Optional[int]:
        for i in range(self.profile.unlocked_slots):
            if self.profile.upgrade_loadout[i] is None and self.profile.can_equip_upgrade(
                meta.type, i
            ):
                return i
        return None

    def equipped_slot(self, meta: "UpgradeMeta") -> Optional[int]:
        return self.profile.get_equipped_slot(meta.type)

    def is_unlocked(self, meta: "UpgradeMeta") -> bool:
        return meta.type in self.profile.unlocked_upgrades

    # ------------------------------------------------------------------
    # Interações
    # ------------------------------------------------------------------

    def toggle_upgrade(self, meta: "UpgradeMeta") -> LoadoutResult:
        """Card clicado: equipa no primeiro slot livre, ou desequipa."""
        if not self.is_unlocked(meta):
            return LoadoutResult(LoadoutAction.DENIED_UPGRADE_LOCKED, meta=meta)

        equipado_em = self.equipped_slot(meta)
        if equipado_em is not None:
            self.profile.equip_upgrade(None, equipado_em)
            return LoadoutResult(
                LoadoutAction.UNEQUIPPED, slot_index=equipado_em, meta=meta
            )

        alvo = self.first_free_slot(meta)
        if alvo is None:
            # Ancora a recusa no ÚLTIMO slot destravado: é o que o jogador
            # precisa esvaziar para o upgrade caber.
            return LoadoutResult(
                LoadoutAction.DENIED_NO_FREE_SLOT,
                slot_index=max(0, self.profile.unlocked_slots - 1),
                meta=meta,
            )

        self.profile.equip_upgrade(meta.type, alvo)
        return LoadoutResult(LoadoutAction.EQUIPPED, slot_index=alvo, meta=meta)

    def press_slot(self, index: int) -> LoadoutResult:
        """Slot clicado: destrava (travado) ou devolve o upgrade (equipado)."""
        if index >= self.profile.unlocked_slots:
            if self.profile.can_unlock_slot(index) and self.profile.unlock_slot(index):
                return LoadoutResult(LoadoutAction.SLOT_UNLOCKED, slot_index=index)
            return LoadoutResult(LoadoutAction.DENIED_SLOT_COST, slot_index=index)

        equipado = self.profile.upgrade_loadout[index]
        if equipado is None:
            return LoadoutResult(LoadoutAction.NOTHING, slot_index=index)

        meta = self.meta_for(equipado)
        self.profile.equip_upgrade(None, index)
        return LoadoutResult(LoadoutAction.UNEQUIPPED, slot_index=index, meta=meta)

    def press_ship(self, ship: "ShipProfile") -> LoadoutResult:
        """Nave do carrossel: seleciona, compra, ou recusa por saldo."""
        if self.profile.is_ship_unlocked(ship.id):
            if self.profile.selected_ship == ship.id:
                return LoadoutResult(LoadoutAction.NOTHING)
            self.profile.select_ship(ship.id)
            return LoadoutResult(LoadoutAction.SHIP_SELECTED)

        if self.profile.can_unlock_ship(ship.id) and self.profile.unlock_ship(ship.id):
            # Comprou: já entra selecionada. Comprar e não equipar seria um
            # segundo passo que ninguém quer depois de gastar as estrelas.
            self.profile.select_ship(ship.id)
            return LoadoutResult(LoadoutAction.SHIP_PURCHASED)

        return LoadoutResult(LoadoutAction.DENIED_SHIP_COST)
