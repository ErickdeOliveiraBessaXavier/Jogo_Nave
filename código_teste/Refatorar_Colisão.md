# Plano de Refatoração — Sistema de Colisões

## Diagnóstico

`game/systems/collisions.py` cresceu para ~2085 linhas com 30+ imports de
entidades concretas. Os sintomas são clássicos de god file:

- `_destroy_enemy` (~145 linhas) — cascata de `isinstance` para definir HP,
  som, tamanho de explosão, fragmentos.
- `ship_vs_enemies` — cascata paralela e diferente do `_destroy_enemy`
  (semântica de "morte por contato instantâneo").
- `get_collision_info` — cascata só para extrair `(cx, cy, radius)`.
- `_calculate_default_explosion_size` — cascata só para tamanho visual.
- 4 métodos `*_vs_boss` duplicam a lógica de morte do boss
  (`_apply_boss_damage`, `explosive_effects_vs_boss`,
  `air_strike_bombs_vs_boss`, `cannon_mines_vs_boss`).
- `bullets_vs_giant_meteor_boss` é totalmente bespoke (fragmentos por hit).

Toda nova entidade exige edição de `collisions.py` em múltiplos pontos —
violação direta de OCP. A causa-raiz é que **a lógica de reação ao dano
pertence à entidade, não ao sistema de colisão**.

## Objetivo

Eliminar `isinstance` de `collisions.py` movendo a reação ao dano para cada
entidade via Protocols. O sistema de colisão volta a fazer apenas
**detecção** e **roteamento**; entidades respondem a eventos.

## Princípios

- Tell-Don't-Ask: o sistema **avisa** a entidade que foi atingida, não
  pergunta o tipo dela.
- Value objects imutáveis (`frozen=True`) para os resultados — evita
  mutação acidental e permite reuso em testes.
- Protocols estruturais (`runtime_checkable=False` por padrão — tipagem
  estática, zero overhead em runtime).
- Sem dispatch por string (`getattr(sound_manager, f"play_{...}")`). Som é
  representado por enum ou `Callable[[], None]`.
- `dt` continua passando explícito; nada nesta refatoração toca o loop.
- Sem regressão de performance: nenhuma alocação extra no hot path
  (`HitResult` é dataclass com `slots=True`).

---

## Fase 1 — Fundação

### `game/systems/hit_result.py` (novo)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..entities.explosion import ExplosionType


@dataclass(frozen=True, slots=True)
class HitResult:
    """Resposta imutável de uma entidade a um evento de dano.

    Campos:
        killed: True se a entidade morreu neste hit (afeta score/cleanup).
        points: pontos a conceder ao jogador (>0 implica FloatingScore).
        explosion_size: raio em pixels da explosão visual (0 = nenhuma).
        explosion_type: variante visual (ALIEN, SLIME, etc.) ou None.
        sound: callable a tocar (ou None). Use HitSounds para padrões.
        fragments: spawns derivados (ex.: meteoros menores). Cada item
            deve ser uma entidade pronta para append em entity_manager.enemies.
        triggers_special_death: a entidade quer um death-sequence custom
            controlado pelo entity_manager (ex.: SlimeBoss).
    """

    killed: bool = False
    points: int = 0
    explosion_size: int = 0
    explosion_type: "ExplosionType | None" = None
    sound: Callable[[], None] | None = None
    fragments: tuple[object, ...] = ()
    triggers_special_death: bool = False


# Resultado neutro reusado quando não há reação (alocação zero no hot path).
NO_HIT = HitResult()
```

### `game/systems/hit_sounds.py` (novo)

Encapsula o dispatch de som — evita stringly-typed code e dá completion no
IDE. Cada constante é o método já bound do singleton `sound_manager`.

```python
from __future__ import annotations

from ..core.sound import sound_manager

# Bound methods — chamadas com custo idêntico a sound_manager.play_X().
EXPLOSION_ALIEN = sound_manager.play_explosion_alien
EXPLOSION_ASTEROID = sound_manager.play_explosion_asteroid
EXPLOSION_BOSS = sound_manager.play_explosion_boss
BOSS_DAMAGE = sound_manager.play_boss_damage
```

### `game/systems/collision_protocols.py` (novo)

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pygame

if TYPE_CHECKING:
    from .hit_result import HitResult


class CollisionGeometry(Protocol):
    """Contrato para extrair geometria de colisão circular.

    Substitui o cascade `get_collision_info` em collisions.py.
    """

    @property
    def rect(self) -> pygame.Rect: ...

    def collision_circle(self) -> tuple[float, float, float]:
        """Retorna (center_x, center_y, radius) para checks de área."""
        ...


class Damageable(CollisionGeometry, Protocol):
    """Contrato para entidades que recebem dano de projéteis/áreas.

    `on_hit` decide o que acontece: morre? perde HP? explode em fragmentos?
    O sistema apenas executa o HitResult retornado.
    """

    dead: bool

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult": ...


class ShipDamageable(CollisionGeometry, Protocol):
    """Contrato para o caminho 'morte por contato com a nave'.

    Semântica diferente de `on_hit`: dano máximo, sem score, som específico
    de impacto. RockGlider continua usando dano por partes; minas explodem
    imediatamente; etc. Cada entidade decide.
    """

    dead: bool

    def on_ship_contact(self) -> "HitResult": ...


class Removable(Protocol):
    """Substitui filtros `isinstance` no cleanup do EntityManager."""

    def should_remove(self) -> bool: ...
```

### Por que dois métodos (`on_hit` vs `on_ship_contact`)?

A semântica de morte é diferente:

| Evento | Score | Dano | Som padrão |
|---|---|---|---|
| Tiro / área | Sim | `bullet.damage` | `EXPLOSION_ALIEN` |
| Contato com nave | Não (jogador morreu) | Letal | varia (asteroid/alien) |

Tentar unificar via `on_hit(damage=999)` mistura semânticas: o player morre
mas o jogador "ganharia pontos" pelo que matou. Manter separado é mais
limpo e cada entidade descreve sua própria reação a cada caso.

---

## Fase 2 — Migração das entidades

Migração incremental: o caminho antigo continua funcionando até o
`_destroy_enemy` ser substituído. Cada entidade migrada não precisa esperar
pelas outras.

### Helper geométrico padrão

A maioria das entidades usa `rect` retangular. Adicione na base / mixin:

```python
def collision_circle(self) -> tuple[float, float, float]:
    r = self.rect
    return r.centerx, r.centery, max(r.width, r.height) / 2
```

Override apenas quando o `rect` mente sobre o tamanho real
(ex.: `ExplosiveMine.radius`, `Boulder.RADIUS`, `RockShard.size`,
`EntryDebris.S * rock_size`).

### Padrão A — morre em um hit

`Alien`, `EyeEnemy`, `Meteor` (sem fragmentos), `MountainPropeller` simples.

```python
# alien.py
from ..systems.hit_result import HitResult
from ..systems import hit_sounds
from .explosion import ExplosionType


class Alien:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.dead = True
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=40,
            explosion_type=ExplosionType.ALIEN,
            sound=hit_sounds.EXPLOSION_ALIEN,
        )

    def on_ship_contact(self) -> HitResult:
        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)
```

### Padrão B — HP múltiplo

`Boss`, `SpikeBoss`, `StoneSentry`, `MountainStalagmite`, `SerpentBlock`,
`Boulder`, `MountainPropeller`, `ElementalRobot`.

```python
# stone_sentry.py
class StoneSentry:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=45,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)
```

### Padrão C — FSM com flag de morte

`ElementalRobot` precisa consumir `just_died` (a morte só é fatal num
frame específico do estado DYING).

```python
# bot_elemental.py
class ElementalRobot:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        if self.fsm_state == "DYING" and self.just_died:
            self.just_died = False  # consumir
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=55,
                explosion_type=self.get_explosion_type(),
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)
```

### Padrão D — dano por partes

`RockGlider`.

```python
# rock_glider.py
class RockGlider:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        pts, part_destroyed, _full, part_center, part_name = (
            self.take_part_damage(hit_x, hit_y, amount=damage)
        )

        if not part_destroyed:
            return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

        is_rock = part_name == "rock"
        return HitResult(
            killed=part_destroyed,
            points=pts,
            explosion_size=35 if is_rock else 25,
            sound=hit_sounds.EXPLOSION_ASTEROID if is_rock else hit_sounds.EXPLOSION_ALIEN,
        )

    def on_ship_contact(self) -> HitResult:
        ship_cx, ship_cy = self.rect.centerx, self.rect.centery  # aproximação
        _pts, part_destroyed, _full, _center, part_name = self.take_part_damage(
            ship_cx, ship_cy, amount=max(self.ROCK_MAX_HP, self.BOT_MAX_HP)
        )
        sound = (
            hit_sounds.EXPLOSION_ASTEROID if part_name == "rock"
            else hit_sounds.EXPLOSION_ALIEN if part_destroyed
            else hit_sounds.BOSS_DAMAGE
        )
        return HitResult(killed=False, sound=sound)
```

> Observação: `on_ship_contact` aqui não tem acesso direto à posição da
> nave. Solução: passar o ponto de contato como parâmetro opcional ou
> calcular via `self.rect`. Prefira o parâmetro — mantém entidades sem
> dependência da nave.

Atualize a assinatura do protocol:

```python
def on_ship_contact(self, contact_x: float, contact_y: float) -> "HitResult": ...
```

### Padrão E — Meteor (fragmentos na morte)

```python
# meteor.py
class Meteor:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.dead = True
        fragments = tuple(self._build_fragment_specs())  # ver nota abaixo
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=max(12, int(self.w // 2)),
            sound=hit_sounds.EXPLOSION_ASTEROID,
            fragments=fragments,
        )
```

> **Atenção ao pool.** Hoje `spawn_fragments` recebe `meteor_factory=
> entity_manager.meteor_pool.get` para reutilizar instâncias. O `HitResult`
> não pode carregar a referência ao pool. Duas opções:
>
> 1. **`fragments` carrega specs**, não entidades. `Meteor._build_fragment_specs`
>    retorna tuplas `(size, x, y, vx, vy)`. O `EntityManager.absorve_hit_result`
>    chama `meteor_pool.get(...)` para cada spec. **Preferida** — mantém
>    o pool isolado do hit_result.
> 2. `fragments` carrega entidades já alocadas. `Meteor` recebe o pool no
>    `__init__` (DI). Pior — acopla Meteor ao pool.

### Padrão F — imune a dano comum

`SquareMinionBoss`, `RockShard`, `OrbitalRock`, `EntryDebris`.

```python
# square_minion_boss.py
class SquareMinionBoss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        return HitResult(explosion_size=20, sound=hit_sounds.BOSS_DAMAGE)
```

```python
# rock_shard.py
class RockShard:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        return NO_HIT  # absorve sem feedback

    def on_ship_contact(self, cx: float, cy: float) -> HitResult:
        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)
```

### Padrão G — explode por conta própria

`ExplosiveMine`. A morte é controlada pelo timer interno, não pelo hit.

```python
# explosive_mine.py
class ExplosiveMine:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        return NO_HIT  # quem mata é o timer, não o tiro

    def on_ship_contact(self, cx: float, cy: float) -> HitResult:
        self.dead = True  # explode imediatamente
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)
```

### Padrão H — bosses (unifica 4 métodos do Collisions)

```python
# boss.py
class Boss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=config.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)
```

`SlimeBoss` precisa de death-sequence (limpa drips, anima, etc.):

```python
class SlimeBoss(Boss):
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        if self.dead and not self.death_sequence_started:
            self.death_sequence_started = True
            return HitResult(
                killed=True,
                points=config.BOSS_DEFEAT_SCORE,
                triggers_special_death=True,  # EntityManager dispara animação
                sound=hit_sounds.BOSS_DAMAGE,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)
```

`GiantMeteorBoss` solta fragmentos **a cada hit** (não só na morte):

```python
class GiantMeteorBoss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)

        fragments: tuple = ()
        if random.random() < Config.GIANT_METEOR_HIT_FRAGMENT_CHANCE:
            fragments = tuple(self._build_fragment_specs(
                count_range=Config.GIANT_METEOR_HIT_FRAGMENT_COUNT,
                speed_range=(90.0, 180.0),
            ))

        if self.dead:
            fragments += tuple(self._build_fragment_specs(
                count_range=Config.GIANT_METEOR_DEATH_FRAGMENT_COUNT,
                speed_range=(120.0, 240.0),
            ))
            return HitResult(
                killed=True,
                points=config.BOSS_DEFEAT_SCORE,
                explosion_size=120,
                sound=hit_sounds.EXPLOSION_BOSS,
                fragments=fragments,
            )

        return HitResult(
            explosion_size=18,
            sound=hit_sounds.BOSS_DAMAGE,
            fragments=fragments,
        )
```

`MountainSerpentBoss` (cabeça invulnerável quando há blocos):

```python
class MountainSerpentBoss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        if not self.is_vulnerable:
            return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)
        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=config.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)
```

---

## Fase 3 — Refatoração de `collisions.py`

### `Collisions._apply_hit` (substitui `_destroy_enemy`)

```python
def _apply_hit(
    self,
    target: "Damageable",
    damage: int,
    hit_x: float,
    hit_y: float,
    entity_manager: "EntityManager",
    floating_scores: list[FloatingScore] | None = None,
) -> HitResult:
    """Roteador único: chama on_hit e materializa os efeitos."""
    result = target.on_hit(damage, hit_x, hit_y)

    if result.explosion_size > 0:
        entity_manager.spawn_explosion(
            hit_x, hit_y, size=result.explosion_size,
            explosion_type=result.explosion_type,
        )

    if result.sound is not None:
        result.sound()

    if result.fragments:
        entity_manager.absorb_fragments(result.fragments)

    if result.killed and result.points > 0 and floating_scores is not None:
        floating_scores.append(FloatingScore(hit_x, hit_y, result.points))

    if result.triggers_special_death:
        entity_manager.trigger_death_sequence(target)

    return result
```

### `Collisions._apply_ship_contact`

```python
def _apply_ship_contact(
    self,
    target: "ShipDamageable",
    contact_x: float,
    contact_y: float,
    entity_manager: "EntityManager",
) -> HitResult:
    result = target.on_ship_contact(contact_x, contact_y)

    if result.explosion_size > 0:
        entity_manager.spawn_explosion(contact_x, contact_y, size=result.explosion_size)
    if result.sound is not None:
        result.sound()
    return result
```

### `bullets_vs_enemies` simplificado

```python
def bullets_vs_enemies(
    self,
    bullets: list[Bullet],
    enemy_grid: SpatialGrid[Damageable],
    floating_scores: list[FloatingScore],
    entity_manager: "EntityManager",
) -> tuple[int, int, list[tuple[float, float, int]]]:
    if not bullets:
        return 0, 0, []

    score_gain = 0
    destroyed_count = 0
    score_events: list[tuple[float, float, int]] = []

    targets = self._batch_query_for_projectiles(bullets, enemy_grid)

    for bullet in bullets:
        if bullet.dead:
            continue
        for enemy in targets.get(id(bullet), ()):
            if enemy.dead or not self._projectile_collides_with_enemy(bullet.rect, enemy):
                continue

            result = self._apply_hit(
                enemy, bullet.damage, bullet.x, bullet.y,
                entity_manager, floating_scores,
            )
            score_gain += result.points
            if result.killed:
                destroyed_count += 1
                score_events.append((bullet.x, bullet.y, result.points))

            if bullet.explosive and not bullet.dead:
                self._apply_explosive_bullet_aoe(
                    bullet, enemy_grid, floating_scores, entity_manager,
                )

            if not bullet.piercing:
                bullet.dead = True
                break

    return score_gain, destroyed_count, score_events
```

### Bosses — métodos `*_vs_boss` colapsam em um helper

```python
def _project_into_boss(
    self,
    projectiles: Sequence[Projectile],
    boss: "Damageable",
    entity_manager: "EntityManager",
    floating_scores: list[FloatingScore],
    is_piercing_allowed: bool = False,
) -> int:
    score_gain = 0
    if not projectiles or boss.dead:
        return 0

    for proj in projectiles:
        if proj.dead or not self._check_mask_collision(proj.rect, None, boss, proj.x, proj.y):
            continue

        if not (is_piercing_allowed and getattr(proj, "piercing", False)):
            proj.dead = True

        damage = int(proj.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
        result = self._apply_hit(boss, damage, proj.x, proj.y, entity_manager, floating_scores)
        score_gain += result.points

    return score_gain
```

`bullets_vs_boss`, `mini_ship_bullets_vs_boss`, `*_vs_spike_boss`,
`*_vs_slime_boss`, `bullets_vs_giant_meteor_boss` e
`bullets_vs_mountain_serpent_boss` viram **wrappers de uma linha** apontando
para `_project_into_boss`.

`explosive_effects_vs_boss`, `air_strike_bombs_vs_boss` e
`cannon_mines_vs_boss` viram um helper único `_aoe_into_boss` que aplica
`_apply_hit(boss, damage, source_x, source_y, ...)`.

### `ship_vs_enemies` simplificado

```python
def ship_vs_enemies(
    self,
    ship: Ship,
    enemy_grid: SpatialGrid["ShipDamageable"],
    entity_manager: "EntityManager",
) -> bool:
    if ship.invuln > 0:
        return False

    ship_rect = ship.rect
    candidates = enemy_grid.query(
        ship_rect.x - 10, ship_rect.y - 10,
        ship_rect.width + 20, ship_rect.height + 20,
    )
    cx, cy = ship_rect.centerx, ship_rect.centery

    for enemy in candidates:
        if enemy.dead or not getattr(enemy, "causes_damage", True):
            continue
        if not self._ship_collides_with_enemy(ship_rect, enemy):
            continue

        self._apply_ship_contact(enemy, cx, cy, entity_manager)
        entity_manager.spawn_explosion(cx, cy, size=30)
        return True

    return False
```

### `get_collision_info` desaparece

Substituído por `enemy.collision_circle()` chamado diretamente.

### `_calculate_default_explosion_size` desaparece

Cada `on_hit` decide seu próprio `explosion_size` no `HitResult`.

---

## Fase 4 — Cleanup e remoção

### `should_remove()` em entidades com lógica especial

```python
# serpent_block.py
def should_remove(self) -> bool:
    return False  # boss controla — nunca remove via cleanup genérico

# explosive_mine.py
def should_remove(self) -> bool:
    return self.dead and not self.is_exploding  # respeita timer

# default (mixin ou base)
def should_remove(self) -> bool:
    return self.dead
```

### `EntityManager` — cleanup unificado

```python
# entity_manager.py
def cleanup(self) -> None:
    self.enemies = [e for e in self.enemies if not e.should_remove()]
    self.bullets = [b for b in self.bullets if not b.should_remove()]
    # ...

def absorb_fragments(self, fragments: tuple[object, ...]) -> None:
    """Materializa fragments do HitResult (specs ou entidades prontas)."""
    for spec in fragments:
        if isinstance(spec, MeteorSpec):
            self.spawn_meteor(**spec._asdict())
        else:
            self.enemies.append(spec)

def trigger_death_sequence(self, target: object) -> None:
    if isinstance(target, SlimeBoss):
        self.trigger_slime_boss_death(target)
    # outros bosses com cinemática especial entram aqui
```

> Aqui sobra **um** `isinstance` (em `trigger_death_sequence`). É aceitável:
> esses casos são genuinamente "comportamentos especiais que afetam o
> mundo inteiro", não pertencem ao escopo da entidade. Limite: máximo 3-4
> bosses ao longo da vida do jogo.

---

## Fase 5 — Limpeza final

- Remover de `collisions.py` os imports concretos das entidades —
  só sobram os necessários para type hints (`TYPE_CHECKING`) e os
  poucos onde a colisão tem geometria especial não-circular
  (lasers, ondas).
- Remover `Collisions._is_invulnerable_to_damage` e
  `_handle_invulnerable_hit` — `SquareMinionBoss.on_hit` resolve.
- Adicionar `__slots__` nas entidades migradas que ainda não têm —
  `HitResult` com `slots=True` só ajuda se as entidades também forem
  slot-friendly no hot path.

---

## Ordem de execução recomendada

A ordem importa: violar produz quebra silenciosa.

1. **Infra (dia 1)**: `hit_result.py`, `hit_sounds.py`, `collision_protocols.py`.
   Build verde sem mudar nada além de imports.
2. **Coexistência (dia 1)**: adicionar `_apply_hit` ao lado de
   `_destroy_enemy`. Nenhum caller usa ainda.
3. **Migração entidade-por-entidade (dias 2-4)**: para cada entidade,
   adicionar `on_hit`, `on_ship_contact`, `collision_circle`,
   `should_remove`. Rodar o jogo e validar visualmente.
4. **Switch dos métodos públicos (dia 4)**:
   `bullets_vs_enemies` → `_apply_hit`,
   `_apply_area_damage` → `_apply_hit`,
   `player_lasers_vs_enemies` → `_apply_hit`,
   `mini_ship_bullets_vs_enemies` → `_apply_hit`.
5. **Bosses (dia 5)**: colapsar os 4 métodos `*_vs_boss` em
   `_project_into_boss` + `_aoe_into_boss`.
6. **Ship contact (dia 5)**: `ship_vs_enemies` → `_apply_ship_contact`.
7. **Remoção (dia 6)**: deletar `_destroy_enemy`, `get_collision_info`,
   `_calculate_default_explosion_size`, `_is_invulnerable_to_damage`.

---

## Validação

A cada entidade migrada, jogar a fase onde ela aparece e validar:

- [ ] Pontuação correta (FloatingScore aparece no lugar certo)
- [ ] Som correto (asteroid vs alien vs boss_damage)
- [ ] Tamanho de explosão idêntico ao anterior (lado a lado se preciso)
- [ ] Fragmentos spawnam (Meteor, GiantMeteorBoss)
- [ ] Death-sequence dispara (SlimeBoss)
- [ ] Imunidade preserva (SquareMinionBoss vs laser, SerpentBoss head)
- [ ] Multi-hit preserva HP (Boss, StoneSentry, Boulder)
- [ ] FSM consome flag (ElementalRobot.just_died)
- [ ] Dano por partes (RockGlider rock vs bot)
- [ ] Cleanup não remove SerpentBlock prematuramente

---

## Métricas de sucesso

| Antes | Alvo |
|---|---|
| `collisions.py` ~2085 linhas | < 1000 linhas |
| 30+ imports de entidades | < 10 (só geometrias especiais) |
| 25+ chamadas `isinstance` | 0 em métodos de hit, ≤ 3 em outros |
| 4 métodos `*_vs_boss` duplicados | 1 helper genérico |
| `_destroy_enemy` 145 linhas | `_apply_hit` ~25 linhas |

---

## Checklist de migração

```
Infra
[ ] hit_result.py + NO_HIT singleton
[ ] hit_sounds.py
[ ] collision_protocols.py (Damageable, ShipDamageable, CollisionGeometry, Removable)

Entidades — colocar on_hit + on_ship_contact + collision_circle + should_remove
[ ] Alien
[ ] EyeEnemy
[ ] Meteor (specs de fragmentos)
[ ] ExplosiveMine
[ ] SquareMinionBoss
[ ] ElementalRobot (consome just_died)
[ ] RockGlider (dano por partes)
[ ] StoneSentry
[ ] MountainStalagmite
[ ] MountainPropeller
[ ] SerpentBlock (should_remove=False)
[ ] Boulder
[ ] RockShard
[ ] OrbitalRock
[ ] EntryDebris

Bosses
[ ] Boss
[ ] SpikeBoss
[ ] SlimeBoss (triggers_special_death)
[ ] GiantMeteorBoss (fragments por hit + morte)
[ ] StoneGolemBoss
[ ] MountainSerpentBoss (gating por is_vulnerable)

Sistema
[ ] Collisions._apply_hit
[ ] Collisions._apply_ship_contact
[ ] Collisions._project_into_boss (unifica 4 *_vs_boss)
[ ] Collisions._aoe_into_boss (unifica 3 area-vs-boss)
[ ] bullets_vs_enemies usa _apply_hit
[ ] player_lasers_vs_enemies usa _apply_hit
[ ] mini_ship_bullets_vs_enemies usa _apply_hit
[ ] _apply_area_damage usa _apply_hit
[ ] ship_vs_enemies usa _apply_ship_contact

Cleanup
[ ] EntityManager.absorb_fragments
[ ] EntityManager.trigger_death_sequence
[ ] EntityManager.cleanup usa should_remove
[ ] DELETE _destroy_enemy
[ ] DELETE get_collision_info
[ ] DELETE _calculate_default_explosion_size
[ ] DELETE _is_invulnerable_to_damage / _handle_invulnerable_hit
[ ] Remover imports de entidades concretas em collisions.py
```

---

## Regra de ouro

> Se você está escrevendo `isinstance(enemy, X)` dentro de `collisions.py`,
> esse comportamento pertence a um método de `X`. Sem exceção no hot path
> de hit/contact. As únicas exceções aceitáveis são em
> `EntityManager.trigger_death_sequence` (cinemática global) e em
> geometrias verdadeiramente atípicas (lasers, ondas radiais), e mesmo
> essas devem caber em ≤ 3 ramos.
