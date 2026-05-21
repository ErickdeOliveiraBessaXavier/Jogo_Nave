## Plano de Refatoração — Problemas Pylint (9.60/10)

### Prioridade 1 — Importações Cíclicas (R0401)

**Causa raiz:** imports diretos entre módulos de cenas, systems e render no nível do módulo, criando grafos circulares.

**Solução:**

- Mover todos os imports problemáticos para dentro de funções/métodos onde já são usados (padrão `TYPE_CHECKING` + import local)
- `game.render.game_renderer` não deve importar de `game.scenes.playing` diretamente — usar `TYPE_CHECKING` ou extrair o `RenderFrame` como contrato independente (já existe `render_frame.py`, verificar se ainda há import direto da cena)
- `game.core.upgrades → game.core.upgrades_config`: mover as constantes que `upgrades.py` precisa para `upgrades_config.py` ou criar um terceiro módulo `upgrades_types.py` com apenas enums/constantes

**Arquivos afetados:** `game/render/game_renderer.py`, `game/scenes/*.py`, `game/core/upgrades.py`

---

### Prioridade 2 — Duplicação Estrutural Grave (R0801)

Agrupar pelos tipos de duplicação:

#### 2a. TypedDicts duplicados
`DeathParticle`, `ChargingParticle`, `TrailParticle`, `ParticleDict` definidos em múltiplos arquivos.

**Solução:** Criar `game/entities/particle_types.py` com todos os TypedDicts de partículas. Cada arquivo importa deste módulo central.

#### 2b. `TrailParticle` + lógica de trail (`BossSquare` vs `SquareMinionBoss`)
Quase 100% do código de trail é idêntico.

**Solução:** Extrair mixin ou classe base `SquareProjectileBase` em `game/entities/square_base.py` com toda a lógica de trail, animação de borda e `_draw_animated_border`. `BossSquare` e `SquareMinionBoss` herdam e sobrescrevem apenas cor e comportamento específico.

#### 2c. Partícula de zone (`_FireParticle` vs `_PlusParticle` em `fire_zone`/`ice_poison_zone`)
Estrutura `@dataclass` com campos `x, y, age, lifetime, base_size, rotation, rot_speed` idêntica.

**Solução:** Criar `ZoneParticle` em `game/entities/zone_base.py` (já existe a base) como dataclass base. Subclasses sobrescrevem apenas `current_size` e `alpha` se necessário.

#### 2d. `_wrap_text` duplicado em 4+ lugares
`settings.py`, `world_transition.py`, `difficulty_selection.py`, `upgrades_selection.py`, `statistics.py`.

**Solução:** Mover para `game/scenes/ui_helpers.py` (arquivo já existe) como função utilitária `wrap_text(text, font, max_width) -> list[str]`.

#### 2e. `render_with_fade` + lógica de transição duplicada
`settings.py` e `statistics.py` têm blocos de transição idênticos.

**Solução:** Já existe `render_with_fade` em `ui_helpers.py`. Verificar se ambas as cenas a usam corretamente — aparentemente sim, mas o bloco `_on_back` + campos `transitioning/fade_out/transition_progress` está duplicado. Extrair `FadeTransitionMixin` com esses campos e o método `_on_back` padrão.

#### 2f. Lógica `on_hit` / `collision_circle` duplicada em entidades
`MountainMage`, `StoneSentry`, `MountainSerpentBoss`, `StoneGolemBoss` têm implementações quase idênticas de `on_hit`, `collision_circle` e `take_damage`.

**Solução:** Já existe `BossHitMixin` — expandir ou criar `EnemyHitMixin` genérico com implementação padrão de `collision_circle` (baseada em `self.rect`) e `on_hit` parametrizado por `points` e `explosion_size`.

#### 2g. `LevelConfig` construído identicamente em dois lugares
`_apply_difficulty_to_fixed_level` em `_legacy.py` e `DifficultyAdjuster._apply_to_config` em `meta_progression.py`.

**Solução:** Mover o método de ajuste para `_legacy.py` (onde `LevelConfig` é definido) e importar em `meta_progression.py`. Ou usar `dataclasses.replace()` diretamente com os campos ajustados.

#### 2h. Keybindings padrão duplicados
Lista `[K_1, K_2, ..., K_9]` em `meta_progression.py` e `gameplay_input_handler.py`.

**Solução:** Definir `DEFAULT_KEYBINDINGS: list[int]` em `game/core/upgrades_config.py` e importar nos dois lugares.

#### 2i. Rainbow colors duplicadas
`game/core/colors.py` e `game/scenes/main_menu.py`.

**Solução:** Expor a lista de `RAINBOW_COLORS` de `colors.py` e importar em `main_menu.py`.

#### 2j. Score accumulation pattern duplicado em `collision_physics` vs `collisions`
Blocos `score_gain += result.points / if result.killed / destroyed_count += 1` repetidos.

**Solução:** Já existe `apply_hit` em `CollisionPhysics` que retorna `HitResult`. O problema é o *loop de acumulação* ao redor — extrair `_accumulate_hit_result(result, score_gain, destroyed_count, score_events, hit_x, hit_y)` como helper estático.

---

### Resumo de Arquivos a Criar

| Arquivo | Conteúdo |
|---|---|
| `game/entities/particle_types.py` | TypedDicts: `DeathParticle`, `ChargingParticle`, `TrailParticle`, `ParticleDict`, `ZoneParticle` |
| `game/entities/square_base.py` | `SquareProjectileBase` com trail + `_draw_animated_border` |
| `game/entities/enemy_hit_mixin.py` | `EnemyHitMixin` com `on_hit`, `collision_circle`, `on_ship_contact` padrão |
| `game/scenes/ui_helpers.py` (expandir) | `wrap_text`, `FadeTransitionMixin` |
| `game/core/upgrades_config.py` (expandir) | `DEFAULT_KEYBINDINGS` |
| `game/core/colors.py` (expandir) | `RAINBOW_COLORS` como constante exportada |

### Ordem de Execução Recomendada

1. `particle_types.py` — zero risco, sem lógica
2. `DEFAULT_KEYBINDINGS` + `RAINBOW_COLORS` — trivial
3. `wrap_text` em `ui_helpers.py` — baixo risco
4. `ZoneParticle` em `zone_base.py` — baixo risco
5. `SquareProjectileBase` — médio risco, testar colisão
6. `EnemyHitMixin` — médio risco, testar todos os inimigos afetados
7. `FadeTransitionMixin` — médio risco
8. `LevelConfig` ajuste consolidado — alto risco, testar progressão completa
9. Importações cíclicas — alto risco, testar inicialização completa do jogo