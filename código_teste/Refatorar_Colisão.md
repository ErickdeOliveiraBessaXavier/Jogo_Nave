# Plano de Refatoração — Sistema de Colisões

## Objetivo
Remover todos os `isinstance` do `collisions.py` movendo a lógica de reação para cada entidade.

---

## Fase 1 — Criar a fundação

### `src/systems/hit_result.py` (arquivo novo)

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class HitResult:
    killed: bool = False
    points: int = 0
    explosion_size: int = 20
    explosion_type: Any = None        # ExplosionType | None
    sound: str = "explosion_alien"    # método do sound_manager sem o prefixo "play_"
    fragments: list = field(default_factory=list)
```

### `src/systems/collision_behaviors.py` (arquivo novo)

```python
from typing import Protocol, runtime_checkable
from .hit_result import HitResult

@runtime_checkable
class Damageable(Protocol):
    dead: bool
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult: ...

@runtime_checkable
class AreaDamageable(Protocol):
    dead: bool
    def on_area_hit(self, source_x: float, source_y: float, radius: float) -> HitResult: ...
```

---

## Fase 2 — Migrar as entidades

Adicione `on_hit` em cada entidade seguindo os exemplos abaixo.
Mantenha o código antigo funcionando — a migração é incremental.

---

### Padrão simples (entidade morre no hit)

Usado por: `Alien`, `EyeEnemy`, `StoneSentry`

```python
# alien.py
from ..systems.hit_result import HitResult

class Alien:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.dead = True
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=40,
            explosion_type=ExplosionType.ALIEN,
            sound="explosion_alien",
        )
```

---

### Padrão com HP próprio (entidade aguenta múltiplos hits)

Usado por: `ElementalRobot`, `Boulder`, `StoneSentry`, `MountainStalagmite`, `SerpentBlock`

```python
# stone_sentry.py
from ..systems.hit_result import HitResult

class StoneSentry:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(1)
        if self.dead:
            return HitResult(killed=True, points=self.get_points_value(), explosion_size=45)
        return HitResult(killed=False, explosion_size=10, sound="boss_damage")
```

```python
# elemental_robot.py — FSM com flag just_died
from ..systems.hit_result import HitResult

class ElementalRobot:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(1)
        if self.fsm_state == "DYING" and self.just_died:
            self.just_died = False
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=55,
                explosion_type=self.get_explosion_type(),
            )
        return HitResult(killed=False, explosion_size=10, sound="boss_damage")
```

---

### Padrão imune (não recebe dano)

Usado por: `SquareMinionBoss`, `RockShard`, `OrbitalRock`, `EntryDebris`

```python
# square_minion_boss.py
from ..systems.hit_result import HitResult

class SquareMinionBoss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        # Imune — só feedback visual
        return HitResult(killed=False, points=0, explosion_size=20, sound="boss_damage")
```

```python
# rock_shard.py / orbital_rock.py / entry_debris.py
from ..systems.hit_result import HitResult

class RockShard:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        return HitResult(killed=False, points=0, explosion_size=0, sound="")
```

---

### Padrão com fragmentos

Usado por: `Meteor`

```python
# meteor.py
from ..systems.hit_result import HitResult

class Meteor:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.dead = True
        fragments = self.spawn_fragments(is_side_scroll=self._is_side_scroll)
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=max(12, int(self.w // 2)),
            sound="explosion_asteroid",
            fragments=fragments,  # EntityManager vai fazer enemies.append em cada um
        )
```

> **Atenção:** `spawn_fragments` hoje recebe `meteor_factory` como argumento
> (para usar o pool). Mova essa responsabilidade para o `EntityManager`:
> após receber os fragments no `HitResult`, registre-os via `entity_manager.register_fragment(f)`.

---

### Padrão com dano parcial

Usado por: `RockGlider`

```python
# rock_glider.py
from ..systems.hit_result import HitResult

class RockGlider:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        pts, part_destroyed, _fully, part_center, part_name = \
            self.take_part_damage(hit_x, hit_y, amount=1)

        if not part_destroyed:
            return HitResult(killed=False, explosion_size=10, sound="boss_damage")

        sound = "explosion_asteroid" if part_name == "rock" else "explosion_alien"
        size = 35 if part_name == "rock" else 25
        return HitResult(killed=part_destroyed, points=pts, explosion_size=size, sound=sound)
```

---

### Padrão de mina (explode por conta própria)

Usado por: `ExplosiveMine`

```python
# explosive_mine.py
from ..systems.hit_result import HitResult

class ExplosiveMine:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        # Não morre no hit — controla a própria morte via is_exploding
        return HitResult(killed=False, points=0, explosion_size=0, sound="")
```

---

### Bosses

Cada boss implementa `on_hit` com sua lógica de morte específica.
O padrão é idêntico ao HP próprio, só muda o que acontece ao morrer.

```python
# boss.py (e spike_boss.py, slime_boss.py — mesma estrutura)
from ..systems.hit_result import HitResult

class Boss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=config.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound="explosion_boss",
            )
        return HitResult(killed=False, explosion_size=15, sound="boss_damage")
```

`SlimeBoss` — morte especial via `entity_manager`:

```python
# slime_boss.py
class SlimeBoss:
    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        self.take_damage(damage)
        if self.dead and not self.death_sequence_started:
            self.death_sequence_started = True
            # Sinaliza para o EntityManager via flag — ele chama trigger_slime_boss_death
            return HitResult(killed=True, points=config.BOSS_DEFEAT_SCORE,
                             explosion_size=0, sound="")
        return HitResult(killed=False, explosion_size=15, sound="boss_damage")
```

---

## Fase 3 — Refatorar o sistema

### `collisions.py` — substituir `_destroy_enemy`

```python
def _destroy_enemy(
    self,
    enemy: "Damageable",
    damage: int,
    hit_x: float,
    hit_y: float,
    entity_manager: "EntityManager",
) -> HitResult:
    result = enemy.on_hit(damage, hit_x, hit_y)

    if result.explosion_size > 0:
        entity_manager.spawn_explosion(
            hit_x, hit_y, result.explosion_size, result.explosion_type
        )

    if result.sound:
        getattr(sound_manager, f"play_{result.sound}")()

    for fragment in result.fragments:
        entity_manager.enemies.append(fragment)

    return result
```

### `collisions.py` — exemplo de método público limpo

```python
def bullets_vs_enemies(self, bullets, enemies, entity_manager, floating_scores):
    score_gain = 0

    for bullet in bullets:
        candidates = entity_manager.enemy_spatial_grid.query_from_rect(bullet.rect)
        for enemy in candidates:
            if enemy.dead:
                continue
            if not bullet.rect.colliderect(enemy.rect):
                continue

            result = self._destroy_enemy(
                enemy, bullet.damage, bullet.x, bullet.y, entity_manager
            )
            score_gain += result.points

            if result.points > 0:
                floating_scores.append(FloatingScore(bullet.x, bullet.y, result.points))

            if not bullet.piercing:
                bullet.dead = True
                break

    return score_gain
```

### `entity_manager.py` — simplificar `cleanup`

Adicione `should_remove() -> bool` nas entidades que têm regras especiais de remoção
(ex: `SerpentBlock`, `MountainStalagmite`, `ExplosiveMine`).

```python
# serpent_block.py
def should_remove(self) -> bool:
    return False  # nunca remove sozinho — o boss controla

# explosive_mine.py
def should_remove(self) -> bool:
    return self.dead or self.is_off_screen()

# padrão para todas as outras entidades
def should_remove(self) -> bool:
    return self.dead
```

```python
# entity_manager.py — cleanup simplificado
self.enemies = [e for e in self.enemies if not e.should_remove()]
```

---

## Checklist de migração

```
[ ] hit_result.py criado
[ ] collision_behaviors.py criado

[ ] Meteor
[ ] Alien
[ ] EyeEnemy
[ ] ExplosiveMine
[ ] SquareMinionBoss
[ ] ElementalRobot
[ ] RockGlider
[ ] StoneSentry
[ ] MountainStalagmite
[ ] SerpentBlock
[ ] Boulder / RockShard / OrbitalRock / EntryDebris
[ ] Boss / SpikeBoss / SlimeBoss / GiantMeteorBoss / StoneGolemBoss / MountainSerpentBoss

[ ] _destroy_enemy refatorado no collisions.py
[ ] isinstance removidos dos métodos públicos
[ ] cleanup simplificado no entity_manager.py
```

---

## Regra de ouro

> Se você está escrevendo `isinstance(enemy, X)` dentro de `collisions.py`,
> esse código pertence ao `on_hit` de `X`.