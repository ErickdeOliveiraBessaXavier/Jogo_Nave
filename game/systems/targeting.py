"""targeting.py — Utilitários puros de targeting de inimigos.

Função compartilhada por `Ship` (charge shot do Caçador, homing) e `MiniShip`
(auto-aim). Lógica única evita duplicação e divergência sutil entre os dois
call sites.

A função é pura: não muta entidades, não emite eventos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Optional

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


def enemy_center(enemy: Any) -> Optional[tuple[float, float]]:
    """Centro geométrico tolerante a inimigos com (w,h) ou (radius)."""
    can_damage_fn = getattr(enemy, "can_take_damage", None)
    if callable(can_damage_fn) and not can_damage_fn():
        return None

    if hasattr(enemy, "w") and hasattr(enemy, "h"):
        return float(enemy.x + enemy.w / 2), float(enemy.y + enemy.h / 2)
    if hasattr(enemy, "radius"):
        return float(enemy.x), float(enemy.y)
    return None


def find_nearest_enemy(
    from_x: float,
    from_y: float,
    entity_manager: "EntityManager",
    max_range_sq: float = float("inf"),
) -> Optional[Any]:
    """Inimigo vivo mais próximo de (from_x, from_y) — None se nada em range.

    Cobre `entity_manager.enemies`, inimigos dentro de formações ativas e o
    boss atual. `max_range_sq` permite restringir a busca por distância ao
    quadrado (evita sqrt no caller); use `float("inf")` para busca ilimitada.
    """
    nearest: Optional[Any] = None
    best_sq = max_range_sq

    # Função auxiliar para verificar se um inimigo é um alvo válido
    def is_targetable(e: Any) -> bool:
        if getattr(e, "dead", False):
            return False
        # Se a entidade possui can_take_damage, respeita o retorno dela
        # (usado por bosses durante entrada/animações)
        can_damage_fn = getattr(e, "can_take_damage", None)
        if callable(can_damage_fn):
            return bool(can_damage_fn())
        return True

    for enemy in entity_manager.enemies:
        if not is_targetable(enemy):
            continue
        center = enemy_center(enemy)
        if center is None:
            continue
        dx = center[0] - from_x
        dy = center[1] - from_y
        dist_sq = dx * dx + dy * dy
        if dist_sq < best_sq:
            best_sq = dist_sq
            nearest = enemy

    for formation in entity_manager.formations:
        for enemy in formation.get_enemies():
            if not is_targetable(enemy):
                continue
            center = enemy_center(enemy)
            if center is None:
                continue
            dx = center[0] - from_x
            dy = center[1] - from_y
            dist_sq = dx * dx + dy * dy
            if dist_sq < best_sq:
                best_sq = dist_sq
                nearest = enemy

    boss = entity_manager.boss
    if boss is not None and is_targetable(boss):
        # Usar enemy_center para o boss também, garantindo consistência
        center = enemy_center(boss)
        if center is not None:
            dx = center[0] - from_x
            dy = center[1] - from_y
            dist_sq = dx * dx + dy * dy
            if dist_sq < best_sq:
                nearest = boss

    return nearest


def find_nearest_in_list(
    from_x: float,
    from_y: float,
    enemies: Iterable[Any],
    max_range_sq: float = float("inf"),
) -> Optional[Any]:
    """Variante que opera sobre uma lista pré-filtrada — útil para o MiniShip,
    que recebe a lista combinada do caller sem acesso ao EntityManager."""
    nearest: Optional[Any] = None
    best_sq = max_range_sq

    # Função auxiliar para verificar se um inimigo é um alvo válido
    def is_targetable(e: Any) -> bool:
        if getattr(e, "dead", False):
            return False
        can_damage_fn = getattr(e, "can_take_damage", None)
        if callable(can_damage_fn):
            return bool(can_damage_fn())
        return True

    for enemy in enemies:
        if not is_targetable(enemy):
            continue
        center = enemy_center(enemy)
        if center is None:
            continue
        dx = center[0] - from_x
        dy = center[1] - from_y
        dist_sq = dx * dx + dy * dy
        if dist_sq < best_sq:
            best_sq = dist_sq
            nearest = enemy

    return nearest
