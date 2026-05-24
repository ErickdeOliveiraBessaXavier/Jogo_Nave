from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import pygame

if TYPE_CHECKING:
    from ..scenes.playing import PlayingScene
    from ..systems.player_slot import PlayerSlot


logger = logging.getLogger(__name__)


class GameplayInputHandler:
    """Despacha eventos pygame (teclado, mouse, gamepad) para ações de gameplay.

    A cena (`PlayingScene`) continua dona dos slots de upgrade, do modo de
    seleção e dos toggles de debug — este handler apenas roteia o evento para
    o método certo da cena ou do `Ship`.

    Em multiplayer, eventos de gamepad são roteados pelo `instance_id` do
    pygame: `_slot_for_instance_id` traduz para o `PlayerSlot` correto, e
    cada ação (cycle_facing, dash, charge, Cofre) opera em `slot.ship`. LT
    e botões P1-only (upgrade select / D-pad) permanecem ligados ao slot
    primário.
    """

    # Inicializa o handler de inputs.
    def __init__(self, scene: "PlayingScene") -> None:
        self.scene = scene
        # Estado do gatilho LT por slot do gamepad (calibrado na primeira
        # leitura abaixo de -0.5 — proteção contra falsa detecção). Cada
        # controle calibra independentemente.
        self._lt_pressed: dict[int, bool] = {}
        self._lt_calibrated: dict[int, bool] = {}

    # ------------------------------------------------------------------
    # Dispatch principal
    # ------------------------------------------------------------------

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self._handle_keydown(event)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_mousebuttondown(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            self._handle_mousebuttonup(event)
        elif event.type == pygame.KEYUP:
            self._handle_keyup(event)
        elif event.type == pygame.JOYBUTTONDOWN:
            self._handle_gamepad_button(event.button, event.instance_id)
        elif event.type == pygame.JOYHATMOTION:
            self._handle_gamepad_hat(event.value, event.instance_id)
        elif event.type == pygame.JOYAXISMOTION:
            self._handle_gamepad_axis(event.axis, event.value, event.instance_id)

    # ------------------------------------------------------------------
    # Teclado / Mouse
    # ------------------------------------------------------------------

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        scene = self.scene
        if event.key == pygame.K_p:
            from ..scenes.paused import PausedScene

            scene.app.states.push(PausedScene(scene.app, previous_scene=scene))
        elif event.key == pygame.K_F3:
            scene.show_fps = not scene.show_fps
            logger.info("Debug FPS: %s", "ATIVADO" if scene.show_fps else "DESATIVADO")
        elif event.key == pygame.K_F7:
            scene.show_enemy_hitboxes = not scene.show_enemy_hitboxes
            logger.info(
                "Debug Hitbox: %s",
                "ATIVADO" if scene.show_enemy_hitboxes else "DESATIVADO",
            )
        elif event.key == pygame.K_F8:
            scene.trigger_world_transition_debug_preview()
        elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
            if not scene.ship.is_entering and scene.can_handle_gameplay_actions():
                scene.ship.cycle_facing()
        elif event.key in (pygame.K_q, pygame.K_e):
            # Cofre: Q usa slot 0, E usa slot 1.
            if not scene.ship.is_entering and scene.can_handle_gameplay_actions():
                slot = 0 if event.key == pygame.K_q else 1
                scene.activate_stored_powerup(slot)
        elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            # Fantasma: dash com i-frames.
            if (
                not scene.ship.is_entering
                and scene.can_handle_gameplay_actions()
                and scene.ship.profile.has_dash
            ):
                held = scene.app.input.poll_held()
                move_vec = pygame.math.Vector2(0, 0)
                if "hold_left" in held:
                    move_vec.x -= 1
                if "hold_right" in held:
                    move_vec.x += 1
                if "hold_up" in held:
                    move_vec.y -= 1
                if "hold_down" in held:
                    move_vec.y += 1
                scene.ship.try_dash(move_vec)
        elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
            if not scene.ship.is_entering and scene.can_handle_gameplay_actions():
                if scene.ship.profile.has_charge_shot and (event.mod & pygame.KMOD_ALT):
                    # Só ativa charge com Space + Alt pressionados juntos.
                    scene.ship.start_charge()

        if __debug__:
            scene.process_cheat_input(event)

        if scene.can_handle_gameplay_actions() and not scene.ship.is_entering:
            self._handle_upgrade_key(event)

    def _handle_mousebuttondown(self, event: pygame.event.Event) -> None:
        scene = self.scene
        if event.button == 1:
            if not scene.ship.is_entering and scene.can_handle_gameplay_actions():
                if (
                    scene.ship.profile.has_charge_shot
                    and not scene.ship.charge_shot_active
                    and pygame.key.get_mods() & pygame.KMOD_ALT
                ):
                    # Botão esquerdo + Alt: inicia charge (espelho do Space+Alt).
                    scene.ship.start_charge()
                elif not scene.ship.auto_fire and scene.shooting.is_ready(scene.ship):
                    scene.shooting.fire(scene.ship, scene.player_damage_multiplier)
        elif event.button == 2:
            if not scene.ship.is_entering and scene.can_handle_gameplay_actions():
                scene.ship.cycle_facing()
        elif event.button == 3:
            # Botão direito: inicia charge no Caçador/Magneto.
            if (
                not scene.ship.is_entering
                and scene.can_handle_gameplay_actions()
                and scene.ship.profile.has_charge_shot
                and not scene.ship.charge_shot_active
            ):
                scene.ship.start_charge()

    def _handle_mousebuttonup(self, event: pygame.event.Event) -> None:
        scene = self.scene
        # Caçador/Magneto: soltar botão esquerdo ou direito dispara o charge.
        if (
            event.button in (1, 3)
            and scene.ship.profile.has_charge_shot
            and scene.ship.charge_shot_active
            and not scene.ship.is_entering
            and scene.can_handle_gameplay_actions()
        ):
            if scene.ship.charge_shot_progress >= 1.0:
                scene.shooting.fire(scene.ship, scene.player_damage_multiplier)
            else:
                scene.ship.cancel_charge()

    def _handle_keyup(self, event: pygame.event.Event) -> None:
        scene = self.scene
        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
            if (
                scene.ship.profile.has_charge_shot
                and scene.ship.charge_shot_active
                and not scene.ship.is_entering
                and scene.can_handle_gameplay_actions()
            ):
                if scene.ship.charge_shot_progress >= 1.0:
                    scene.shooting.fire(scene.ship, scene.player_damage_multiplier)
                else:
                    scene.ship.cancel_charge()

    # ------------------------------------------------------------------
    # Gamepad
    # ------------------------------------------------------------------

    def _slot_for_instance_id(self, instance_id: int) -> Optional["PlayerSlot"]:
        """Resolve o slot do roster a partir do `instance_id` do evento.

        Retorna None se o gamepad emissor não está mapeado a nenhum slot
        (orphan event, controle desconectado entre evento e processamento, etc.).
        """
        scene = self.scene
        gp_slot_idx = scene.app.gamepad.slot_of_instance_id(instance_id)
        if gp_slot_idx is None:
            return None
        for slot in scene.roster.all_slots():
            if slot.gamepad_slot == gp_slot_idx:
                return slot
        return None

    def _handle_gamepad_button(self, button: int, instance_id: int) -> None:
        from ..core.gamepad import XboxButton

        scene = self.scene
        # Start sempre abre pausa — qualquer controle, mesmo durante entry
        # ou modo de seleção. Não precisa resolver slot (pausa é global).
        if button == XboxButton.START:
            scene.upgrade_select_mode = False
            from ..scenes.paused import PausedScene

            scene.app.states.push(PausedScene(scene.app, previous_scene=scene))
            return

        slot = self._slot_for_instance_id(instance_id)
        if slot is None or slot.is_dead:
            return

        ship = slot.ship
        if ship.is_entering or not scene.can_handle_gameplay_actions():
            return

        is_primary = slot is scene.roster.primary()

        # Modo de seleção de upgrade é exclusivo do P1 (upgrades pertencem
        # ao perfil dele). P2 nesses botões: no-op.
        if scene.upgrade_select_mode and is_primary:
            if button == XboxButton.A:
                scene.confirm_upgrade_select()
            elif button == XboxButton.B:
                scene.upgrade_select_mode = False
            elif button == XboxButton.LB:
                scene.navigate_upgrade_select(+1)
            elif button == XboxButton.RB:
                scene.navigate_upgrade_select(-1)
            return

        # Tiro normal sai do RT via ``hold_shoot``. A/X/Y ficam livres para
        # Cofre e cycle. Y também é o botão de revive (held); para evitar
        # consumo indevido do Cofre slot 0 quando o jogador está tentando
        # reviver, suprimimos o activate se ele está dentro de algum beacon.
        if button == XboxButton.A:
            scene.activate_stored_powerup_for(slot, 1)  # Cofre E
        elif button == XboxButton.X:
            ship.cycle_facing()
        elif button == XboxButton.Y:
            if not scene.slot_inside_any_beacon(slot):
                scene.activate_stored_powerup_for(slot, 0)  # Cofre Q

    def _handle_gamepad_hat(self, value: tuple[int, int], instance_id: int) -> None:
        """D-pad ↑ alterna o modo de seleção de upgrades — somente P1."""
        slot = self._slot_for_instance_id(instance_id)
        if slot is None or slot is not self.scene.roster.primary():
            return
        if slot.ship.is_entering or not self.scene.can_handle_gameplay_actions():
            return
        _x, y = value
        if y > 0:
            self.scene.toggle_upgrade_select_mode()

    def _handle_gamepad_axis(self, axis: int, value: float, instance_id: int) -> None:
        """LT analógico é o botão único de habilidade especial.

        - Naves com ``has_dash`` (Fantasma): aperto do LT executa dash na
          direção atual do stick esquerdo.
        - Naves com ``has_charge_shot`` (Caçador, Magneto): segurar o LT
          carrega o tiro; soltar com a carga cheia dispara o laser/teleguiado,
          soltar antes cancela.

        Roteado por `instance_id` para o slot correto (P1 ou P2). Calibração
        e estado de "pressionado" são mantidos por slot — gamepads PS4-likes
        e XInput podem ter layouts/repouso diferentes.
        """
        from ..core.gamepad import GamepadManager

        scene = self.scene
        gp = scene.app.gamepad
        gp_slot_idx = gp.slot_of_instance_id(instance_id)
        if gp_slot_idx is None:
            return
        # `slot_axis_lt(slot)` resolve per-slot — necessário em coop quando
        # P1 e P2 usam controles de layouts diferentes (XInput vs PS4-like).
        # Antes usávamos `gp.axis_lt` global (sempre slot 0), o que fazia
        # eventos do LT do P2 nunca casarem se ele tinha layout diferente.
        if axis != gp.slot_axis_lt(gp_slot_idx):
            return

        # Defesa contra falsa detecção, por slot.
        if value <= -0.5:
            self._lt_calibrated[gp_slot_idx] = True
        if not self._lt_calibrated.get(gp_slot_idx, False):
            return
        normalized = (value + 1.0) * 0.5
        pressed = normalized > GamepadManager.TRIGGER_THRESHOLD
        prev_pressed = self._lt_pressed.get(gp_slot_idx, False)
        if pressed == prev_pressed:
            return
        self._lt_pressed[gp_slot_idx] = pressed

        slot = self._slot_for_instance_id(instance_id)
        if slot is None or slot.is_dead:
            return
        ship = slot.ship
        if ship.is_entering or not scene.can_handle_gameplay_actions():
            return

        profile = ship.profile

        # Dash dispara no instante do press, sem segurar.
        if pressed and profile.has_dash:
            move_vec = self._gamepad_dash_vector(gp_slot_idx)
            ship.try_dash(move_vec)

        # Charge shot precisa de hold/release.
        if profile.has_charge_shot:
            if pressed and not ship.charge_shot_active:
                ship.start_charge()
            elif not pressed and ship.charge_shot_active:
                if ship.charge_shot_progress >= 1.0:
                    scene.shooting.fire(ship, scene.player_damage_multiplier)
                else:
                    ship.cancel_charge()

    def _gamepad_dash_vector(self, gp_slot_idx: int = 0) -> pygame.math.Vector2:
        """Direção do dash via stick esquerdo do slot (fallback hold actions)."""
        scene = self.scene
        gx, gy = scene.app.input.gamepad_movement_vector_for(
            scene.app.gamepad, slot=gp_slot_idx
        )
        if gx != 0.0 or gy != 0.0:
            vec = pygame.math.Vector2(gx, gy)
            if vec.length() > 0:
                vec.normalize_ip()
            return vec
        # Fallback: WASD se o usuário estiver com teclado em paralelo.
        held = scene.app.input.poll_held(scene.app.gamepad)
        move_vec = pygame.math.Vector2(0, 0)
        if "hold_left" in held:
            move_vec.x -= 1
        if "hold_right" in held:
            move_vec.x += 1
        if "hold_up" in held:
            move_vec.y -= 1
        if "hold_down" in held:
            move_vec.y += 1
        return move_vec

    # ------------------------------------------------------------------
    # Teclas de upgrade
    # ------------------------------------------------------------------

    def _handle_upgrade_key(self, event: pygame.event.Event) -> None:
        """Ativa o slot de upgrade correspondente à tecla pressionada."""
        from ..core.upgrades_config import UPGRADE_SLOT_COUNT, DEFAULT_KEYBINDINGS

        scene = self.scene
        try:
            keybinds = scene.player_profile.upgrade_keybindings
            for i, keycode in enumerate(keybinds[:UPGRADE_SLOT_COUNT]):
                if event.key == keycode:
                    scene.activate_upgrade_slot(i)
                    return
        except (AttributeError, TypeError):
            for i, keycode in enumerate(DEFAULT_KEYBINDINGS[:UPGRADE_SLOT_COUNT]):
                if event.key == keycode:
                    scene.activate_upgrade_slot(i)
                    return
