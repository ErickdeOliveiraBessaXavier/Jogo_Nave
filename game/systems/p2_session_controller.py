"""P2SessionController — ciclo de vida do 2º jogador (co-op local).

Extraído da `PlayingScene` (§9). Não referencia a cena: recebe os objetos de
domínio (roster, gamepad, entity_manager) e **callbacks** para o que a cena
mantém — o trio `set_player_count` (level_controller + spawners), a abertura do
modal de seleção de nave (que precisa da cena para render de fundo e perfil) e o
rebuild das mini-naves permanentes.

Cobre: gatilhos de entrada (START no 2º controle), saída voluntária (BACK) e
desconexão do controle, além do spawn/despawn da nave de P2 e do snapshot de HUD.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import pygame

from ..core.config import config as Config
from ..core.gamepad import XboxButton
from ..entities.player.ship import Ship
from ..render.render_frame import P2HudInfo
from .player_slot import PlayerRoster, PlayerSlot

logger = logging.getLogger(__name__)


class P2SessionController:
    def __init__(
        self,
        *,
        roster: PlayerRoster,
        gamepad: Any,
        entity_manager: Any,
        get_is_side_scroll: Callable[[], bool],
        get_lives: Callable[[], int],
        set_player_count: Callable[[int], None],
        open_p2_modal: Callable[[Callable[[Any], None]], None],
        build_permanent_mini_ships: Callable[[PlayerSlot], None],
    ) -> None:
        self._roster = roster
        self._gamepad = gamepad
        self._entity_manager = entity_manager
        self._get_is_side_scroll = get_is_side_scroll
        self._get_lives = get_lives
        self._set_player_count = set_player_count
        self._open_p2_modal = open_p2_modal
        self._build_permanent_mini_ships = build_permanent_mini_ships

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def try_handle_event(self, event: pygame.event.Event) -> bool:
        """Trata os eventos de sessão do P2. Retorna True se consumiu o evento
        (a cena não deve repassá-lo ao input handler)."""
        if event.type == pygame.JOYBUTTONDOWN and self._is_join_trigger(event):
            # Start no 2º controle com P2 ainda fora: abre o modal de nave.
            self._open_p2_modal(self.spawn_p2)
            return True
        if event.type == pygame.JOYBUTTONDOWN and self._is_leave_trigger(event):
            # Saída voluntária (Back/Select) — score compartilhado é preservado.
            self.remove_p2(reason="voluntary")
            return True
        if event.type == pygame.JOYDEVICEREMOVED and self._is_disconnect():
            # Controle do P2 desconectou — evita nave parada sem input.
            self.remove_p2(reason="disconnect")
            return True
        return False

    def _is_join_trigger(self, event: pygame.event.Event) -> bool:
        """True se é START no segundo controle, e P2 ainda não juntou."""
        if event.button != XboxButton.START:
            return False
        if self._roster.count() >= 2:
            return False
        if not self._gamepad.secondary_connected:
            return False
        return self._gamepad.slot_of_instance_id(event.instance_id) == 1

    def _is_leave_trigger(self, event: pygame.event.Event) -> bool:
        """True se BACK foi pressionado no gamepad atribuído ao P2."""
        if event.button != XboxButton.BACK:
            return False
        if self._roster.count() < 2:
            return False
        return self._gamepad.slot_of_instance_id(event.instance_id) == 1

    def _is_disconnect(self) -> bool:
        """True se o gamepad desconectado era o atribuído ao P2 (o evento em si não
        carrega o slot; consultamos roster + gamepad)."""
        if self._roster.count() < 2:
            return False
        p2_slot = self._roster.all_slots()[1]
        if p2_slot.gamepad_slot != 1:
            return False
        # GamepadManager já processou o JOYDEVICEREMOVED (o app despacha pra cá
        # depois de chamar gamepad.handle_event), então slot 1 já está vazio.
        return not self._gamepad.is_slot_connected(1)

    # ------------------------------------------------------------------
    # Spawn / despawn
    # ------------------------------------------------------------------

    def remove_p2(self, *, reason: str) -> None:
        """Remove o slot do P2 do roster. Beacon e companheiros são descartados."""
        all_slots = self._roster.all_slots()
        if len(all_slots) < 2:
            return
        p2 = all_slots[1]
        p2.revival_beacon = None
        # Companheiros vinculados à nave do P2 (mini-naves permanentes do
        # Engenheiro ou temporárias do powerup, wingmen e o feixe de coop) somem
        # junto — sem a nave delas, ficariam orbitando/apontando entidade fantasma.
        self._entity_manager.remove_companions_of_ship(p2.ship)
        self._roster.remove(p2)
        # Volta ao escalonamento solo na próxima fase.
        self._set_player_count(self._roster.count())
        logger.info("P2 saiu da partida (motivo=%s).", reason)

    def _anchor(self) -> tuple[float, float]:
        """Posição de P1 na qual ancorar o spawn de P2.

        Enquanto P1 está entrando em cena, `x`/`y` ainda são o ponto de partida
        FORA da tela — ancorar neles mandaria P2 voar para fora do quadro. O
        destino da entrada é o ponto certo nesse caso.
        """
        primary_ship = self._roster.primary().ship
        if primary_ship.is_entering:
            return primary_ship.entry_target_pos
        return primary_ship.x, primary_ship.y

    def spawn_p2(self, profile: Any) -> None:
        """Cria a nave de P2 e adiciona ao roster com animação de entrada."""
        anchor_x, anchor_y = self._anchor()
        is_side_scroll = self._get_is_side_scroll()

        # Define alvos de spawn baseados em P1
        if is_side_scroll:
            target_x = anchor_x
            target_y = anchor_y + 80.0
            start_x = -100.0
            start_y = target_y
        else:
            target_x = anchor_x + 80.0
            target_y = anchor_y
            start_x = target_x
            start_y = float(Config.SCREEN_HEIGHT + 100)

        p2_ship = Ship(
            start_x,
            start_y,
            mouse_control=False,
            auto_fire=False,
            profile=profile,
            player_index=1,  # sprite recolorido em ciano (nave, minis e HUD)
        )

        # Ativa animação de entrada similar ao P1
        p2_ship.start_entering_animation(
            (start_x, start_y),
            (target_x, target_y),
            1.5,  # Duração da animação
        )
        p2_ship.grant_invulnerability(float(Config.INVULN_TIME * 1000))
        p2_ship.apply_world_mode(is_side_scroll)

        lives = self._get_lives()
        p2_slot = PlayerSlot(
            ship=p2_ship,
            lives=lives,
            gamepad_slot=1,
            apply_permanent_upgrades=False,
        )
        p2_ship.lives = lives
        self._roster.add(p2_slot)
        self._build_permanent_mini_ships(p2_slot)
        # Escala de co-op para a próxima fase (a fase atual mantém o valor antigo
        # — mudar inimigos vivos seria confuso pro jogador).
        self._set_player_count(self._roster.count())

        logger.info(
            "P2 entrou na partida com a nave '%s' (vidas=%d) e animação de entrada.",
            profile.id,
            lives,
        )

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------

    def build_hud_info(self) -> Optional[P2HudInfo]:
        """Snapshot do P2 para o HUD secundário (None em single-player)."""
        all_slots = self._roster.all_slots()
        if len(all_slots) < 2:
            return None
        p2 = all_slots[1]
        beacon_progress = (
            p2.revival_beacon.progress_ratio if p2.revival_beacon is not None else 0.0
        )
        return P2HudInfo(
            lives=p2.lives,
            is_dead=p2.is_dead,
            ship=p2.ship,
            beacon_progress=beacon_progress,
        )
