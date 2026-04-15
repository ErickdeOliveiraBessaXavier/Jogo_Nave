# Manual do Sistema Procedural de Fases
> Referência para IA ajustar geração de níveis, mundos e spawn de inimigos.

---

## Arquivos Relevantes

| Arquivo | Responsabilidade |
|---|---|
| `game/core/world_config.py` | Definição de mundos, temas e rotação procedural |
| `game/core/levels.py` | Geração de fases, pesos de spawn, pipeline de modificadores |
| `game/core/difficulty.py` | Presets de dificuldade e seus multiplicadores |
| `game/core/meta_progression.py` | Perfil do jogador, ajuste adaptativo, checkpoints |
| `game/systems/spawner.py` | Spawn em tempo real, formações, minas, meteoros guiados |

---

## 1. Estrutura de Mundos (`world_config.py`)

### Mundos fixos (níveis 1–45)

```
Mundo 1 — Cordilheira Celestial  → níveis 1–10   → boss: StoneGolemBoss
Mundo 2 — Vazio Sideral          → níveis 11–25  → boss: definido em FIXED_LEVELS
Mundo 3 — Metrópole Neon         → níveis 26–35  → boss: GiantMeteorBoss
Mundo 4 — Núcleo Vulcânico       → níveis 36–45  → boss: SlimeBoss
```

### Rotação procedural (níveis 46+)

- A cada 10 níveis = 1 setor novo.
- Tema rotaciona: MOUNTAINS → STARFIELD → CITY → VOLCANIC → (repete).
- Boss é `None` (procedural).

### ⚠️ Bug conhecido no cálculo de setor (níveis 41+)

O cálculo atual de `sector_id` usa `(level_number - 1) // 10 + 1`, o que causa
colisão de setor entre níveis 41–50 e 50–59. O cálculo correto deve ser:

```python
offset = level_number - 41        # base zero a partir do nível 41
sector_id = offset // 10          # 0, 1, 2, ...
sector_start = 41 + sector_id * 10
sector_end = sector_start + 9
theme_index = sector_id % 4       # rotaciona entre os 4 temas
```

### Como adicionar um novo mundo fixo

1. Criar `WorldConfig` em `_get_worlds()` com `world_id`, `start_level`, `end_level`, `boss_level`, `boss_type` e `theme_modifiers`.
2. Garantir que `start_level` do novo mundo = `end_level` do anterior + 1 (mundos devem ser contíguos).
3. Atualizar o threshold de rotação procedural se necessário.

---

## 2. Pipeline de Modificadores de Spawn (`levels.py`)

Toda fase passa por este pipeline antes de chegar ao spawner:

```
generate_level() ou FIXED_LEVELS
        ↓
_apply_world_theme_to_config()   ← aplica theme_modifiers do WorldConfig
        ↓
_apply_theme_enemy_eligibility() ← remove inimigos proibidos no tema (ENEMY_THEME_ALLOWLIST)
        ↓
_apply_theme_enemy_weights()     ← ajusta frequência por tema (ENEMY_THEME_WEIGHT_MULTIPLIERS)
        ↓
_apply_stage_progression_enemy_weights() ← ajusta por posição no mundo (early/mid/late)
        ↓
LevelConfig final entregue ao spawner
```

**Regra do cache:** `generate_level()` usa `@lru_cache`. As funções `_apply_*`
**devem sempre retornar novas instâncias** de `LevelConfig` — nunca mutar in-place.

---

## 3. Controle de Frequência de Inimigos

### Camada 1 — `theme_modifiers` (WorldConfig)

Modifica spawn time por tipo de inimigo para o mundo inteiro.

```python
theme_modifiers={
    "meteor_weight": 1.8,        # ÷ spawn_time → meteoros mais frequentes
    "alien_weight": 0.5,         # ÷ spawn_time → aliens menos frequentes
    "rock_glider_weight": 2.0,
    "eye_weight": 1.5,
    "spawn_rate_multiplier": 1.15,  # multiplica todos os tipos
}
```

### Camada 2 — `ENEMY_THEME_WEIGHT_PROFILES` (levels.py)

Perfis por tema (conservative / moderate / aggressive). Perfil ativo definido em:
```python
ACTIVE_ENEMY_TUNING_PROFILE = "moderate"  # alterar aqui para trocar perfil global
```

Valores > 1.0 aumentam frequência (reduzem spawn_time). Aplicados após camada 1.

### Camada 3 — `ENEMY_STAGE_WEIGHT_PROFILES` (levels.py)

Ajustes por faixa de estágio dentro do mundo:
- `early` → primeiros 33% dos estágios do mundo
- `mid`   → 34%–66%
- `late`  → últimos 34%

Permite que certos inimigos apareçam mais no final do mundo (ex: StoneSentry cresce em `late`).

### Elegibilidade por tema — `ENEMY_THEME_ALLOWLIST`

Se um tipo está na allowlist, ele **só aparece nos temas listados**.
Se não está na allowlist, aparece em todos os temas.

```python
ENEMY_THEME_ALLOWLIST = {
    RockGlider: {WorldTheme.MOUNTAINS},          # exclusivo do mundo de montanhas
    StoneSentry: {WorldTheme.MOUNTAINS},
    ElementalRobot: {WorldTheme.MOUNTAINS},
    Meteor: {STARFIELD, CITY, VOLCANIC, PROCEDURAL},  # proibido em MOUNTAINS
}
```

**Substituição automática:** `THEME_ENEMY_REPLACEMENTS` define fallback quando um
inimigo é removido pela elegibilidade:
```python
(WorldTheme.MOUNTAINS, Meteor): RockGlider   # Meteor → RockGlider em montanhas
```

---

## 4. Temas de Fase (`LevelTheme`)

Temas são selecionados proceduralmente por `_choose_theme()`. Cada tema define:

| Campo | Efeito |
|---|---|
| `enemy_weight` | Pesos relativos de cada tipo (0.0 = não spawna) |
| `spawn_rate_multiplier` | Multiplica taxa geral de spawn |
| `enemies_multiplier` | Multiplica `enemies_to_clear` |
| `special_feature` | `"mines_heavy"`, `"formations_heavy"`, `"meteor_only"` |

### Temas disponíveis

| Nome | Característica |
|---|---|
| `balanced` | Mix padrão |
| `asteroid_field` | Muitos meteoros |
| `alien_invasion` | Muitos aliens |
| `eye_swarm` | Muitos EyeEnemy (nível 5+) |
| `minefield` | Minas ativadas forçadas (nível 2+) |
| `formation_hell` | Formações constantes (nível 4+) |
| `meteor_storm` | Só meteoros, spawn extremo, spawna GiantMeteorBoss |

### Lógica de seleção por nível

```
nível 1–2      → sempre "balanced"
nível 8+, múltiplo de 5 → 40% chance de "meteor_storm"
nível 6+       → chance crescente de tema especial (max 70%)
demais         → escolha aleatória entre standard_themes
```

---

## 5. Limites de Spawn em Tela (`DifficultyConfig`)

Caps rígidos verificados antes de qualquer spawn:

```python
MAX_METEORS_ON_SCREEN     = 35
MAX_ALIENS_ON_SCREEN      = 12
MAX_EYES_ON_SCREEN        = 5
MAX_SQUARE_MINIONS_ON_SCREEN = 3
MAX_TOTAL_ENEMIES_ON_SCREEN  = 50

# Caps especiais por tipo (verificados em _should_spawn_enemy):
ElementalRobot → máximo 1 na tela
StoneSentry    → máximo 3 na tela
```

`SPAWN_REDUCTION_THRESHOLD = 0.8` — ao atingir 80% do cap, spawn tem 50% de chance de ser suprimido.

`MIN_SPAWN_TIME = 0.3` — nenhum inimigo pode ter spawn_time menor que isso após todos os modificadores.

---

## 6. Spawn Ponderado (`spawner.py`)

Ativo quando `DifficultyConfig.WEIGHTED_SPAWN_ENABLED = True`.

- Um único timer (`WEIGHTED_SPAWN_TICK = 0.15s`) substitui timers por tipo.
- Pesos calculados como `1.0 / spawn_time` (spawn menor = peso maior).
- **Anti-repetição:** `WEIGHTED_RECENT_MEMORY = 3` últimos tipos são penalizados por `WEIGHTED_REPEAT_PENALTY = 0.45` por repetição.
- Telemetria opcional: `WEIGHTED_SPAWN_TELEMETRY = True` loga distribuição a cada `WEIGHTED_TELEMETRY_INTERVAL = 15s`.

---

## 7. Presets de Dificuldade (`difficulty.py`)

| Preset | spawn_rate_mult | enemy_health_mult | lives | rewards_mult |
|---|---|---|---|---|
| CASUAL | 0.75 | 0.8 | 5 | 0.8 |
| NORMAL | 1.0 | 1.0 | 3 | 1.0 |
| HARDCORE | 1.4 | 1.3 | 2 | 1.5 |
| NIGHTMARE | 2.0 | 1.5 | 1 | 3.0 |

NIGHTMARE tem regras especiais: `permadeath` e `no_powerups`.  
HARDCORE e NIGHTMARE ignoram FIXED_LEVELS no nível 1 (sem tutorial).

---

## 8. Meta-Progressão e Ajuste Adaptativo (`meta_progression.py`)

O `PlayerProfile` monitora performance por nível e aplica ajuste automático:

```
clear_rate < 30% (5+ tentativas) → facilitar até 15%
clear_rate > 85% + win_streak ≥ 3 → dificultar até 15%
```

Limites do ajuste: `[0.75, 1.25]` (nunca mais que ±25%).  
Ajuste é suavizado: 50% do delta por tentativa (`ADJUSTMENT_SPEED = 0.5`).

### Sistema de checkpoints

- Ao entrar em um mundo novo pela primeira vez → checkpoint salvo.
- Ao morrer → `reset_to_checkpoint()` retorna ao `start_level` do mundo checkpoint.
- Mundos 1–4 são os únicos com checkpoint nomeado.

---

## 9. Checklist para Ajustes Comuns

### Tornar um mundo mais difícil
→ Aumentar valores em `theme_modifiers` do `WorldConfig` (`meteor_weight`, `spawn_rate_multiplier`).  
→ Aumentar valores em `ENEMY_THEME_WEIGHT_PROFILES["moderate"][WorldTheme.X]`.  
→ Aumentar valores em `"late"` do `ENEMY_STAGE_WEIGHT_PROFILES`.

### Adicionar novo tipo de inimigo a um tema
1. Adicionar à `ENEMY_THEME_ALLOWLIST` com os temas permitidos (ou omitir para todos).
2. Adicionar `DEFAULT_ENEMY_SPAWN_TIME[NovoTipo]`.
3. Adicionar pesos nos três perfis de `ENEMY_THEME_WEIGHT_PROFILES`.
4. Adicionar pesos em `ENEMY_STAGE_WEIGHT_PROFILES` para cada faixa.
5. Adicionar ao `THEME_FALLBACK_ENEMIES` dos temas relevantes.
6. Implementar spawn em `_spawn_enemy_of_type()` no `spawner.py`.

### Criar novo tema de fase
1. Adicionar entrada em `LEVEL_THEMES` com `enemy_weight`, multiplicadores e `special_feature`.
2. Incluir o tema na lógica de `_choose_theme()` com condição de desbloqueio.
3. Se tiver `special_feature` nova, tratar em `generate_config()`.

### Ajustar curva de dificuldade geral
→ `DifficultyConfig.SPAWN_RATE_CURVE`: `"logarithmic"` (padrão), `"linear"`, `"exponential"`.  
→ `DifficultyConfig.DIFFICULTY_SCALING`: escalar base (padrão `0.15`).  
→ `DifficultyConfig.MAX_DIFFICULTY_MULTIPLIER`: teto da dificuldade (padrão `2.5`).

---

## 10. Invariantes que Devem Ser Mantidas

1. `MIN_SPAWN_TIME` deve ser respeitado após **todos** os modificadores.
2. Funções `_apply_*` devem retornar **novas instâncias** de `LevelConfig` (nunca mutar).
3. Mundos fixos (1–4) devem ser **contíguos** (`end_level + 1 == próximo start_level`).
4. `boss_level` deve estar dentro de `[start_level, end_level]` do mundo.
5. Todo tipo de inimigo em `FIXED_LEVELS` ou gerado proceduralmente deve ter entrada em `DEFAULT_ENEMY_SPAWN_TIME`.
6. `ENEMY_THEME_WEIGHT_PROFILES` e `ENEMY_STAGE_WEIGHT_PROFILES` devem ter entradas para **todos os três perfis** (conservative, moderate, aggressive) ao adicionar novos temas.# Manual do Sistema Procedural de Fases
> Referência para IA ajustar geração de níveis, mundos e spawn de inimigos.

---

## Arquivos Relevantes

| Arquivo | Responsabilidade |
|---|---|
| `game/core/world_config.py` | Definição de mundos, temas e rotação procedural |
| `game/core/levels.py` | Geração de fases, pesos de spawn, pipeline de modificadores |
| `game/core/difficulty.py` | Presets de dificuldade e seus multiplicadores |
| `game/core/meta_progression.py` | Perfil do jogador, ajuste adaptativo, checkpoints |
| `game/systems/spawner.py` | Spawn em tempo real, formações, minas, meteoros guiados |

---

## 1. Estrutura de Mundos (`world_config.py`)

### Mundos fixos (níveis 1–45)

```
Mundo 1 — Cordilheira Celestial  → níveis 1–10   → boss: StoneGolemBoss
Mundo 2 — Vazio Sideral          → níveis 11–25  → boss: definido em FIXED_LEVELS
Mundo 3 — Metrópole Neon         → níveis 26–35  → boss: GiantMeteorBoss
Mundo 4 — Núcleo Vulcânico       → níveis 36–45  → boss: SlimeBoss
```

### Rotação procedural (níveis 46+)

- A cada 10 níveis = 1 setor novo.
- Tema rotaciona: MOUNTAINS → STARFIELD → CITY → VOLCANIC → (repete).
- Boss é `None` (procedural).

### ⚠️ Bug conhecido no cálculo de setor (níveis 41+)

O cálculo atual de `sector_id` usa `(level_number - 1) // 10 + 1`, o que causa
colisão de setor entre níveis 41–50 e 50–59. O cálculo correto deve ser:

```python
offset = level_number - 41        # base zero a partir do nível 41
sector_id = offset // 10          # 0, 1, 2, ...
sector_start = 41 + sector_id * 10
sector_end = sector_start + 9
theme_index = sector_id % 4       # rotaciona entre os 4 temas
```

### Como adicionar um novo mundo fixo

1. Criar `WorldConfig` em `_get_worlds()` com `world_id`, `start_level`, `end_level`, `boss_level`, `boss_type` e `theme_modifiers`.
2. Garantir que `start_level` do novo mundo = `end_level` do anterior + 1 (mundos devem ser contíguos).
3. Atualizar o threshold de rotação procedural se necessário.

---

## 2. Pipeline de Modificadores de Spawn (`levels.py`)

Toda fase passa por este pipeline antes de chegar ao spawner:

```
generate_level() ou FIXED_LEVELS
        ↓
_apply_world_theme_to_config()   ← aplica theme_modifiers do WorldConfig
        ↓
_apply_theme_enemy_eligibility() ← remove inimigos proibidos no tema (ENEMY_THEME_ALLOWLIST)
        ↓
_apply_theme_enemy_weights()     ← ajusta frequência por tema (ENEMY_THEME_WEIGHT_MULTIPLIERS)
        ↓
_apply_stage_progression_enemy_weights() ← ajusta por posição no mundo (early/mid/late)
        ↓
LevelConfig final entregue ao spawner
```

**Regra do cache:** `generate_level()` usa `@lru_cache`. As funções `_apply_*`
**devem sempre retornar novas instâncias** de `LevelConfig` — nunca mutar in-place.

---

## 3. Controle de Frequência de Inimigos

### Camada 1 — `theme_modifiers` (WorldConfig)

Modifica spawn time por tipo de inimigo para o mundo inteiro.

```python
theme_modifiers={
    "meteor_weight": 1.8,        # ÷ spawn_time → meteoros mais frequentes
    "alien_weight": 0.5,         # ÷ spawn_time → aliens menos frequentes
    "rock_glider_weight": 2.0,
    "eye_weight": 1.5,
    "spawn_rate_multiplier": 1.15,  # multiplica todos os tipos
}
```

### Camada 2 — `ENEMY_THEME_WEIGHT_PROFILES` (levels.py)

Perfis por tema (conservative / moderate / aggressive). Perfil ativo definido em:
```python
ACTIVE_ENEMY_TUNING_PROFILE = "moderate"  # alterar aqui para trocar perfil global
```

Valores > 1.0 aumentam frequência (reduzem spawn_time). Aplicados após camada 1.

### Camada 3 — `ENEMY_STAGE_WEIGHT_PROFILES` (levels.py)

Ajustes por faixa de estágio dentro do mundo:
- `early` → primeiros 33% dos estágios do mundo
- `mid`   → 34%–66%
- `late`  → últimos 34%

Permite que certos inimigos apareçam mais no final do mundo (ex: StoneSentry cresce em `late`).

### Elegibilidade por tema — `ENEMY_THEME_ALLOWLIST`

Se um tipo está na allowlist, ele **só aparece nos temas listados**.
Se não está na allowlist, aparece em todos os temas.

```python
ENEMY_THEME_ALLOWLIST = {
    RockGlider: {WorldTheme.MOUNTAINS},          # exclusivo do mundo de montanhas
    StoneSentry: {WorldTheme.MOUNTAINS},
    ElementalRobot: {WorldTheme.MOUNTAINS},
    Meteor: {STARFIELD, CITY, VOLCANIC, PROCEDURAL},  # proibido em MOUNTAINS
}
```

**Substituição automática:** `THEME_ENEMY_REPLACEMENTS` define fallback quando um
inimigo é removido pela elegibilidade:
```python
(WorldTheme.MOUNTAINS, Meteor): RockGlider   # Meteor → RockGlider em montanhas
```

---

## 4. Temas de Fase (`LevelTheme`)

Temas são selecionados proceduralmente por `_choose_theme()`. Cada tema define:

| Campo | Efeito |
|---|---|
| `enemy_weight` | Pesos relativos de cada tipo (0.0 = não spawna) |
| `spawn_rate_multiplier` | Multiplica taxa geral de spawn |
| `enemies_multiplier` | Multiplica `enemies_to_clear` |
| `special_feature` | `"mines_heavy"`, `"formations_heavy"`, `"meteor_only"` |

### Temas disponíveis

| Nome | Característica |
|---|---|
| `balanced` | Mix padrão |
| `asteroid_field` | Muitos meteoros |
| `alien_invasion` | Muitos aliens |
| `eye_swarm` | Muitos EyeEnemy (nível 5+) |
| `minefield` | Minas ativadas forçadas (nível 2+) |
| `formation_hell` | Formações constantes (nível 4+) |
| `meteor_storm` | Só meteoros, spawn extremo, spawna GiantMeteorBoss |

### Lógica de seleção por nível

```
nível 1–2      → sempre "balanced"
nível 8+, múltiplo de 5 → 40% chance de "meteor_storm"
nível 6+       → chance crescente de tema especial (max 70%)
demais         → escolha aleatória entre standard_themes
```

---

## 5. Limites de Spawn em Tela (`DifficultyConfig`)

Caps rígidos verificados antes de qualquer spawn:

```python
MAX_METEORS_ON_SCREEN     = 35
MAX_ALIENS_ON_SCREEN      = 12
MAX_EYES_ON_SCREEN        = 5
MAX_SQUARE_MINIONS_ON_SCREEN = 3
MAX_TOTAL_ENEMIES_ON_SCREEN  = 50

# Caps especiais por tipo (verificados em _should_spawn_enemy):
ElementalRobot → máximo 1 na tela
StoneSentry    → máximo 3 na tela
```

`SPAWN_REDUCTION_THRESHOLD = 0.8` — ao atingir 80% do cap, spawn tem 50% de chance de ser suprimido.

`MIN_SPAWN_TIME = 0.3` — nenhum inimigo pode ter spawn_time menor que isso após todos os modificadores.

---

## 6. Spawn Ponderado (`spawner.py`)

Ativo quando `DifficultyConfig.WEIGHTED_SPAWN_ENABLED = True`.

- Um único timer (`WEIGHTED_SPAWN_TICK = 0.15s`) substitui timers por tipo.
- Pesos calculados como `1.0 / spawn_time` (spawn menor = peso maior).
- **Anti-repetição:** `WEIGHTED_RECENT_MEMORY = 3` últimos tipos são penalizados por `WEIGHTED_REPEAT_PENALTY = 0.45` por repetição.
- Telemetria opcional: `WEIGHTED_SPAWN_TELEMETRY = True` loga distribuição a cada `WEIGHTED_TELEMETRY_INTERVAL = 15s`.

---

## 7. Presets de Dificuldade (`difficulty.py`)

| Preset | spawn_rate_mult | enemy_health_mult | lives | rewards_mult |
|---|---|---|---|---|
| CASUAL | 0.75 | 0.8 | 5 | 0.8 |
| NORMAL | 1.0 | 1.0 | 3 | 1.0 |
| HARDCORE | 1.4 | 1.3 | 2 | 1.5 |
| NIGHTMARE | 2.0 | 1.5 | 1 | 3.0 |

NIGHTMARE tem regras especiais: `permadeath` e `no_powerups`.  
HARDCORE e NIGHTMARE ignoram FIXED_LEVELS no nível 1 (sem tutorial).

---

## 8. Meta-Progressão e Ajuste Adaptativo (`meta_progression.py`)

O `PlayerProfile` monitora performance por nível e aplica ajuste automático:

```
clear_rate < 30% (5+ tentativas) → facilitar até 15%
clear_rate > 85% + win_streak ≥ 3 → dificultar até 15%
```

Limites do ajuste: `[0.75, 1.25]` (nunca mais que ±25%).  
Ajuste é suavizado: 50% do delta por tentativa (`ADJUSTMENT_SPEED = 0.5`).

### Sistema de checkpoints

- Ao entrar em um mundo novo pela primeira vez → checkpoint salvo.
- Ao morrer → `reset_to_checkpoint()` retorna ao `start_level` do mundo checkpoint.
- Mundos 1–4 são os únicos com checkpoint nomeado.

---

## 9. Checklist para Ajustes Comuns

### Tornar um mundo mais difícil
→ Aumentar valores em `theme_modifiers` do `WorldConfig` (`meteor_weight`, `spawn_rate_multiplier`).  
→ Aumentar valores em `ENEMY_THEME_WEIGHT_PROFILES["moderate"][WorldTheme.X]`.  
→ Aumentar valores em `"late"` do `ENEMY_STAGE_WEIGHT_PROFILES`.

### Adicionar novo tipo de inimigo a um tema
1. Adicionar à `ENEMY_THEME_ALLOWLIST` com os temas permitidos (ou omitir para todos).
2. Adicionar `DEFAULT_ENEMY_SPAWN_TIME[NovoTipo]`.
3. Adicionar pesos nos três perfis de `ENEMY_THEME_WEIGHT_PROFILES`.
4. Adicionar pesos em `ENEMY_STAGE_WEIGHT_PROFILES` para cada faixa.
5. Adicionar ao `THEME_FALLBACK_ENEMIES` dos temas relevantes.
6. Implementar spawn em `_spawn_enemy_of_type()` no `spawner.py`.

### Criar novo tema de fase
1. Adicionar entrada em `LEVEL_THEMES` com `enemy_weight`, multiplicadores e `special_feature`.
2. Incluir o tema na lógica de `_choose_theme()` com condição de desbloqueio.
3. Se tiver `special_feature` nova, tratar em `generate_config()`.

### Ajustar curva de dificuldade geral
→ `DifficultyConfig.SPAWN_RATE_CURVE`: `"logarithmic"` (padrão), `"linear"`, `"exponential"`.  
→ `DifficultyConfig.DIFFICULTY_SCALING`: escalar base (padrão `0.15`).  
→ `DifficultyConfig.MAX_DIFFICULTY_MULTIPLIER`: teto da dificuldade (padrão `2.5`).

---

## 10. Invariantes que Devem Ser Mantidas

1. `MIN_SPAWN_TIME` deve ser respeitado após **todos** os modificadores.
2. Funções `_apply_*` devem retornar **novas instâncias** de `LevelConfig` (nunca mutar).
3. Mundos fixos (1–4) devem ser **contíguos** (`end_level + 1 == próximo start_level`).
4. `boss_level` deve estar dentro de `[start_level, end_level]` do mundo.
5. Todo tipo de inimigo em `FIXED_LEVELS` ou gerado proceduralmente deve ter entrada em `DEFAULT_ENEMY_SPAWN_TIME`.
6. `ENEMY_THEME_WEIGHT_PROFILES` e `ENEMY_STAGE_WEIGHT_PROFILES` devem ter entradas para **todos os três perfis** (conservative, moderate, aggressive) ao adicionar novos temas.