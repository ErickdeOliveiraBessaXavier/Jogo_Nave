"""CollisionOrchestrator — orquestração de colisões de um frame de gameplay.

Extraído da `PlayingScene` (§9). Roda todos os passes de colisão do frame
(projéteis vs inimigos/formações/boss, dano à nave, spikes, zonas) e RETORNA um
`CollisionResult` (ganho de score já multiplicado, inimigos abatidos, floating
scores prontos) que a cena APLICA. Inverte o padrão do `RenderFrame`: a cena monta
o frame para o render consumir; aqui o orquestrador computa e a cena aplica.

Não referencia a cena: recebe os sistemas de domínio (entity_manager, collisions,
roster, boss_controller, level_controller) por construtor e callbacks/acessores
para o que é estado da cena — o roteamento de hit à nave (`on_ship_hit`, chamado
IMEDIATAMENTE para preservar a ordem/invuln entre fontes de dano no mesmo frame),
o `dt` do frame, o estado do multiplicador de score e o threshold de agrupamento.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Sequence, cast

from ..entities.projectiles.spike_boss_laser import SpikeBossLaser

if TYPE_CHECKING:
    from ..core.spatial_grid import SpatialGrid
    from ..systems.collision_protocols import Enemy
    from ..systems.entity_manager import EntityManager
    from ..systems.player_slot import PlayerSlot


@dataclass
class CollisionResult:
    """Efeitos de um frame de colisões que a cena aplica ao seu estado."""

    score_gain: int = 0
    enemies_destroyed: int = 0
    # (x, y, score) já com o multiplicador aplicado — prontos para emitir.
    floating_scores: list[tuple[float, float, int]] = field(default_factory=list)


class CollisionOrchestrator:
    def __init__(
        self,
        *,
        entity_manager: Any,
        collisions: Any,
        roster: Any,
        boss_controller: Any,
        level_controller: Any,
        on_ship_hit: Callable[["PlayerSlot"], None],
        get_last_dt: Callable[[], float],
        get_multiplier_state: Callable[[], tuple[bool, float]],
        get_batch_threshold: Callable[[], float],
    ) -> None:
        # Nomes iguais aos da cena para manter os corpos dos passes verbatim.
        self.entity_manager = entity_manager
        self.collisions = collisions
        self.roster = roster
        self.boss_controller = boss_controller
        self.level_controller = level_controller
        self._on_ship_hit = on_ship_hit
        self._get_last_dt = get_last_dt
        self._get_multiplier_state = get_multiplier_state
        self._get_batch_threshold = get_batch_threshold

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def run(self) -> CollisionResult:
        """Roda os passes de colisão do frame e devolve os efeitos p/ a cena aplicar.

        Ship-hits são roteados via `on_ship_hit` DURANTE o run (imediato), na mesma
        ordem do código original — a invulnerabilidade que o 1º hit ativa suprime os
        seguintes no mesmo frame, então a ordem importa. Score/kills/floating scores
        são acumulados no resultado e aplicados pela cena depois (ordem irrelevante).
        """
        result = CollisionResult()
        enemy_grid = self.entity_manager.enemy_spatial_grid

        gain, destroyed, score_events, ship_hits_proj = (
            self._check_projectile_vs_enemies(enemy_grid)
        )
        gain, destroyed, score_events, ship_hits_form = (
            self._check_formation_collisions(gain, destroyed, score_events)
        )

        # Mine/fire zones devolvem set de `id(ship)` atingidos. Rotear o hit
        # ao slot dono — ambos os players tomam dano em armadilhas.
        zone_ship_hits = ship_hits_proj | ship_hits_form
        if zone_ship_hits:
            for slot in self.roster.alive_slots():
                if id(slot.ship) in zone_ship_hits:
                    self._on_ship_hit(slot)

        batched_events = self._batch_floating_scores(
            score_events, proximity_threshold=self._get_batch_threshold()
        )
        for x, y, pts in batched_events:
            result.floating_scores.append((x, y, self._apply_score_multiplier(pts)))

        result.score_gain += self._apply_score_multiplier(gain)
        result.enemies_destroyed = destroyed

        if self.entity_manager.spikes:
            all_player_projectiles = (
                self.entity_manager.bullets + self.entity_manager.mini_ship_bullets
            )
            spike_gain = self.collisions.projectiles_vs_spikes(
                all_player_projectiles,
                self.entity_manager.spike_spatial_grid,
                self.entity_manager,
            )
            active, value = self._get_multiplier_state()
            if active:
                spike_gain = int(spike_gain * value)
            result.score_gain += spike_gain

        # Nave vs. inimigos (físico) — per-slot
        for slot in self.roster.alive_slots():
            if self.collisions.ship_vs_enemies(
                slot.ship, enemy_grid, self.entity_manager
            ):
                self._on_ship_hit(slot)

        result.score_gain += self._check_boss_collisions(0)

        # Balas vs. objetos indestrutíveis
        self.collisions.bullets_vs_boss_squares(
            self.entity_manager.bullets,
            self.entity_manager.boss_squares,
            self.entity_manager,
        )

        if self.boss_controller.boss_type == "slime":
            self.collisions.bullets_vs_slime_drips(
                self.entity_manager.bullets,
                self.entity_manager.slime_drips,
                self.entity_manager,
            )

        # Damage per-slot: cada nave recebe os ataques que efetivamente acertam.
        for slot in self.roster.alive_slots():
            self._check_ship_damage(slot)

        return result

    # ------------------------------------------------------------------
    # Score (helpers)
    # ------------------------------------------------------------------

    def _apply_score_multiplier(self, pts: int) -> int:
        """Aplica multiplicador de score base + eventual bônus ativo."""
        multiplier = self.level_controller.base_score_multiplier
        active, value = self._get_multiplier_state()
        if active:
            multiplier *= value
        return int(pts * multiplier)

    def _batch_floating_scores(
        self,
        score_events: list[tuple[float, float, int]],
        proximity_threshold: float = 60.0,
    ) -> list[tuple[float, float, int]]:
        """Agrupa score events próximos num único evento somado.

        Para poucos eventos (≤8), usa O(n²) simples.
        Para muitos eventos, usa grid spatial para melhor performance.
        """
        if not score_events:
            return []

        # Para poucos eventos, o custo O(n²) é negligenciável
        if len(score_events) <= 8:
            return self._batch_floating_scores_quadratic(
                score_events, proximity_threshold
            )

        # Grid binning para muitos eventos (picos de dano)
        cell_size = proximity_threshold
        buckets: dict[tuple[int, int], list[tuple[float, float, int]]] = {}

        for x, y, pts in score_events:
            key = (int(x // cell_size), int(y // cell_size))
            if key not in buckets:
                buckets[key] = []
            buckets[key].append((x, y, pts))

        # Agregar pontos dentro de cada célula
        batched: list[tuple[float, float, int]] = []
        for event_list in buckets.values():
            if not event_list:
                continue
            avg_x = sum(e[0] for e in event_list) / len(event_list)
            avg_y = sum(e[1] for e in event_list) / len(event_list)
            total_pts = sum(e[2] for e in event_list)
            batched.append((avg_x, avg_y, total_pts))

        return batched

    def _batch_floating_scores_quadratic(
        self,
        score_events: list[tuple[float, float, int]],
        proximity_threshold: float,
    ) -> list[tuple[float, float, int]]:
        """Batching O(n²) para poucos eventos (manutenção de compatibilidade)."""
        batched: list[tuple[float, float, int]] = []
        used = [False] * len(score_events)

        for i, (x1, y1, pts1) in enumerate(score_events):
            if used[i]:
                continue
            batch_x, batch_y, batch_pts, batch_count = x1, y1, pts1, 1
            used[i] = True

            for j, (x2, y2, pts2) in enumerate(score_events):
                if used[j] or i == j:
                    continue
                dist = math.hypot(x2 - x1, y2 - y1)
                if dist <= proximity_threshold:
                    batch_x = (batch_x * batch_count + x2) / (batch_count + 1)
                    batch_y = (batch_y * batch_count + y2) / (batch_count + 1)
                    batch_pts += pts2
                    batch_count += 1
                    used[j] = True

            batched.append((batch_x, batch_y, batch_pts))

        return batched

    # ------------------------------------------------------------------
    # Passes de colisão
    # ------------------------------------------------------------------

    def _check_projectile_vs_enemies(
        self, enemy_grid: "SpatialGrid[Any]"
    ) -> tuple[int, int, list[tuple[float, float, int]], set[int]]:
        """Projéteis da nave vs. inimigos normais. Retorna (score, kills, events, ship_hits).

        `ship_hits` é um set de `id(ship)` para naves atingidas por mine/fire zones.
        """
        enemies_view = cast(Sequence["Enemy"], self.entity_manager.enemies)
        alive_ships = [slot.ship for slot in self.roster.alive_slots()]

        all_player_projectiles = (
            self.entity_manager.bullets + self.entity_manager.mini_ship_bullets
        )
        # Campos que bloqueiam tiros (parede do Tesla Twin, campo do Jammer Node):
        # destroem os projéteis da nave que os cruzam antes de atingir inimigos
        # atrás deles. Detecção duck-typed via `projectile_fields()` (§5).
        self.collisions.projectiles_vs_blocker_fields(
            all_player_projectiles, self.entity_manager.enemies
        )
        # Mirror Pylon reflete os tiros que cruzam a face espelhada (vira-os em
        # bolts inimigos). Roda no mesmo ponto, antes de atingir inimigos atrás.
        self.collisions.projectiles_vs_reflectors(
            all_player_projectiles, self.entity_manager.enemies, self.entity_manager
        )
        gain, destroyed, score_events = self.collisions.projectiles_vs_enemies(
            all_player_projectiles,
            enemy_grid,
            self.entity_manager,
        )

        laser_gain, laser_destroyed, laser_events = (
            self.collisions.player_lasers_vs_enemies(
                self.entity_manager.player_lasers,
                enemies_view,
                self.entity_manager.floating_scores,
                self.entity_manager,
                enemy_grid,
            )
        )
        gain += laser_gain
        destroyed += laser_destroyed
        score_events.extend(laser_events)

        # Orbes da Torreta Orbital são destrutíveis pelos tiros da nave (balas e
        # lasers), impedindo que cheguem ao ponto memorizado e virem campo.
        if self.entity_manager.orbital_orbs:
            self.collisions.player_shots_vs_orbital_orbs(
                self.entity_manager.orbital_orbs,
                all_player_projectiles,
                self.entity_manager.player_lasers,
                self.entity_manager,
            )

        cacador_gain, cacador_destroyed, cacador_events = (
            self.collisions.cacador_lasers_vs_enemies(
                self.entity_manager.cacador_lasers,
                enemies_view,
                self.entity_manager.floating_scores,
                self.entity_manager,
                enemy_grid,
            )
        )
        gain += cacador_gain
        destroyed += cacador_destroyed
        score_events.extend(cacador_events)

        homing_gain, homing_destroyed, homing_events = (
            self.collisions.homing_bullets_vs_enemies(
                self.entity_manager.homing_bullets,
                enemy_grid,
                self.entity_manager,
            )
        )
        gain += homing_gain
        destroyed += homing_destroyed
        score_events.extend(homing_events)

        upgrade_dt = self._get_last_dt()
        if self.entity_manager.orbital_shields:
            os_gain, os_destroyed, os_events = (
                self.collisions.orbital_shields_vs_enemies(
                    self.entity_manager.orbital_shields,
                    enemy_grid,
                    upgrade_dt,
                    self.entity_manager,
                )
            )
            gain += os_gain
            destroyed += os_destroyed
            score_events.extend(os_events)

        if self.entity_manager.plasma_beams:
            pb_gain, pb_destroyed, pb_events = (
                self.collisions.plasma_beams_vs_enemies(
                    self.entity_manager.plasma_beams,
                    enemy_grid,
                    upgrade_dt,
                    self.entity_manager,
                )
            )
            gain += pb_gain
            destroyed += pb_destroyed
            score_events.extend(pb_events)

        if self.entity_manager.coop_links:
            cl_gain, cl_destroyed, cl_events = (
                self.collisions.coop_links_vs_enemies(
                    self.entity_manager.coop_links,
                    enemy_grid,
                    upgrade_dt,
                    self.entity_manager,
                )
            )
            gain += cl_gain
            destroyed += cl_destroyed
            score_events.extend(cl_events)

        mine_gain, mine_destroyed, mine_events, ship_hits = (
            self.collisions.check_mine_explosions(
                enemies_view,
                self.entity_manager.mine_explosions,
                alive_ships,
                self.entity_manager,
            )
        )
        gain += mine_gain
        destroyed += mine_destroyed
        score_events.extend(mine_events)

        # Blasts de área one-shot (ex.: explosão do núcleo do CyberTank) — dano à
        # nave no raio telegrafado, reusando o roteador de explosão de mina.
        if self.entity_manager.area_blasts:
            for bx, by, br in self.entity_manager.area_blasts:
                ship_hits |= self.collisions.handle_mine_explosion(
                    bx, by, int(br), alive_ships, self.entity_manager
                )
            self.entity_manager.area_blasts.clear()

        if self.entity_manager.implosion_pool.active:
            ip_gain, ip_dest, ip_events = (
                self.collisions.implosion_pulses_vs_enemies(
                    self.entity_manager.implosion_pool.active,
                    enemy_grid,
                    self.entity_manager,
                )
            )
            gain += ip_gain
            destroyed += ip_dest
            score_events.extend(ip_events)

        if self.entity_manager.ice_poison_zones:
            iz_gain, iz_dest, iz_events = self.collisions.ice_poison_zones_vs_entities(
                self.entity_manager.ice_poison_zones,
                enemies_view,
                alive_ships,
                self.entity_manager,
            )
            gain += iz_gain
            destroyed += iz_dest
            score_events.extend(iz_events)

        if self.entity_manager.fire_zones:
            fz_gain, fz_dest, fz_events, fz_ship_hits = (
                self.collisions.fire_zones_vs_entities(
                    self.entity_manager.fire_zones,
                    enemies_view,
                    alive_ships,
                    self.entity_manager,
                )
            )
            gain += fz_gain
            destroyed += fz_dest
            score_events.extend(fz_events)
            ship_hits |= fz_ship_hits

        # Campos elétricos deixados pelos orbes da Torreta Orbital: dano contínuo
        # + debuff de paralisia a quem encosta. Não pontuam nem ferem inimigos.
        if self.entity_manager.electric_fields:
            ship_hits |= self.collisions.electric_fields_vs_ships(
                self.entity_manager.electric_fields,
                alive_ships,
                self.entity_manager,
            )

        return gain, destroyed, score_events, ship_hits

    def _check_formation_collisions(
        self, gain: int, destroyed: int, score_events: list[tuple[float, float, int]]
    ) -> tuple[int, int, list[tuple[float, float, int]], set[int]]:
        """Colisões de área vs. formações e inimigos avulsos.

        Retorna ship_hits como set de `id(ship)` para naves atingidas por
        mine/fire zones (varredura de formações e inimigos avulsos).
        """
        ship_hits: set[int] = set()
        alive_ships = [slot.ship for slot in self.roster.alive_slots()]

        formation_enemy_ids = {
            id(enemy)
            for formation in self.entity_manager.formations
            for enemy in formation.get_enemies()
        }
        enemies_view = [
            enemy
            for enemy in self.entity_manager.enemies
            if id(enemy) not in formation_enemy_ids
        ]

        for formation in self.entity_manager.formations:
            fe = formation.get_enemies()

            f_gain, f_dest, f_events, f_ship_hits = (
                self.collisions.check_mine_explosions(
                    fe,
                    self.entity_manager.mine_explosions,
                    alive_ships,
                    self.entity_manager,
                )
            )
            gain += f_gain
            destroyed += f_dest
            score_events.extend(f_events)
            ship_hits |= f_ship_hits

            if self.entity_manager.ice_poison_zones:
                iz_gain, iz_dest, iz_events = (
                    self.collisions.ice_poison_zones_vs_entities(
                        self.entity_manager.ice_poison_zones,
                        fe,
                        alive_ships,
                        self.entity_manager,
                    )
                )
                gain += iz_gain
                destroyed += iz_dest
                score_events.extend(iz_events)

            if self.entity_manager.fire_zones:
                fz_gain, fz_dest, fz_events, fz_ship_hits = (
                    self.collisions.fire_zones_vs_entities(
                        self.entity_manager.fire_zones,
                        fe,
                        alive_ships,
                        self.entity_manager,
                    )
                )
                gain += fz_gain
                destroyed += fz_dest
                score_events.extend(fz_events)
                ship_hits |= fz_ship_hits

            if self.entity_manager.cannon_mines:
                cg, cd, ce = self.collisions.cannon_mines_vs_enemies(
                    self.entity_manager.cannon_mines, fe, self.entity_manager
                )
                gain += cg
                destroyed += cd
                score_events.extend(ce)

            if self.entity_manager.explosive_effects:
                eg, ed, ee = self.collisions.explosive_effects_vs_enemies(
                    self.entity_manager.explosive_effects, fe, self.entity_manager
                )
                gain += eg
                destroyed += ed
                score_events.extend(ee)

            if self.entity_manager.air_strike_bombs:
                ag, ad, ae = self.collisions.air_strike_bombs_vs_enemies(
                    self.entity_manager.air_strike_bombs, fe, self.entity_manager
                )
                gain += ag
                destroyed += ad
                score_events.extend(ae)

        if self.entity_manager.explosive_effects:
            eg, ed, ee = self.collisions.explosive_effects_vs_enemies(
                self.entity_manager.explosive_effects, enemies_view, self.entity_manager
            )
            gain += eg
            destroyed += ed
            score_events.extend(ee)

        if self.entity_manager.air_strike_bombs:
            ag, ad, ae = self.collisions.air_strike_bombs_vs_enemies(
                self.entity_manager.air_strike_bombs, enemies_view, self.entity_manager
            )
            gain += ag
            destroyed += ad
            score_events.extend(ae)

        if self.entity_manager.cannon_mines:
            mg, md, me = self.collisions.cannon_mines_vs_enemies(
                self.entity_manager.cannon_mines, enemies_view, self.entity_manager
            )
            gain += mg
            destroyed += md
            score_events.extend(me)

        if self.entity_manager.fire_zones:
            fz_gain, fz_dest, fz_events, fz_ship_hits = (
                self.collisions.fire_zones_vs_entities(
                    self.entity_manager.fire_zones,
                    enemies_view,
                    alive_ships,
                    self.entity_manager,
                )
            )
            gain += fz_gain
            destroyed += fz_dest
            score_events.extend(fz_events)
            ship_hits |= fz_ship_hits

        return gain, destroyed, score_events, ship_hits

    def _check_boss_collisions(self, gain: int) -> int:
        """Todas as colisões envolvendo o boss. Retorna score_gain total."""
        score_gain = 0
        boss = self.entity_manager.boss

        if not (boss and self.boss_controller.boss_type):
            return gain

        all_player_projectiles = (
            self.entity_manager.bullets + self.entity_manager.mini_ship_bullets
        )
        # Barreira FÍSICA (corpo sólido): bloqueia/destrói os tiros SEM dano ao corpo.
        # Conceito separado do passe de dano abaixo. No-op em bosses sem barreira ativa.
        self.collisions.projectiles_vs_boss_barrier(
            all_player_projectiles,
            boss,  # type: ignore[arg-type]
            self.entity_manager,
        )
        score_gain = self.collisions.projectiles_vs_boss(
            all_player_projectiles,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.player_lasers_vs_boss(
            self.entity_manager.player_lasers,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.cacador_lasers_vs_boss(
            self.entity_manager.cacador_lasers,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )
        score_gain += self.collisions.homing_bullets_vs_boss(
            self.entity_manager.homing_bullets,
            boss,  # type: ignore[arg-type]
            self.entity_manager.floating_scores,
            self.entity_manager,
        )

        if self.entity_manager.explosive_effects:
            score_gain += self.collisions.explosive_effects_vs_boss(
                self.entity_manager.explosive_effects,
                boss,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

        if self.entity_manager.air_strike_bombs:
            score_gain += self.collisions.air_strike_bombs_vs_boss(
                self.entity_manager.air_strike_bombs,
                boss,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

        if self.entity_manager.cannon_mines:
            score_gain += self.collisions.cannon_mines_vs_boss(
                self.entity_manager.cannon_mines,
                boss,
                self.entity_manager.floating_scores,
                self.entity_manager,
            )

        if self.boss_controller.boss_type == "slime":
            from ..entities.bosses.slime_boss import SlimeBoss

            # Slime drip per-slot: cada gota só pode atingir um ship (consumida
            # ao colidir). Iterar slots vivos resolve sem double-damage.
            slime_boss = cast(SlimeBoss, boss)
            for slot in self.roster.alive_slots():
                drip_damage = slime_boss.check_drip_damage(
                    slot.ship.rect, self.entity_manager
                )
                if drip_damage > 0:
                    self._on_ship_hit(slot)
                    self.level_controller.notify_damage_taken(drip_damage)

        score_gain = self._apply_score_multiplier(score_gain)

        return gain + score_gain

    def _check_ship_damage(self, slot: "PlayerSlot") -> None:
        """Verifica todas as colisões que causam dano à nave do slot."""
        em = self.entity_manager
        ship = slot.ship

        if self.collisions.enemy_projectiles_vs_ship(
            ship, em.alien_bullets, em.enemy_projectile_grid
        ):
            self._on_ship_hit(slot)
        if self.collisions.enemy_projectiles_vs_ship(
            ship, em.serpent_bullets, em.enemy_projectile_grid
        ):
            self._on_ship_hit(slot)
        if self.collisions.enemy_projectiles_vs_ship(
            ship, em.neon_bolts, em.enemy_projectile_grid
        ):
            self._on_ship_hit(slot)
        if self.collisions.eye_laser_vs_ship(ship, em.eye_lasers):
            self._on_ship_hit(slot)

        orb_hit = self.collisions.energy_orbs_vs_ship(
            ship, em.energy_orbs, em.enemy_projectile_grid
        )
        if orb_hit:
            self._on_ship_hit(slot)
            if ship.invuln > 0:
                orb_hit.apply_effect(ship)

        # Contato com orbe da Torreta Orbital: dano; o orbe morre sem virar campo
        # e solta um estouro de energia no impacto (feedback visual).
        if self.collisions.orbital_orbs_vs_ship(
            ship, em.orbital_orbs, em, em.enemy_projectile_grid
        ):
            self._on_ship_hit(slot)

        from ..entities.projectiles.boss_laser import BossLaser

        # A cerca elétrica (Fase 3) também vive em boss_lasers, mas é tratada à parte:
        # além do dano, aplica o debuff de paralisia (reuso do sistema elétrico). É
        # identificada por class attribute (`applies_paralysis`), não por isinstance (§5).
        fence_beams = [
            laser for laser in em.boss_lasers
            if isinstance(laser, BossLaser) and getattr(laser, "applies_paralysis", False)
        ]
        boss_lasers = [
            laser for laser in em.boss_lasers
            if isinstance(laser, BossLaser) and not getattr(laser, "applies_paralysis", False)
        ]
        if self.collisions.laser_vs_ship(ship, boss_lasers):
            self._on_ship_hit(slot)

        if fence_beams and self.collisions.fence_vs_ship(ship, fence_beams):
            self._on_ship_hit(slot)

        spike_lasers: list[SpikeBossLaser] = [
            laser for laser in em.boss_lasers if isinstance(laser, SpikeBossLaser)
        ]
        if spike_lasers and self.collisions.spike_boss_laser_vs_ship(
            ship, spike_lasers
        ):
            self._on_ship_hit(slot)

        if self.collisions.ship_vs_spikes(ship, em.spikes, em):
            self._on_ship_hit(slot)
        if self.collisions.ship_vs_boss_squares(ship, em.boss_squares):
            self._on_ship_hit(slot)

        if self.boss_controller.boss_type == "stone_golem" and em.boss:
            self._check_stone_golem_sweep(em, slot)

        if self.boss_controller.boss_type == "mountain_serpent" and em.boss:
            if self.collisions.ship_vs_boss(ship, em.boss, self.entity_manager):
                self._on_ship_hit(slot)

    def _check_stone_golem_sweep(self, em: "EntityManager", slot: "PlayerSlot") -> None:
        """Verifica dano do feixe sweep do StoneGolemBoss contra o slot."""
        from ..entities.bosses.stone_golem_boss import StoneGolemBoss

        golem = cast(StoneGolemBoss, em.boss)
        beam = golem.get_sweep_beam()
        ship = slot.ship
        if not beam or ship.invuln > 0:
            return

        px, py, ex, ey = beam
        sx = float(ship.rect.centerx)
        sy = float(ship.rect.centery)
        dx, dy = ex - px, ey - py
        len_sq = dx * dx + dy * dy
        if len_sq <= 0:
            return

        t = max(0.0, min(1.0, ((sx - px) * dx + (sy - py) * dy) / len_sq))
        closest_x = px + t * dx
        closest_y = py + t * dy
        dist = math.hypot(sx - closest_x, sy - closest_y)
        if dist < golem.SCALE * 2 + ship.rect.width * 0.4:
            self._on_ship_hit(slot)
