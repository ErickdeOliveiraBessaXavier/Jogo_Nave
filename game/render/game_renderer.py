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
from typing import TYPE_CHECKING, Any, Optional, TypedDict, cast

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset
from ..core.upgrades import get_upgrade_icon

if TYPE_CHECKING:
    from ..entities.ship import Ship
    from ..systems.entity_manager import EntityManager
    from .render_frame import RenderFrame


class PowerupUiData(TypedDict):
    color: tuple[int, int, int]
    symbol: str
    label: str


class GameRenderer:
    """
    Gerencia a renderização da cena principal de gameplay.
    Responsável por:
    - Desenhar o background dinâmico.
    - Delegar o desenho de entidades ao EntityManager.
    - Renderizar o HUD (score, vidas, upgrades, combo).
    - Aplicar efeitos de tela como screen-shake e fades.
    """

    # Cores e Símbolos de Power-ups para o HUD
    POWERUP_UI_DATA: dict[str, PowerupUiData] = {
        "shield": {"color": colors.BLUE, "symbol": "S", "label": "ESCUDO"},
        "double_shot": {"color": colors.GREEN, "symbol": "2X", "label": "TIRO DUPLO"},
        "speed": {"color": colors.YELLOW, "symbol": "V", "label": "VELOCIDADE"},
        "score": {"color": colors.MAGENTA, "symbol": "$", "label": "SCORE X1.5"},
        "mini_ships": {"color": colors.CYAN, "symbol": "M", "label": "MINI-SHIPS"},
        "explosive_shot": {"color": colors.ORANGE, "symbol": "EX", "label": "EXPLOSIVOS"},
        "life": {"color": colors.RED, "symbol": "+", "label": "VIDA"},
        "piercing_shot": {"color": colors.PURPLE, "symbol": "P", "label": "PERFURANTE"},
        "rainbow": {"color": colors.WHITE, "symbol": "*", "label": "RAINBOW"},
        "cooldown_haste": {"color": colors.LIGHT_BLUE, "symbol": "CD", "label": "RECARGA"},
        "time_stop": {"color": colors.PURPLE, "symbol": "T", "label": "STOP"},
        "damage_boost": {"color": colors.ORANGE, "symbol": "DMG", "label": "DANO+"},
        "chain_shot": {"color": (80, 220, 255), "symbol": "Z", "label": "RAIO"},
        "repulsion_shield": {"color": (100, 255, 80), "symbol": "W", "label": "VENTO"},
    }

    def __init__(self, base_renderer: Any) -> None:
        self.r = base_renderer
        self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        self.warning_font = get_font(Config.WARNING_FONT_SIZE)
        
        # Fontes do HUD
        self.hud_font_tiny = get_font(10)
        self.hud_font_small = get_font(13)
        self.hud_font_medium = get_font(18)
        self.hud_font_large = get_font(24)
        self.hud_font_score = get_font(32)
        self.hud_font_score_small = get_font(26)

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

        # 6. Novo HUD Organizado
        self._render_unified_hud(frame, self.game_surface)

        # 7. Overlays específicos (Upgrades, Cofre, Combo)
        # Upgrades e Combo agora são chamados dentro de unified_hud para melhor posicionamento
        # Mas mantemos aqui se preferir manter a ordem original de camadas.

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
            self.r.preparation(
                surface, 
                frame.preparation_time_left, 
                stage_name=frame.stage_name, 
                difficulty=frame.difficulty_preset
            )

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

    def _render_unified_hud(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Renderiza todo o HUD de forma integrada e organizada com design simétrico."""
        
        # 1. Caixa Superior Esquerda (Score e Kills)
        self._render_score_kills_box(frame, surface)
        
        # 2. Caixa Superior Direita (Vidas e Powerups)
        self._render_players_status_box(frame, surface)
            
        # 4. Cofre (Cofre é centralizado logo abaixo do topo se houver espaço)
        p2_ship = frame.p2_hud.ship if frame.p2_hud is not None else None
        self._render_storage_slots_hud(frame.ship, surface, p2_ship)
        
        # 5. Upgrades (Bottom Centralizado)
        self._render_upgrades_hud(frame, surface)
        
        # 6. Combo (Bottom Right)
        self._render_combo_hud(frame.ship, surface)

    def _render_score_kills_box(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Renderiza o score e kills em uma caixa adaptativa no canto superior esquerdo."""
        score_text: str = f"{frame.score:06d}"
        kills_text = f"KILLS: {frame.total_enemies_destroyed}"
        
        # Calcular largura necessária
        score_w = self.hud_font_score.size(score_text)[0]
        if score_w > 300:
            score_text = f"{frame.score:.2e}".replace("e+0", "e+").replace("e-0", "e-")
            score_w = self.hud_font_score.size(score_text)[0]
            if score_w > 300:
                score_w = self.hud_font_score_small.size(score_text)[0]
        kills_w = self.hud_font_tiny.size(kills_text)[0]
        content_w = max(score_w, kills_w)
        
        box_padding = 20
        box_w = content_w + (box_padding * 2)
        box_h = 85
        rect = pygame.Rect(15, 0, box_w, box_h)
        
        # Fundo da Caixa
        overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 160), (0, 0, box_w, box_h), 
                         border_bottom_left_radius=15, border_bottom_right_radius=15)
        surface.blit(overlay, rect.topleft)
        
        # Score
        score_font = self.hud_font_score if self.hud_font_score.size(score_text)[0] <= 300 else self.hud_font_score_small
        score_surf = score_font.render(score_text, True, colors.WHITE)
        surface.blit(score_surf, (rect.centerx - score_surf.get_width() // 2, rect.top + 15))
        
        # Kills
        kills_surf = self.hud_font_tiny.render(kills_text, True, colors.GRAY)
        surface.blit(kills_surf, (rect.centerx - kills_surf.get_width() // 2, rect.top + 60))

    def _render_players_status_box(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Renderiza vidas e powerups em uma caixa adaptativa no canto superior direito."""
        p2_hud = frame.p2_hud
        is_coop = p2_hud is not None
        
        # 1. Calcular larguras dos blocos de conteúdo
        # Bloco P1
        p1_lives_txt = str(frame.lives)
        p1_lives_w = self.hud_font_large.size(p1_lives_txt)[0]
        p1_block_w = 32 + 8 + p1_lives_w # Icon (32) + Gap (8) + Text
        
        # Bloco P2 ou Convite
        if is_coop:
            assert p2_hud is not None
            p2_lives_txt = f"{int(p2_hud.beacon_progress * 100)}%" if p2_hud.is_dead else str(p2_hud.lives)
            p2_lives_w = (self.hud_font_small if p2_hud.is_dead else self.hud_font_large).size(p2_lives_txt)[0]
            p2_block_w = 32 + 8 + p2_lives_w
        else:
            invite_w1 = self.hud_font_tiny.size("P2")[0]
            invite_w2 = self.hud_font_small.size("PRESS START")[0]
            p2_block_w = max(invite_w1, invite_w2)

        # 2. Definir dimensões da caixa com base no conteúdo
        internal_gap = 40 # Espaço entre P1 e P2 (space-between feeling)
        side_padding = 20
        box_w = p1_block_w + internal_gap + p2_block_w + (side_padding * 2)
        box_h = 85
        rect = pygame.Rect(Config.SCREEN_WIDTH - box_w - 15, 0, box_w, box_h)
        
        # Fundo da Caixa
        overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 160), (0, 0, box_w, box_h), 
                         border_bottom_left_radius=15, border_bottom_right_radius=15)
        surface.blit(overlay, rect.topleft)
        
        # 3. Renderizar P1 (Alinhado à esquerda da caixa + padding)
        p1_rect = pygame.Rect(rect.left + side_padding, rect.top, p1_block_w, box_h)
        self._render_player_in_box(surface, frame.ship, frame.lives, p1_rect, is_p2=False)
        
        # 4. Renderizar P2 ou Convite (Alinhado à direita da caixa - padding)
        p2_rect = pygame.Rect(rect.right - side_padding - p2_block_w, rect.top, p2_block_w, box_h)
        
        if not is_coop:
            # Convite P2 (Piscando)
            if (pygame.time.get_ticks() // 600) % 2 == 0:
                p2_label = self.hud_font_tiny.render("P2", True, colors.CYAN)
                invite_surf = self.hud_font_small.render("PRESS START", True, colors.WHITE)
                surface.blit(p2_label, (p2_rect.centerx - p2_label.get_width() // 2, p2_rect.top + 20))
                surface.blit(invite_surf, (p2_rect.centerx - invite_surf.get_width() // 2, p2_rect.top + 40))
        else:
            assert p2_hud is not None
            self._render_player_in_box(surface, p2_hud.ship, p2_hud.lives, p2_rect, is_p2=True, p2_info=p2_hud)

    def _render_player_in_box(
        self, 
        surface: pygame.Surface, 
        ship: Ship, 
        lives: int, 
        rect: pygame.Rect, 
        is_p2: bool,
        p2_info: Any = None
    ) -> None:
        """Helper para renderizar info de um jogador dentro de sua área alocada."""
        # 1. Ícone da Nave + Vidas
        if ship and ship.ship_image:
            icon = pygame.transform.scale(ship.ship_image, (32, 32))
            
            # Vidas ou Status Morto
            if is_p2 and p2_info and p2_info.is_dead:
                pct = int(p2_info.beacon_progress * 100)
                txt = self.hud_font_small.render(f"{pct}%", True, colors.CYAN)
                txt_y_offset = 20
            else:
                txt = self.hud_font_large.render(str(lives), True, colors.WHITE)
                txt_y_offset = 14

            # O rect passado já define a largura exata do bloco (Ícone + Gap + Texto)
            # Então apenas desenhamos a partir da esquerda do rect.
            surface.blit(icon, (rect.left, rect.top + 12))
            surface.blit(txt, (rect.left + 40, rect.top + txt_y_offset))

        # 2. Powerups Ativos (Mini ícones na parte de baixo do rect)
        self._render_active_powerups_in_box(surface, ship, rect, is_p2)

    def _render_active_powerups_in_box(self, surface: pygame.Surface, ship: Ship, rect: pygame.Rect, is_p2: bool) -> None:
        """Desenha powerups ativos na linha inferior da caixa do jogador."""
        active: list[tuple[str, float]] = []
        time_checks = [
            (ship.get_invulnerable_time(), "shield", 8.0),
            (ship.get_double_shot_time(), "double_shot", 10.0),
            (ship.get_speed_boost_time(), "speed", 8.0),
            (ship.mini_ships_timer, "mini_ships", 25.0),
            (ship.damage_boost_timer, "damage_boost", 8.0),
            (ship.piercing_shot_timer, "piercing_shot", 7.0),
            (ship.chain_shot_timer, "chain_shot", 8.0),
            (ship.repulsion_shield_timer, "repulsion_shield", 8.0),
        ]
        for time_left, key, total in time_checks:
            if time_left > 0:
                active.append((key, time_left / total))

        if ship.explosive_shots_active and ship.explosive_shots_remaining > 0:
            active.append(("explosive_shot", ship.explosive_shots_remaining / 10.0))
        
        if not active:
            return
            
        icon_size = 20
        gap = 4
        y = rect.top + 55
        
        # Centralizar ícones na área do jogador
        total_w = len(active) * (icon_size + gap) - gap
        curr_x = rect.centerx - total_w // 2
        
        default_data: PowerupUiData = {"color": colors.WHITE, "symbol": "?", "label": "?"}
        for key, ratio in active:
            data = self.POWERUP_UI_DATA.get(key, default_data)
            
            icon_rect = pygame.Rect(curr_x, y, icon_size, icon_size)
            pygame.draw.rect(surface, (20, 20, 30, 180), icon_rect, border_radius=4)
            pygame.draw.rect(surface, data["color"], icon_rect, width=1, border_radius=4)
            
            sym_surf = self.hud_font_tiny.render(data["symbol"], True, data["color"])
            surface.blit(sym_surf, sym_surf.get_rect(center=icon_rect.center))
            
            # Mini barra de progresso horizontal
            pygame.draw.rect(surface, (40, 40, 40), (curr_x, y + icon_size + 1, icon_size, 2))
            pygame.draw.rect(surface, data["color"], (curr_x, y + icon_size + 1, int(icon_size * ratio), 2))
            
            curr_x += icon_size + gap

    def _render_central_hud(self, frame: RenderFrame, surface: pygame.Surface) -> None:
        """Legado. Agora integrado no _render_score_kills_box."""
        pass

    def _render_player_panel(
        self, 
        surface: pygame.Surface, 
        label_text: str, 
        ship: Ship, 
        lives: int, 
        x: int, y: int, 
        is_p2: bool = False,
        is_dead: bool = False,
        beacon_progress: float = 0.0,
        enemies: int | None = None,
        difficulty: DifficultyPreset | None = None
    ) -> None:
        """Legado. Agora integrado no _render_players_status_box."""
        pass

    def _render_active_powerups(self, surface: pygame.Surface, ship: Ship, x: int, y: int, is_p2: bool) -> None:
        """Legado. Agora integrado no _render_active_powerups_in_box."""
        pass

    def _draw_hud_bar(self, surface: pygame.Surface, x: int, y: int, w: int, h: int, ratio: float, color: tuple[int, int, int]) -> None:
        """Desenha uma barra de progresso simples."""
        pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h), border_radius=h//2)
        if ratio > 0:
            fill_w = int(w * ratio)
            pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=h//2)

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

    def _render_p2_hud(self, p2_hud: Any, surface: pygame.Surface) -> None:
        """HUD secundário legado. Agora integrado no _render_unified_hud."""
        pass

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

        # Posicionado no canto inferior direito
        x, y = Config.SCREEN_WIDTH - 150, Config.SCREEN_HEIGHT - 70
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
        """Exibe os slots de powerup armazenados (Cofre)."""

        # Define grupos a renderizar
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

        # Largura total
        total_w = 0
        for i, (g_ship, _, _) in enumerate(groups):
            n = len(g_ship.stored_powerups)
            total_w += n * slot_size + (n - 1) * gap
            if i < len(groups) - 1:
                total_w += group_gap

        # Centralizado abaixo da barra de score
        start_x, y = (Config.SCREEN_WIDTH - total_w) // 2, 65

        cur_x = start_x
        for g_ship, group_label, hint_keys in groups:
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
                    data = self.POWERUP_UI_DATA.get(
                        kind,
                        {
                            "color": (200, 200, 200),
                            "symbol": kind[:2].upper(),
                            "label": kind,
                        },
                    )
                    color = data["color"]
                    center = (slot_size // 2, slot_size // 2 + 4)
                    pygame.draw.circle(slot_surface, color, center, 16)
                    pygame.draw.circle(slot_surface, colors.WHITE, center, 16, 2)
                    symbol = data["symbol"]
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
        """Exibe os slots de upgrades ativos centralizados na parte inferior."""
        active_slots: list[tuple[int, Any]] = [
            (i, upg) for i, upg in enumerate(frame.upgrade_slots) if upg is not None
        ]
        if not active_slots:
            return

        font, font_small = get_font(20), get_font(12)
        slot_w, slot_h = 50, 50
        gap = 10
        pad_x, pad_y = 15, 10
        
        # Calcular dimensões do container
        n = len(active_slots)
        container_w = n * slot_w + (n - 1) * gap + (pad_x * 2)
        container_h = slot_h + (pad_y * 2)
        
        container_rect = pygame.Rect(
            (Config.SCREEN_WIDTH - container_w) // 2,
            Config.SCREEN_HEIGHT - container_h,
            container_w,
            container_h
        )
        
        # Desenhar container (Estilo similar à barra de score)
        overlay = pygame.Surface((container_w, container_h), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 160), (0, 0, container_w, container_h), border_top_left_radius=15, border_top_right_radius=15)
        surface.blit(overlay, container_rect.topleft)

        start_x = container_rect.left + pad_x

        for display_index, (i, upg) in enumerate(active_slots):
            slot_x = start_x + display_index * (slot_w + gap)
            slot_y = container_rect.top + pad_y
            
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

            surface.blit(slot_surface, (slot_x, slot_y))

            if ui["active"]:
                pygame.draw.rect(surface, colors.GREEN, pygame.Rect(slot_x, slot_y, slot_w, slot_h), 3, border_radius=8)

            if frame.upgrade_select_mode and i == frame.upgrade_select_index:
                t_ticks = pygame.time.get_ticks()
                shake_x = int(math.sin(t_ticks / 35.0) * 2)
                shake_y = int(math.cos(t_ticks / 42.0) * 2)
                pygame.draw.rect(surface, colors.CUSTOM_GOLD, pygame.Rect(slot_x - 3 + shake_x, slot_y - 3 + shake_y, slot_w + 6, slot_h + 6), 3, border_radius=10)

        if frame.upgrade_select_mode:
            hint = font_small.render("LB/RB navegar  A confirmar  B cancelar", True, colors.CUSTOM_GOLD)
            surface.blit(hint, (container_rect.centerx - hint.get_width() // 2, container_rect.top - 25))
