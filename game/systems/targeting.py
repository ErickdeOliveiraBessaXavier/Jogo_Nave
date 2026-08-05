"""targeting.py — Utilitários puros de targeting de inimigos.

Função compartilhada por `Ship` (charge shot do Caçador, homing) e `MiniShip`
(auto-aim). Lógica única evita duplicação e divergência sutil entre os dois
call sites.

A função é pura: não muta entidades, não emite eventos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Optional, cast

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


def target_point(enemy: Any) -> Optional[tuple[float, float]]:
    """Ponto de mira/colisão do inimigo, preferindo a geometria precisa.

    Prioriza ``collision_circle()`` — o hitbox canônico que os sistemas de
    colisão, chain shot e AoE consomem. Isso é essencial para inimigos cujo
    ``(x, y, w, h)`` não corresponde à posição real: o ``MountainSerpentBoss``,
    por exemplo, expõe ``x/y/w/h`` como bounds fixos de tela inteira, mas o
    ``collision_circle`` segue a cabeça móvel. Mirar em ``x + w/2`` levaria as
    escoltas a um ponto invisível no topo central da tela.

    Cai para ``(x + w/2, y + h/2)`` e depois ``(x, y)`` (entidades por raio).
    """
    collision_circle = getattr(enemy, "collision_circle", None)
    if callable(collision_circle):
        cx, cy, _r = cast("tuple[float, float, float]", collision_circle())
        return float(cx), float(cy)
    if hasattr(enemy, "w") and hasattr(enemy, "h"):
        return float(enemy.x + enemy.w / 2), float(enemy.y + enemy.h / 2)
    if hasattr(enemy, "radius"):
        return float(enemy.x), float(enemy.y)
    return None


def is_targetable(enemy: Any) -> bool:
    """True se o inimigo está vivo e pode receber dano agora.

    Bosses em entrada/animação ou em fase invulnerável (ex.: a cabeça da
    Serpente enquanto os blocos laterais estão de pé) expõem
    ``can_take_damage()`` retornando False — devem ser ignorados por toda a
    seleção de alvo: auto-aim do MiniShip, caça do Wingman e homing da Ship.
    """
    if getattr(enemy, "dead", False):
        return False
    can_damage_fn = getattr(enemy, "can_take_damage", None)
    if callable(can_damage_fn):
        return bool(can_damage_fn())
    return True


def is_on_screen(entity: Any, screen_w: float, screen_h: float) -> bool:
    """True se o rect da entidade intersecta a área visível (teste ESTRITO).

    Estrito quer dizer: um inimigo parado acima do topo (``y = -100``, formação
    ainda entrando) NÃO conta, nem um que já saiu por qualquer borda. É o oposto
    do ``_is_enemy_off_screen`` do `EntityManager`, que por regra de gameplay
    mantém "vivo" quem está prestes a entrar.

    Vive aqui, junto de `is_targetable`, porque toda seleção de alvo precisa da
    MESMA noção de visível: perseguir quem está saindo de cena gasta o projétil
    num alvo que o jogador já não vê. Duas definições de "na tela" divergem com
    o tempo — o `EntityManager.is_on_screen` delega para cá.
    """
    ew = getattr(entity, "w", getattr(getattr(entity, "rect", None), "width", 50))
    eh = getattr(entity, "h", getattr(getattr(entity, "rect", None), "height", 50))
    x = getattr(entity, "x", 0.0)
    y = getattr(entity, "y", 0.0)
    return x + ew > 0 and x < screen_w and y + eh > 0 and y < screen_h


def is_huntable(enemy: Any, screen_w: float, screen_h: float) -> bool:
    """Alvo legítimo para um projétil teleguiado: pode tomar dano E está visível.

    A visibilidade importa tanto quanto a vulnerabilidade. Um inimigo que está
    deixando a tela continua alvejável por um instante, e um teleguiado travado
    nele vira escolta: sai junto pela borda e morre fora do campo de visão, sem
    acertar nada. Do lado do jogador isso lê como o tiro ter ignorado os
    inimigos que ainda estavam ali.
    """
    return is_targetable(enemy) and is_on_screen(enemy, screen_w, screen_h)


def enemy_center(enemy: Any) -> Optional[tuple[float, float]]:
    """Como ``target_point``, mas só para alvos que podem receber dano agora.

    Retorna ``None`` quando o inimigo está morto ou invulnerável, excluindo-o
    da seleção de alvo.
    """
    if not is_targetable(enemy):
        return None
    return target_point(enemy)


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
