# Guia: Criar Novo Inimigo

---

## 1. Arquivo da entidade (`game/entities/nome_inimigo.py`)

Interface mínima obrigatória:

```python
class MeuInimigo:
    dead: bool
    health: int
    active: bool

    @property
    def rect(self) -> pygame.Rect: ...

    def update(self, dt: float) -> list[Projectile]:  # retorna projéteis gerados
        ...

    def collision_circle(self) -> tuple[float, float, float]:  # cx, cy, radius
        ...

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> HitResult:
        ...

    def on_ship_contact(self, contact_x: float, contact_y: float) -> HitResult:
        ...

    def should_remove(self) -> bool:
        return self.dead
```

`HitResult` vem de `game/systems/hit_result.py`. Campos úteis:
```python
HitResult(
    killed=True/False,
    points=250,
    explosion_size=35,
    sound=hit_sounds.EXPLOSION_ALIEN,
)
```

> **Atalho — herdar `EnemyHitMixin`** (`game/entities/enemy_hit_mixin.py`).
> No caso comum, herde o mixin e ganhe `on_hit`, `collision_circle` e
> `on_ship_contact` de graça — só precisa implementar `take_damage`,
> `get_points_value` e a property `rect`. O `on_hit` padrão chama `take_damage`,
> detecta morte e devolve o `HitResult` com explosão/som. Exemplos: `StoneSentry`,
> `MountainMage`. Só sobrescreva `on_hit` para efeito especial (fragmentos, som
> custom). O dano é centralizado em `CollisionPhysics.apply_hit` — você nunca
> itera inimigo a inimigo nem toca em cada fonte de dano por alvo.

---

## 2. Registrar no Spawner (`game/systems/spawner.py`)

### 2a. Import no topo
```python
from ..entities.meu_inimigo import MeuInimigo
```

### 2b. Adicionar ao `_count_enemies_by_type`
```python
counts: dict[str, int] = {
    ...
    "meu_inimigo": 0,
}
# dentro do loop:
elif isinstance(enemy, MeuInimigo):
    counts["meu_inimigo"] += 1
```

### 2c. Definir cap (topo do arquivo)
```python
SPAWNER_CAP_MEU_INIMIGO: int = 2
```

### 2d. Adicionar ao `_is_hard_capped` e `_should_spawn_enemy`
```python
if enemy_type == MeuInimigo and counts["meu_inimigo"] >= SPAWNER_CAP_MEU_INIMIGO:
    return True  # (em _is_hard_capped)
    # return False  (em _should_spawn_enemy)
```

### 2e. Adicionar ao `_enemy_type_key`
```python
aliases = {
    ...
    "MeuInimigo": "meu_inimigo",
}
```

### 2f. Adicionar ao `_spawn_enemy_of_type`
```python
if enemy_type == MeuInimigo:
    return self._spawn_meu_inimigo(entity_manager)
```

### 2g. Implementar `_spawn_meu_inimigo`
```python
def _spawn_meu_inimigo(self, entity_manager: "EntityManager") -> bool:
    enemy = MeuInimigo(...)
    enemy.health = int(enemy.health * self.enemy_health_multiplier)
    entity_manager.enemies.append(enemy)
    return True
```

---

## 3. Registrar no sistema de progressão (pacote `game/core/levels/`)

> ⚠️ Após o split do item 4, `core/levels.py` virou o **pacote** `core/levels/`.
> Os símbolos abaixo se distribuem assim:
>
> | Símbolo | Módulo |
> |---|---|
> | `ENEMY_THEME_ALLOWLIST`, `DEFAULT_ENEMY_SPAWN_TIME`, `ENEMY_THEME_WEIGHT_PROFILES`, `ENEMY_STAGE_WEIGHT_PROFILES`, `THEME_FALLBACK_ENEMIES` | `pipeline.py` |
> | `ENEMY_PRESSURE_TIER_BY_KEY`, `ENEMY_PRESSURE_UNLOCK_START/WINDOW`, `DifficultyConfig.MIN_SPAWN_GAP_BY_TYPE`, `ProceduralLevelGenerator` | `procedural.py` |
> | `FIXED_LEVELS`, `LevelConfig` | `fixed_levels.py` |
>
> O contrato público continua reexportado em `core/levels/__init__.py`, então
> *callers* externos seguem com `from game.core.levels import X`. Mas para
> **editar** as tabelas você abre o módulo específico.

### 3a. Import (nos módulos `pipeline.py` e `procedural.py`)
```python
from ...entities.meu_inimigo import MeuInimigo   # três pontos: o pacote está um nível mais fundo
```

### 3b. `ENEMY_THEME_ALLOWLIST` — restringir ao(s) mundo(s) válidos
```python
MeuInimigo: {WorldTheme.MOUNTAINS},
```
Omitir a entrada = permitido em todos os mundos.

### 3c. `DEFAULT_ENEMY_SPAWN_TIME` — tempo base de fallback
```python
MeuInimigo: 20.0,
```

### 3d. `ENEMY_PRESSURE_TIER_BY_KEY` — tier de progressão
```python
"meu_inimigo": "strong",  # "volume" | "intermediate" | "strong"
```
| Tier | Curva (início→fim) | Uso típico |
|---|---|---|
| volume | 1.25 → 0.90 | inimigos de volume (meteoros, gliders) |
| intermediate | 0.55 → 1.15 | inimigos médios (aliens) |
| strong | 0.20 → 0.95 | inimigos especiais / mini-bosses |

### 3e. `ENEMY_PRESSURE_UNLOCK_START` e `ENEMY_PRESSURE_UNLOCK_WINDOW`
```python
# Quando no mundo o inimigo começa a aparecer (0.0 = início, 1.0 = fim)
"meu_inimigo": 0.45,   # UNLOCK_START

# Janela de ramp-up: quanto tempo leva para atingir presença plena
"meu_inimigo": 0.30,   # UNLOCK_WINDOW
```

### 3f. `ENEMY_THEME_WEIGHT_PROFILES` — multiplicadores por perfil de tuning
```python
"conservative": { WorldTheme.MOUNTAINS: { MeuInimigo: 1.10 } },
"moderate":      { WorldTheme.MOUNTAINS: { MeuInimigo: 1.25 } },
"aggressive":    { WorldTheme.MOUNTAINS: { MeuInimigo: 1.40 } },
```

### 3g. `ENEMY_STAGE_WEIGHT_PROFILES` — ajuste por estágio dentro do mundo
```python
"moderate": { WorldTheme.MOUNTAINS: {
    "early": { MeuInimigo: 0.85 },
    "mid":   { MeuInimigo: 1.05 },
    "late":  { MeuInimigo: 1.20 },
}}
```

### 3h. `THEME_FALLBACK_ENEMIES` — lista de fallback
```python
WorldTheme.MOUNTAINS: [RockGlider, MountainMage, StoneSentry, ElementalRobot, MeuInimigo],
```

### 3i. `MIN_SPAWN_GAP_BY_TYPE` (em `DifficultyConfig`, `procedural.py`) — gap mínimo entre spawns
```python
"meu_inimigo": 15.0,  # segundos
```
Para inimigos especiais (ElementalRobot, StoneSentry, MountainMage, MountainPropeller),
o gap é automaticamente `max(gap_definido, spawn_time_calculado)` — adicione o seu tipo
ao bloco `if enemy_type in (ElementalRobot, StoneSentry, MountainMage, MountainPropeller, MeuInimigo)`
em `_get_min_spawn_gap`. Esse método vive em **`game/systems/spawner.py`** (não em `levels/`);
ele lê `DifficultyConfig.MIN_SPAWN_GAP_BY_TYPE`.

---

## 4. Inserir no gerador procedural (`game/core/levels/procedural.py`)

Em `ProceduralLevelGenerator`, dentro do método de configuração do tema alvo —
ex.: `_configure_mountains_spawn` para MOUNTAINS (já é chamado por `generate_config`
só quando o tema casa, então o `if world.theme == ...` é implícito; basta o gate de
`stage_progress`). `_get_progressive_enemy_weight` é função **module-level** (sem `self.`):

```python
# dentro de _configure_mountains_spawn(self, enemy_spawn_config, stage_progress, difficulty, spawn_multiplier)
if stage_progress >= 0.43:
    weight = _get_progressive_enemy_weight("meu_inimigo", 1.0, stage_progress)
    spawn_time = (BASE_TIME / difficulty / spawn_multiplier) * (2.0 / weight)
    enemy_spawn_config[MeuInimigo] = self._clamp_spawn_time(spawn_time)
```

Para um tema sem método dedicado, adicione o gate no corpo de `generate_config`
guardado por `if world.theme == WorldTheme.X` (o `world` vem de
`get_world_for_level(level_number)` — é assim que `generate_config` despacha para
`_configure_mountains_spawn`).

`BASE_TIME` é o spawn_time em segundos quando `weight == 2.0` (ponto neutro).
Regra de ouro para escolher `BASE_TIME`:

| Tipo | BASE_TIME sugerido |
|---|---|
| Inimigo de volume | 0.8 – 2.0 |
| Inimigo médio | 3.0 – 8.0 |
| Inimigo especial | 10.0 – 18.0 |
| Mini-boss | 15.0 – 25.0 |

O threshold (`stage_progress >= X`) deve ser ligeiramente abaixo do `UNLOCK_START`
para que o ramp-up suave da `gate_mult` (que começa em 0.15) tenha espaço.

---

## 5. Adicionar ao config manual de nível (opcional)

Em `FIXED_LEVELS` dentro de `core/levels/fixed_levels.py`, se quiser que o inimigo
apareça em uma fase fixa independente do procedural:

```python
3: LevelConfig(
    level_number=3,
    enemy_spawn_config={
        RockGlider: 0.7,
        MeuInimigo: 12.0,  # spawn_time em segundos
    },
    ...
)
```

O valor é o **intervalo em segundos** no modo legado e o **inverso do peso**
(`1/spawn_time`) no modo ponderado.

---

## 6. Checklist final

- [ ] Entidade implementa a interface mínima (`rect`, `on_hit`, `on_ship_contact`, `should_remove`)
- [ ] Import no `spawner.py` e nos módulos de `core/levels/` (`pipeline.py`/`procedural.py`, **três pontos**: `from ...entities...`)
- [ ] Cap definido e aplicado em `_is_hard_capped` + `_should_spawn_enemy`
- [ ] Alias em `_enemy_type_key`
- [ ] Rota em `_spawn_enemy_of_type`
- [ ] `ENEMY_THEME_ALLOWLIST` (se mundo específico)
- [ ] `DEFAULT_ENEMY_SPAWN_TIME`
- [ ] `ENEMY_PRESSURE_TIER_BY_KEY` + `UNLOCK_START` + `UNLOCK_WINDOW`
- [ ] `ENEMY_THEME_WEIGHT_PROFILES` (conservative/moderate/aggressive)
- [ ] `ENEMY_STAGE_WEIGHT_PROFILES` (early/mid/late)
- [ ] `MIN_SPAWN_GAP_BY_TYPE`
- [ ] Bloco no gerador procedural com `_get_progressive_enemy_weight`
- [ ] `_get_min_spawn_gap`: adicionar ao `if enemy_type in (...)` se gap = spawn_time

---

## Armadilhas conhecidas

**Spawn imediato no início da fase**
`last_spawn_clock_by_type` usa `-9999.0` como sentinel para tipos nunca spawnados,
fazendo `_can_spawn_now` retornar `True` imediatamente. **Isso está corrigido** —
`_reset_spawn_pipeline` inicializa o dict com `0.0` para todos os tipos do nível.
Não introduza novos sentinels negativos nesse dict.

**MountainPropeller tem spawner duplo**
Spawna tanto pelo pipeline ponderado quanto por `_update_propeller_spawner` (timer 14s).
Se criar inimigo com spawner dedicado separado, garanta que o cap impeça duplicação.

**`_update_mine_spawner` usa `1/60` fixo como dt**
Bug conhecido. Não copiar esse padrão — passar `dt` real.
