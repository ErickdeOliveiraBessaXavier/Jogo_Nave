"""game_renderer.py — Renderizador especializado para a PlayingScene.

Desacopla a lógica de renderização e HUD da cena de gameplay, tratando
o desenho de entidades, efeitos visuais, shake de tela e overlays.

Consome um `RenderFrame` (DTO) construído pela cena por frame. Não acessa
nada de `PlayingScene` diretamente — contrato explícito via `render_frame.py`.
"""

from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING, Any, Optional, cast

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.config import config as Config
from ..core.upgrades import get_upgrade_icon

if TYPE_CHECKING:
    from ..entities.ship import Ship
    from ..systems.entity_manager import EntityManager
    from .render_frame import RenderFrame


class GameRenderer:
    """
    Gerencia a renderização da cena principal de gameplay.
    Responsável por:
    - Desenhar o background dinâmico.
    - Delegar o desenho de entidades ao EntityManager.
    - Renderizar o HUD (score, vidas, upgrades, combo).
    - Aplicar efeitos de tela como screen-shake e fades.
    """

    def __init__(self, base_renderer: Any) -> None:
        self.r = base_renderer
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)

    def render(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Método principal de renderização chamado a cada frame."""

        from ..scenes.playing import GameState
        dt = frame.dt
        speed_multiplier = 1.0
        boss_active = False

        if frame.state == GameState.PREPARING:
            progress = min(
                1.0,
                max(
                    0.0,
                    (Config.PREPARATION_TIME - frame.preparation_time_left)
                    / Config.PREPARATION_TIME,
                ),
            )
            speed_multiplier = 1.0 + (Config.WARP_SPEED_MULTIPLIER - 1.0) * (
                1.0 - progress**2
            )
        else:
            boss_active = bool(
                frame.boss_controller.active
                and frame.entity_manager.boss
                and not frame.entity_manager.boss.dead
            )
            if boss_active:
                speed_multiplier = Config.BOSS_WARP_SPEED_MULTIPLIER

        # 1. Background
        self.r.background(
            self.game_surface,
            dt=dt,
            speed_multiplier=speed_multiplier,
            draw_celestials=not boss_active,
        )

        # 2. Entidades
        current_fps = self.r.current_fps if self.r.current_fps > 0 else 60.0
        intro_active = bool(
            frame.entity_manager.boss
            and getattr(frame.entity_manager.boss, "is_intro_active", False)
        )
        frame.entity_manager.draw(
            self.game_surface,
            frame.ship.rect.centerx,
            frame.ship.rect.centery,
            frame.boss_controller.enemy_visible,
            fps=current_fps,
            draw_boss=not intro_active,
        )

        if frame.show_enemy_hitboxes:
            self._draw_enemy_hitboxes(frame.entity_manager, self.game_surface)

        # 3. Partículas de transição de mundo
        for p in frame.world_transition_thruster_particles:
            px = frame.ship.x + p["offset_x"]
            py = frame.ship.y + p["offset_y"]
            pygame.draw.circle(
                self.game_surface,
                p["color"],
                (int(px), int(py)),
                max(1, int(p["size"])),
            )

        # 4. Nave do jogador (P1 + naves adicionais em multiplayer local)
        if frame.primary_alive:
            frame.ship.draw(self.game_surface)
        for extra_ship in frame.extra_ships:
            extra_ship.draw(self.game_surface)
        # 4b. Beacons de revive de slots mortos (renderer trata como overlay
        # acima das naves para garantir leitura visual do raio).
        for beacon in frame.revival_beacons:
            beacon.draw(self.game_surface)

        # 5. Efeito de entrada de boss (CloudArchmage)
        if intro_active:
            boss = frame.entity_manager.boss
            if boss:
                from ..entities.cloud_archmage_boss import CloudArchmageBoss

                archmage = cast(CloudArchmageBoss, boss)
                overlay_alpha = archmage.get_intro_dim_alpha()
                if overlay_alpha > 0:
                    overlay = pygame.Surface(
                        (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
                    )
                    overlay.fill((0, 0, 0, overlay_alpha))
                    self.game_surface.blit(overlay, (0, 0))
                archmage.draw(self.game_surface)

        self.r.update_fps(dt)

        # 6. HUD Principal
        self.r.hud(
            self.game_surface,
            frame.score,
            frame.lives,
            frame.total_enemies_destroyed,
            frame.ship,
            frame.stage_name,
            frame.difficulty_preset,
            score_multiplier_active=frame.score_multiplier_active,
            score_multiplier_timer=frame.score_multiplier_timer,
            mini_ships_active=frame.ship.mini_ships_timer > 0,
            mini_ships_timer=frame.ship.mini_ships_timer,
            explosive_shots_active=frame.ship.explosive_shots_active,
            explosive_shots_remaining=frame.ship.explosive_shots_remaining,
        )

        # 7. Overlays específicos (Upgrades, Cofre, Combo)
        self._render_upgrades_hud(frame, self.game_surface)
        # Cofre: passa também a nave do P2 — quando ambos têm Cofre, mostra
        # 4 caixas centralizadas (2 do P1, 2 do P2).
        p2_ship = frame.p2_hud.ship if frame.p2_hud is not None else None
        self._render_storage_slots_hud(frame.ship, self.game_surface, p2_ship)
        self._render_combo_hud(frame.ship, self.game_surface)
        # 7b. HUD do Jogador 2 (multiplayer coop)
        if frame.p2_hud is not None:
            self._render_p2_hud(frame.p2_hud, self.game_surface)

        # 8. Debug info
        if frame.show_fps:
            fps_stats = self.r.get_fps_stats()
            fps_text = (
                f"FPS: {fps_stats['fps']:.1f} | "
                f"Avg: {fps_stats['avg_frame_time']:.1f}ms | "
                f"Max: {fps_stats['max_frame_time']:.1f}ms"
            )
            fps_surface = self.r.font_small.render(fps_text, True, colors.YELLOW)
            self.game_surface.blit(fps_surface, (10, Config.SCREEN_HEIGHT - 30))

        if frame.show_enemy_hitboxes:
            hitbox_text = self.r.font_small.render(
                "F7 Hitbox Debug: ON", True, (255, 200, 40)
            )
            self.game_surface.blit(hitbox_text, (10, Config.SCREEN_HEIGHT - 50))

        # 9. Blit final com Screen Shake
        surface.blit(self.game_surface, self._compute_shake_offset(frame))

        # 10. Warning de Boss
        warning_timer = frame.boss_controller.warning_timer
        if warning_timer > 0 and int(warning_timer * 5) % 2 == 1:
            warning_text = self.warning_font.render("WARNING!", True, colors.RED)
            text_rect = warning_text.get_rect(
                center=(Config.SCREEN_WIDTH / 2, Config.SCREEN_HEIGHT / 2)
            )
            surface.blit(warning_text, text_rect)

        # 11. Overlay de preparação
        if frame.state == GameState.PREPARING:
            self.r.preparation(surface, frame.preparation_time_left)

        # 12. Fade-in inicial
        if frame.start_fade_active:
            frame.start_fade_overlay.fill((0, 0, 0, int(frame.start_fade_alpha)))
            surface.blit(frame.start_fade_overlay, (0, 0))

    def _compute_shake_offset(self, frame: RenderFrame) -> tuple[int, int]:
        """Calcula o deslocamento aleatório para o efeito de screen shake."""
        if frame.shake_timer <= 0:
            return (0, 0)
        intensity = frame.shake_intensity
        return (
            random.randint(-intensity, intensity),
            random.randint(-intensity, intensity),
        )

    @staticmethod
    def _get_enemy_contact_hitboxes(enemy: Any) -> tuple[pygame.Rect, ...]:
        """Retorna hitboxes de contato para debug visual, com fallback para rect."""
        getter = getattr(enemy, "get_ship_contact_hitboxes", None)
        if callable(getter):
            raw_hitboxes = cast(Any, getter)()
            hitboxes = tuple(
                r
                for r in raw_hitboxes
                if isinstance(r, pygame.Rect) and r.width > 0 and r.height > 0
            )
            if hitboxes:
                return hitboxes

        enemy_rect = getattr(enemy, "rect", pygame.Rect(0, 0, 0, 0))
        if (
            isinstance(enemy_rect, pygame.Rect)
            and enemy_rect.width > 0
            and enemy_rect.height > 0
        ):
            return (enemy_rect,)
        return ()

    def _draw_enemy_hitboxes(self, em: EntityManager, surface: pygame.Surface) -> None:
        """Overlay de hitboxes para depuração visual."""
        enemies_in_view = em.enemy_spatial_grid.query(
            0, 0, Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        )
        seen: set[int] = set()
        for enemy in enemies_in_view:
            eid = id(enemy)
            if eid in seen or getattr(enemy, "dead", False):
                continue
            seen.add(eid)

            mask_getter = getattr(enemy, "get_collision_mask_data", None)
            has_mask = False
            if callable(mask_getter):
                raw = cast(
                    "tuple[pygame.mask.Mask, tuple[int, int]] | None",
                    mask_getter(),
                )
                if raw is not None:
                    mask, offset = raw
                    mask_w, mask_h = mask.get_size()
                    if mask_w > 0 and mask_h > 0:
                        outline_surf = pygame.Surface((mask_w, mask_h), pygame.SRCALPHA)
                        for px, py in mask.outline():
                            pygame.draw.circle(
                                outline_surf, (255, 120, 0, 220), (px, py), 1
                            )
                        surface.blit(outline_surf, offset)
                        has_mask = True

            if not has_mask:
                for idx, rect in enumerate(self._get_enemy_contact_hitboxes(enemy)):
                    color = (255, 200, 40) if idx == 0 else (40, 220, 255)
                    pygame.draw.rect(surface, color, rect, 2)

    def _render_p2_hud(self, p2_hud: Any, surface: pygame.Surface) -> None:
        """HUD secundário do Jogador 2 (multiplayer coop).

        Posicionado no canto superior direito, abaixo das vidas do P1 (que
        ocupam a linha 10..36). Quando P2 está morto, mostra a barra de
        progresso do beacon de revive no lugar das vidas.
        """
        font_label = get_font(14)
        font_value = get_font(20)
        right_margin = 10
        y = 44  # logo abaixo da linha das vidas do P1

        label = font_label.render("JOGADOR 2", True, colors.CYAN)
        surface.blit(
            label,
            (Config.SCREEN_WIDTH - label.get_width() - right_margin, y),
        )
        y += 18

        if p2_hud.is_dead:
            pct = int(round(p2_hud.beacon_progress * 100))
            # Cor pulsa entre cinza e ciano conforme o progresso aumenta.
            color = (
                int(150 + 105 * p2_hud.beacon_progress),
                int(200 + 50 * p2_hud.beacon_progress),
                255,
            )
            status = font_value.render(f"REVIVE {pct}%", True, color)
            surface.blit(
                status,
                (Config.SCREEN_WIDTH - status.get_width() - right_margin, y),
            )
            return

        lives_surf = font_value.render(
            f"Vidas: {p2_hud.lives}", True, colors.WHITE
        )
        surface.blit(
            lives_surf,
            (Config.SCREEN_WIDTH - lives_surf.get_width() - right_margin, y),
        )
        y += 26

        # Powerup timers ativos do P2.
        ship = p2_hud.ship
        font_small = get_font(13)

        def right_line(txt: str, color: tuple[int, int, int]) -> None:
            nonlocal y
            t = font_small.render(txt, True, color)
            surface.blit(t, (Config.SCREEN_WIDTH - t.get_width() - right_margin, y))
            y += 16

        invuln_s = ship.get_invulnerable_time()
        ds_s = ship.get_double_shot_time()
        sp_s = ship.get_speed_boost_time()
        if invuln_s > 0:
            right_line(f"[S] Escudo: {invuln_s:.1f}s", colors.BLUE)
        if ds_s > 0:
            right_line(f"[2X] Tiro Duplo: {ds_s:.1f}s", colors.GREEN)
        if sp_s > 0:
            right_line(f"[V] Velocidade: {sp_s:.1f}s", colors.YELLOW)

    def _render_combo_hud(self, ship: Ship, surface: pygame.Surface) -> None:
        """Indicador do combo do Reverberador."""
        if ship.profile.combo_damage_per_kill <= 0:
            return

        kills = ship.combo_kills
        bonus = ship.combo_damage_bonus
        cap = ship.profile.combo_damage_cap

        font_label = get_font(14)
        font_value = get_font(22)

        if kills == 0:
            color = (160, 160, 160)
        elif 0 < cap <= bonus:
            pulse = int(40 + 40 * abs(math.sin(time.time() * 6)))
            color = (255, 220 - pulse // 4, 60)
        else:
            fade = min(1.0, bonus / cap) if cap > 0 else min(1.0, bonus)
            color = (
                int(180 + 75 * fade),
                int(180 + 40 * fade),
                int(140 - 80 * fade),
            )

        x, y = 16, Config.SCREEN_HEIGHT - 70
        label = font_label.render("COMBO", True, colors.WHITE)
        surface.blit(label, (x, y))

        bonus_pct = int(round(bonus * 100))
        text = font_value.render(f"x{kills}  +{bonus_pct}%", True, color)
        surface.blit(text, (x, y + 16))

    def _render_storage_slots_hud(
        self,
        ship: Ship,
        surface: pygame.Surface,
        p2_ship: Optional[Ship] = None,
    ) -> None:
        """Exibe os slots de powerup armazenados (Cofre).

        Em coop, se P1 e P2 estiverem ambos com Cofre, mostra 4 caixas
        centralizadas — 2 do P1 e 2 do P2, com pequena separação visual.
        Se só um dos jogadores tem Cofre, mantém o layout single-player.
        """
        from ..core.colors import (
            POWERUP_COOLDOWN_HASTE,
            POWERUP_DAMAGE_BOOST,
            POWERUP_DOUBLE_SHOT,
            POWERUP_LIFE,
            POWERUP_MINI_SHIPS,
            POWERUP_PIERCING_SHOT,
            POWERUP_RAINBOW,
            POWERUP_SCORE,
            POWERUP_SHIELD,
            POWERUP_SPEED,
            POWERUP_TIME_STOP,
        )

        # Define grupos a renderizar (ship, label, hint_keys). Cada grupo é
        # um Cofre completo (todos os slots dele).
        groups: list[tuple[Ship, str, tuple[str, ...]]] = []
        if ship.has_storage_slots():
            groups.append((ship, "P1", ("Q", "E")))
        if p2_ship is not None and p2_ship.has_storage_slots():
            groups.append((p2_ship, "P2", ("Y", "A")))
        if not groups:
            return

        font_label, font_hint, font_icon = get_font(20), get_font(12), get_font(18)
        font_group = get_font(11)
        slot_size, gap, group_gap = 56, 12, 28

        # Largura total: soma das larguras de cada grupo + group_gap entre eles.
        total_w = 0
        for i, (g_ship, _, _) in enumerate(groups):
            n = len(g_ship.stored_powerups)
            total_w += n * slot_size + (n - 1) * gap
            if i < len(groups) - 1:
                total_w += group_gap

        start_x, y = (Config.SCREEN_WIDTH - total_w) // 2, 8

        powerup_colors = {
            "life": POWERUP_LIFE, "shield": POWERUP_SHIELD,
            "double_shot": POWERUP_DOUBLE_SHOT, "speed": POWERUP_SPEED,
            "score": POWERUP_SCORE, "piercing_shot": POWERUP_PIERCING_SHOT,
            "mini_ships": POWERUP_MINI_SHIPS, "rainbow": POWERUP_RAINBOW,
            "cooldown_haste": POWERUP_COOLDOWN_HASTE, "time_stop": POWERUP_TIME_STOP,
            "damage_boost": POWERUP_DAMAGE_BOOST, "chain_shot": (80, 220, 255),
            "repulsion_shield": (100, 255, 80),
        }
        powerup_symbols = {
            "life": "+", "shield": "S", "double_shot": "2X", "speed": "V",
            "score": "$", "piercing_shot": "P", "mini_ships": "M", "rainbow": "*",
            "cooldown_haste": "CD", "time_stop": "T", "damage_boost": "DMG",
            "chain_shot": "⚡", "repulsion_shield": "🛡",
        }

        cur_x = start_x
        for group_idx, (g_ship, group_label, hint_keys) in enumerate(groups):
            slots = g_ship.stored_powerups
            group_w = len(slots) * slot_size + (len(slots) - 1) * gap

            # Label "P1"/"P2" centralizado acima do grupo (apenas em coop).
            if len(groups) > 1:
                label_surf = font_group.render(group_label, True, colors.CYAN)
                surface.blit(
                    label_surf,
                    (cur_x + (group_w - label_surf.get_width()) // 2, y - 14),
                )

            for i, kind in enumerate(slots):
                x = cur_x + i * (slot_size + gap)
                slot_surface = pygame.Surface(
                    (slot_size, slot_size), pygame.SRCALPHA
                )
                pygame.draw.rect(
                    slot_surface,
                    (20, 20, 30, 200),
                    (0, 0, slot_size, slot_size),
                    border_radius=8,
                )

                border_color = (
                    (*colors.YELLOW, 230)
                    if kind is not None
                    else (*colors.GRAY, 160)
                )
                pygame.draw.rect(
                    slot_surface,
                    border_color,
                    (0, 0, slot_size, slot_size),
                    2,
                    border_radius=8,
                )

                key_label = hint_keys[i] if i < len(hint_keys) else str(i + 1)
                slot_surface.blit(
                    font_hint.render(key_label, True, colors.WHITE), (5, 3)
                )

                if kind is not None:
                    color = powerup_colors.get(kind, (200, 200, 200))
                    center = (slot_size // 2, slot_size // 2 + 4)
                    pygame.draw.circle(slot_surface, color, center, 16)
                    pygame.draw.circle(slot_surface, colors.WHITE, center, 16, 2)
                    symbol = powerup_symbols.get(kind, kind[:2].upper())
                    content = font_icon.render(symbol, True, colors.BLACK)
                    slot_surface.blit(content, content.get_rect(center=center))
                else:
                    dash = font_label.render("—", True, (90, 90, 90))
                    slot_surface.blit(
                        dash, dash.get_rect(center=(slot_size // 2, slot_size // 2))
                    )

                surface.blit(slot_surface, (x, y))

            cur_x += group_w + group_gap

    def _render_upgrades_hud(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Exibe os slots de upgrades ativos e seus cooldowns."""
        active_slots = [(i, upg) for i, upg in enumerate(frame.upgrade_slots) if upg is not None]
        if not active_slots:
            return

        font, font_small = get_font(20), get_font(12)
        pad, slot_w, slot_h = 8, 50, 50
        x, y = Config.SCREEN_WIDTH - pad - slot_w, 44

        for display_index, (i, upg) in enumerate(active_slots):
            slot_surface = pygame.Surface((slot_w, slot_h), pygame.SRCALPHA)
            pygame.draw.rect(slot_surface, (30, 30, 30, 180), (0, 0, slot_w, slot_h), border_radius=8)
            pygame.draw.rect(slot_surface, (*colors.WHITE, 200), (0, 0, slot_w, slot_h), 2, border_radius=8)

            try:
                keycode = frame.upgrade_keybindings[i]
                key_label = pygame.key.name(keycode).upper()
            except (IndexError, TypeError):
                key_label = str(i + 1)
            slot_surface.blit(font_small.render(key_label, True, colors.WHITE), (4, 2))

            ui = upg.get_ui_state()
            icon = get_upgrade_icon(str(ui.get("name", "")), str(ui.get("icon_id", "")) if ui.get("icon_id") else None)
            icon_txt = font.render(icon, True, colors.CYAN)
            slot_surface.blit(icon_txt, icon_txt.get_rect(center=(slot_w // 2, slot_h // 2)))

            cd_left = float(ui["cooldown_left"]) if ui.get("cooldown_left") is not None else 0.0
            cd_base = float(ui["cooldown"]) if ui.get("cooldown") is not None else 1.0
            if cd_left > 0.0:
                pct = max(0.0, min(1.0, cd_left / cd_base))
                bar_h = 4
                pygame.draw.rect(slot_surface, (120, 120, 120, 150), (2, slot_h - bar_h - 2, slot_w - 4, bar_h), border_radius=2)
                pygame.draw.rect(slot_surface, (80, 180, 255, 200), (2, slot_h - bar_h - 2, int((slot_w - 4) * pct), bar_h), border_radius=2)

            charges = ui.get("charges_left")
            if charges is not None:
                c_txt = font_small.render(f"{charges}", True, colors.WHITE)
                slot_surface.blit(c_txt, c_txt.get_rect(bottomright=(slot_w - 3, slot_h - 3)))

            slot_x = x - display_index * (slot_w + 6)
            surface.blit(slot_surface, (slot_x, y))

            if ui["active"]:
                pygame.draw.rect(surface, colors.GREEN, pygame.Rect(slot_x, y, slot_w, slot_h), 3, border_radius=8)

            if frame.upgrade_select_mode and i == frame.upgrade_select_index:
                t_ticks = pygame.time.get_ticks()
                shake_x = int(math.sin(t_ticks / 35.0) * 2)
                shake_y = int(math.cos(t_ticks / 42.0) * 2)
                pygame.draw.rect(surface, colors.CUSTOM_GOLD, pygame.Rect(slot_x - 3 + shake_x, y - 3 + shake_y, slot_w + 6, slot_h + 6), 3, border_radius=10)

        if frame.upgrade_select_mode:
            hint = font_small.render("LB/RB navegar  A confirmar  B cancelar", True, colors.CUSTOM_GOLD)
            surface.blit(hint, (Config.SCREEN_WIDTH - pad - hint.get_width(), y + slot_h + 6))
