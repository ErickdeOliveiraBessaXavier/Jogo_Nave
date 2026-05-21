# Plano de Revisão — Space Shooter

Próximo ciclo de revisão técnica. Item levantado, avaliado, classificado e fechado
quando concluído. O arquivo deve refletir o estado atual — atualize gravidade/status
conforme o trabalho avança.

---

## Escopo

Avaliação focada em código de produção (`game/`) e infraestrutura de build/scripts.
Itens fora do escopo: assets binários, documentos em `código_teste/`, ferramentas
de profiling não usadas em runtime.

---

## Critérios de gravidade

- **Crítico** — viola um princípio do CLAUDE.md (coupling, side-effects em render,
  global state), causa bug observável, ou bloqueia evolução de outra área.
- **Médio** — não bloqueia, mas degrada legibilidade/testabilidade ou fere
  composição/extensão.
- **Baixo** — polimento, nomenclatura, remoção de comentário redundante.

---

## Backlog

### Crítico

#### 1. `Ship` acumula renderização, movimento, powerups e targeting na mesma classe

**Sintoma:** `ship.py` (~1750 LOC) contém em um único arquivo:
- `draw()` com ~300+ linhas renderizando escudo, orbital lasers, chain shot,
  repulsion shield, partículas e dash trail
- `move()` com lógica de mouse-spring, gamepad, teclado, inversão de controles
  e dash simultaneamente
- `_update_timers()` gerenciando >15 timers de powerup independentes
- `bullet_spawn()` com posições hardcoded por facing direction (~100 LOC)
- `activate_orbital_lasers()`, `activate_chain_shot()`, etc. — API de powerups
  crescendo sem contrato formal

**Causa:** `Ship` nasceu como entidade simples e absorveu responsabilidades à
medida que novas mecânicas foram adicionadas, sem fronteira arquitetural explícita.

**Impacto:** Qualquer nova nave ou powerup exige editar `ship.py`. Bugs em
renderização e movimento compartilham o mesmo espaço de risco.

**Direção — decomposição por composição:**

```
entities/
  ship.py           ← fachada pública, mantém API externa intacta
  ship_renderer.py  ← draw() e todos os efeitos visuais
  ship_powerups.py  ← activate_*, timers de powerup, _update_timers()
  ship_movement.py  ← move(), _keep_in_bounds(), dash logic
```

Extração na ordem: `draw()` primeiro (maior isolamento de risco), depois
powerups, depois `move()`.

**Arquivos afetados:** `entities/ship.py`, possivelmente `entities/mini_ship.py`
para alinhar a API quando aplicável.

**Status:** Concluído — `ship.py` reduzido de 1699 → 835 LOC. Extraídos
`ship_renderer.py` (370), `ship_powerups.py` (324) e `ship_movement.py` (230).
`Ship` permanece fachada pública: `draw()`, `move()`, `try_dash()`,
`activate_*`, `consume_*`, `try_store_powerup` delegam para os componentes.

---

#### 2. `PlayingScene` concentra input de gameplay, powerups, cheats e transições (~2300 LOC)

**Sintoma:** Após as extrações anteriores, `playing.py` ainda contém:
- `handle_event()` com tratamento direto de KEYDOWN, MOUSEBUTTONDOWN,
  MOUSEBUTTONUP, JOYAXISMOTION, JOYBUTTONDOWN — input de gameplay acoplado à cena
- `_apply_powerup()` com dict-dispatch de 13 powerups inline na cena
- `_process_cheat_input()` duplicado — também existe em `main_menu.py:669-684`
  com `_CHEAT_CODE = "271195"` redefinido como variável local
- FSM de `TransitionPhase` (6 estados) com timers dispersos em 4 métodos de update

**Causa:** A cena serve de hub de coordenação mesmo após as extrações anteriores.
Lógica que deveria estar em controladores especializados foi mantida inline para
simplicidade de acesso a `self.ship`, `self.entity_manager` e `self.score`.

**Impacto:** Novos powerups, transições ou input acumulam em `playing.py` sem
alternativa estrutural. Bloqueia evolução independente de cada domínio.

**Direção — extrações prioritárias:**

```
systems/
  powerup_system.py        ← _apply_powerup() + _process_powerups_and_stars()
  input_handler.py         ← handle_event() de gameplay
  transition_controller.py ← TransitionPhase FSM + timers associados
  cheat_input.py           ← _CHEAT_CODE + buffer compartilhado entre cenas
```

Cheat code: centralizar `_CHEAT_CODE` e a lógica de buffer; `playing.py` e
`main_menu.py` consomem o mesmo módulo.

**Arquivos afetados:** `scenes/playing.py`, `scenes/main_menu.py`, novos
arquivos em `systems/`.

**Status:** Concluído. `playing.py` reduzido de 2321 → 1904 LOC (-417, ~18%).

- ✅ `cheat_input.py` extraído: `CheatBuffer` em `systems/cheat_input.py`;
  `playing.py` e `main_menu.py` consomem o mesmo módulo (sem mais duplicação
  do code "271195").
- ✅ `powerup_system.py` extraído: `PowerupSystem` em `systems/powerup_system.py`
  com dispatch de classe (`_dispatch`) e métodos `apply(kind)` /
  `process_collection()`. `PlayingScene._apply_powerup` e
  `_process_powerups_and_stars` viraram delegators thin.
- ✅ `gameplay_input_handler.py` extraído: `GameplayInputHandler` em
  `systems/gameplay_input_handler.py`. Movidos `handle_event`,
  `_handle_gamepad_button/hat/axis`, `_gamepad_dash_vector` e
  `_handle_upgrade_key`. Estado `_lt_pressed`/`_lt_calibrated` migrou com o
  handler. `PlayingScene.handle_event` virou one-liner.
- ✅ `transition_controller.py` extraído: `TransitionController` +
  `TransitionPhase` em `systems/transition_controller.py`. Controller owns
  `phase` e os timers de fase (`level_transition_timer`,
  `level_transition_pending_timer`); cena consulta via gates (`is_*`,
  `can_handle_gameplay_actions`) e chama `update_post_victory(dt)` /
  `update_level_transition_wait(dt, animations_finished)`. Cena reexporta
  `TransitionPhase` por back-compat. Cutscene visual (particles + animação)
  ficou na cena — fora do escopo "FSM + timers".

---

### Médio

#### 3. `levels.py` mistura dados estáticos, geração procedural e pipeline (~2200 LOC)

**Sintoma:** O arquivo contém simultaneamente:
- `FIXED_LEVELS` — configuração handcrafted (dados puros)
- `ProceduralLevelGenerator` — geração procedural com seed e caches
- `get_level_config()` — pipeline de transformação com 5 etapas
- `LevelAnalyzer`, `LevelManager` — utilitários
- `DifficultyCurves`, `DifficultyConfig` — configuração de balanceamento

**Causa:** Crescimento incremental sem separação por domínio.

**Direção — separação em pacote:**

```
core/
  levels/
    __init__.py     ← re-exporta get_level_config, LevelManager (API pública inalterada)
    fixed_levels.py ← FIXED_LEVELS dict (dados puros, zero lógica)
    procedural.py   ← ProceduralLevelGenerator, DifficultyCurves, DifficultyConfig
    pipeline.py     ← get_level_config(), grace logic, _apply_theme_enemy_rules()
    analysis.py     ← LevelAnalyzer, LevelManager
```

**Arquivos afetados:** `core/levels.py` → pacote `core/levels/`. API pública
inalterada — callers importam de `core.levels` como antes.

**Status:** Parcial.
- ✅ Pacote `core/levels/` criado com `__init__.py` reexportando o contrato
  público (`get_level_config`, `LevelConfig`, `LevelManager`, `LevelAnalyzer`,
  `FIXED_LEVELS`, `DifficultyConfig`, `THEME_ENEMY_REPLACEMENTS`, `THEME_FEATURES`,
  `calculate_dynamic_enemy_cap`, `ProceduralLevelGenerator`, etc.). Imports
  relativos ajustados para o novo depth (`...entities`, `..difficulty`).
- ⏳ Conteúdo ainda monolítico em `_legacy.py` (2198 LOC). Split por domínio
  (`fixed_levels.py`, `procedural.py`, `pipeline.py`, `analysis.py`) fica
  como follow-up — a fronteira do pacote agora permite refinar
  incrementalmente sem mover a API pública de novo.

---

#### 4. `collisions.py` — helpers de física acoplados ao dispatcher

**Sintoma:** `_check_mask_collision` (L243), `_batch_query_for_projectiles`
(L310), `_apply_hit` (L340), `_apply_ship_contact` (L402) e `_apply_area_damage`
(L424) ficam no mesmo arquivo que os ~25 métodos `X_vs_Y`. Os helpers de física
têm baixa dependência de `EntityManager` e seriam testáveis isoladamente.

**Nota:** Registry/dispatch declarativo foi avaliado e descartado — o modelo
`X_vs_Y` tem coesão razoável e registry introduziria indireção sem ganho
concreto agora.

**Direção:** Extrair helpers para `systems/collision_physics.py`. `Collisions`
permanece como dispatcher, importando os helpers.

**Arquivos afetados:** `systems/collisions.py` → `systems/collision_physics.py`.
Sem alteração de API pública.

**Status:** Concluído.
- Helpers movidos para `systems/collision_physics.py`: classe `CollisionPhysics`
  com `check_mask_collision`, `apply_hit`, `apply_ship_contact`, `apply_area_damage`
  (instance methods que dependem de `EventBus`) + `batch_query_for_projectiles`
  (staticmethod). Funções de módulo `get_enemy_collision_mask_data` e
  `get_rect_mask` (com cache `_RECT_MASK_CACHE`).
- `Collisions.__init__` instancia `self.physics = CollisionPhysics(event_bus)`.
  5 wrappers thin em `Collisions` preservam os ~28 call sites internos
  (`self._apply_hit(...)` etc.) sem precisar reescrevê-los.
- `collisions.py` 1976 → 1794 LOC. Helpers agora testáveis isoladamente
  (só dependem de `EventBus`).

---

#### 5. `entity_manager.update()` longo (~260 LOC inline)

**Sintoma:** `update()` (L487–L748) itera múltiplos grupos inline com lógicas
próprias: dispatch polimórfico de inimigos, atualização de projéteis, cleanup
de boss squares com filter inline, atualização de mountain propellers, black
holes, etc. Difícil identificar fronteiras de responsabilidade.

**Causa:** Crescimento orgânico do método principal. Cada novo tipo de entidade
adicionou seu bloco inline.

**Direção:** Extrair `_update_enemies()`, `_update_projectiles()`,
`_update_effects()`, `_update_collectibles()` como métodos privados dentro do
mesmo arquivo. Sem novos arquivos necessários.

```python
def update(self, dt, player_x, player_y, ...):
    self._update_enemies(enemy_dt, player_x, player_y)
    self._update_projectiles(dt)
    self._update_effects(dt)
    self._update_collectibles(dt, attraction_mult)
    self.cleanup()
    self.rebuild_all_grids()
```

**Arquivos afetados:** `systems/entity_manager.py` apenas.

**Status:** Concluído.
- `update()` compactado para ~30 linhas chamando 12 sub-métodos por domínio:
  `_rebuild_enemy_caches`, `_update_visual_effects`, `_update_formations`,
  `_update_player_projectiles`, `_update_enemy_projectiles`,
  `_update_misc_effects`, `_update_collectibles`,
  `_update_floating_scores_and_mini_ships`, `_update_spikes`, `_update_boss`,
  `_update_enemies`, `_update_mountain_propellers`, `_update_energy_orbs`,
  `_update_environment`.
- EMP/ice multipliers via helper `_emp_state()` em vez de closures inline.
- Mesma API pública, mesmo arquivo. 1320 → 1367 LOC (overhead de docstrings
  e assinaturas — aceito pelo ganho de leitura do `update()`).

---

### Baixo

#### 6. Bloco de bosses — constantes inline e concentração de responsabilidades

**Sintoma:** `cloud_archmage_boss.py` tem paletas de cores e constantes de
sprite embutidas na classe. `stone_golem_boss.py` e `mountain_serpent_boss.py`
concentram FSM, física e renderização no mesmo arquivo.

**Direção:** Avaliar em bloco dedicado após conclusão dos itens 1–5.
`cloud_archmage` primeiro (constantes inline são cirúrgicas). Depois avaliar
se `BossRenderer` por boss é viável ou se o `BossParticleSystem` compartilhado
é suficiente.

**Status:** Pendente — bloco dedicado após itens 1–5.

---

## Ordem de execução recomendada

```
1. ship.py — extração de ShipRenderer (draw)         [Crítico]
2. ship.py — extração de ShipPowerups                [Crítico]
3. ship.py — extração de ShipMovement                [Crítico]
4. playing.py — cheat_input.py + remover duplicação  [Crítico, rápido]
5. playing.py — PowerupSystem                        [Crítico]
6. playing.py — InputHandler de gameplay             [Crítico]
7. levels.py — separação em pacote core/levels/      [Médio]
8. entity_manager.update() — reorganização interna   [Médio]
9. collisions.py — collision_physics.py              [Médio]
10. Bloco bosses                                     [Baixo]
```

Itens 7, 8, 9 podem ser feitos em paralelo por não terem dependência entre si.
Item 10 fica para depois.

---

## Decisões deliberadamente adiadas

- **Registry/dispatch declarativo em `collisions.py`** — modelo `X_vs_Y`
  tem coesão razoável. Reavaliar quando houver necessidade concreta de registrar
  novos tipos de colisão em runtime.

- **`LevelManager` como serviço com injeção de dependência** — a classe hoje
  é wrapper fino de `get_level_config()`. Ganho real só após extração de
  `playing.py` (item 2).

- **Herança de bosses / `BossBase`** — defer até o bloco de bosses ter
  visibilidade completa dos padrões compartilhados entre os bosses existentes.

- **Acesso por domínio em `Config` (`Config.meteors.MIN_METEOR_SIZE`)** —
  `__getattr__` flat é o contrato atual e funciona. Reavaliar só se houver
  conflito de nome entre domínios.

- **`enemy_projectiles_vs_ship` retornar à API mais simples** — após o ciclo
  anterior, o método aceita `grid` opcional. O ganho efetivo depende do tamanho
  da lista; medir com profiling em fase densa antes de decidir reverter.

---

## Status resumido

| # | Item | Gravidade | Status |
|---|------|-----------|--------|
| 1 | `Ship` acumula render, movimento, powerups e targeting | Crítico | Concluído |
| 2 | `PlayingScene` concentra input, powerups, cheats e transições | Crítico | Concluído |
| 3 | `levels.py` mistura dados, procedural e pipeline | Médio | Parcial (pacote criado; split por domínio deferido) |
| 4 | `collisions.py` — extrair helpers de física | Médio | Concluído |
| 5 | `entity_manager.update()` longo (~260 LOC) | Médio | Concluído |
| 6 | Bloco de bosses — constantes inline e responsabilidades | Baixo | Pendente |

---

## Pendências para o próximo ciclo

Itens não terminados neste ciclo, com escopo detalhado para retomar sem
contexto adicional.

### A. Split por domínio dentro de `core/levels/` (item 3)

**Estado atual:** O pacote `core/levels/` existe e expõe a API pública via
`__init__.py`. Todo o conteúdo continua em `_legacy.py` (2198 LOC) — o
arquivo é idêntico ao antigo `core/levels.py` salvo pelos imports relativos
ajustados para o depth do pacote (`...entities`, `..difficulty`,
`..world_config`).

**O que ainda falta fazer:** quebrar `_legacy.py` em 4–5 arquivos por
domínio dentro do pacote. A fronteira do pacote já está em pé; este
refinamento mexe apenas em arquivos internos.

**Ordem topológica sugerida** (cada passo importa apenas os anteriores):

1. **`_types.py`** — `EnemySpawnConfig` (alias de dict), `LevelTheme`
   (dataclass), `LevelConfig` (dataclass com métodos). Atenção:
   `LevelConfig` referencia `LEVEL_THEMES` em alguns métodos; resolver com
   import lazy (`from .fixed_levels import LEVEL_THEMES` dentro do método)
   ou inverter ordem em pontos pontuais.

2. **`fixed_levels.py`** — `LEVEL_THEMES: dict[str, LevelTheme]` (linhas
   771–889 do `_legacy.py`) + `FIXED_LEVELS: dict[int, LevelConfig]`
   (linhas 1636–1766). Dados puros, zero lógica. Importa `_types`.

3. **`procedural.py`** — `DifficultyConfig` (646–720), `DifficultyCurves`
   (728–751), constantes de pressão (`ENEMY_PRESSURE_TIER_BY_KEY`,
   `ENEMY_PRESSURE_TIER_CURVE`, `ENEMY_PRESSURE_UNLOCK_START`,
   `ENEMY_PRESSURE_UNLOCK_WINDOW`, ~891–921), helpers (`_clamp01`,
   `_get_world_stage_progress`, `_get_progressive_enemy_weight`,
   `calculate_dynamic_enemy_cap` em 932–1021), `ProceduralLevelGenerator`
   (1160–1628). Importa `_types`, `fixed_levels`.

4. **`pipeline.py`** — todas as constantes/funções de regras de tema
   (`ACTIVE_ENEMY_TUNING_PROFILE`, `_STAGE_BANDED_THEMES`,
   `ENEMY_THEME_ALLOWLIST`, `ENEMY_THEME_WEIGHT_PROFILES`,
   `ENEMY_STAGE_WEIGHT_PROFILES`, `_resolve_tuning_profile`,
   `THEME_FALLBACK_ENEMIES`, `DEFAULT_ENEMY_SPAWN_TIME`,
   `THEME_ENEMY_REPLACEMENTS`, `THEME_FEATURES`,
   `MAX_ENEMY_VARIETY_BY_DIFFICULTY`, `MAX_ENEMY_VARIETY_BY_STAGE`,
   `THEME_BASE_ENEMY`, `_is_enemy_allowed_in_theme`,
   `_filter_enemy_spawn_for_theme`, `_apply_theme_enemy_eligibility`,
   `_apply_theme_enemy_weights`, `_get_stage_band`,
   `_apply_stage_progression_enemy_weights`, `_apply_enemy_variety_cap`,
   `_ThemeRuleStep`, `_THEME_RULES_PIPELINE`, `_apply_theme_enemy_rules`,
   `_ENEMY_COUNT_TABLE`, `DIFFICULTY_ENEMY_COUNT_MULTIPLIER`) +
   `_apply_world_theme_to_config` (1768–1822), `_create_world_boss_level`
   (1825–1878), `_procedural_generators` cache (1887),
   `get_level_config` (1890–2035), `_apply_difficulty_to_fixed_level`
   (2038–2069). Importa `_types`, `fixed_levels`, `procedural`.

5. **`analysis.py`** — `LevelManager` (2072–2088), `LevelAnalyzer`
   (2096–2198). Importa `pipeline`.

6. **Atualizar `__init__.py`** — trocar `from ._legacy import X` por
   `from .<submodulo> import X` para cada nome reexportado. Manter o
   `__all__` igual.

7. **Deletar `_legacy.py`.**

**Cuidados:**

- A circularidade `LevelConfig` ↔ `LEVEL_THEMES` é o único ponto não-trivial.
  Confirmar com `python -c "from game.core.levels import get_level_config; get_level_config(1)"`
  depois de cada passo.
- Validar callers depois de cada arquivo novo:
  `app.py`, `scenes/playing.py`, `systems/spawner.py`,
  `systems/level_progression_controller.py`,
  `systems/boss_fight_controller.py`, `código_teste/analyze_levels.py`.
- `código_teste/analyze_levels.py` importa `DifficultyPreset` —
  `__init__.py` precisa continuar reexportando (vem de `..difficulty`).

**Tempo estimado:** 20–30 min com validação cuidadosa entre passos.

### B. Bloco de bosses (item 6)

**Sem mudança desde o levantamento original.** Escopo previsto:

1. `cloud_archmage_boss.py` — extrair paletas de cores e constantes de
   sprite que estão embutidas na classe para o topo do módulo (ou um
   `_constants.py`). Mudança cirúrgica, baixo risco.
2. Avaliar se `stone_golem_boss.py` e `mountain_serpent_boss.py` se
   beneficiam de `BossRenderer` por boss (atualmente FSM, física e
   renderização compartilham o mesmo arquivo). Decisão depende de
   comparar com `BossParticleSystem` compartilhado já existente — se a
   renderização não tem muito código de boss, manter inline.
3. Considerar `BossBase` herança só se padrões comuns ficarem evidentes
   após avaliar os 3 bosses acima (continua adiado por falta de
   visibilidade — ver "Decisões deliberadamente adiadas").

---

## Histórico de ciclos anteriores

Relatórios `Melhorias_Código_Avaliação.txt`, `_02.txt` e `_03.txt` foram
arquivados após conclusão. Ciclos recentes encerraram com:

**Ciclo atual (em andamento):**
- **`Ship` decomposto em 3 componentes** — `ship.py` 1699 → 835 LOC.
  Extraídos `ship_renderer.py` (draw + efeitos visuais), `ship_powerups.py`
  (activate_*, timers, ticks de orbital/repulsion), `ship_movement.py`
  (move, dash, bounds). `Ship` virou fachada delegando.
- **`PlayingScene` decomposta em 4 componentes** — `playing.py` 2321 → 1904
  LOC. Extraídos `cheat_input.py` (CheatBuffer compartilhado com main_menu),
  `powerup_system.py` (dispatch de 13 powerups + process_collection),
  `gameplay_input_handler.py` (handle_event + gamepad/upgrade dispatch),
  `transition_controller.py` (FSM `TransitionPhase` + timers de fase).
- **`entity_manager.update()` reorganizado** — método principal compactado
  para ~30 linhas chamando 12 sub-métodos por domínio (formations,
  projectiles, collectibles, enemies, boss, environment, etc.).
- **`collision_physics.py` extraído** — helpers `apply_hit`,
  `apply_ship_contact`, `apply_area_damage`, `check_mask_collision`,
  `batch_query_for_projectiles` movidos para classe `CollisionPhysics`.
  `Collisions` mantém wrappers thin para preservar call sites.
- **`core/levels/` pacote criado (parcial)** — fronteira de pacote em pé
  via `_legacy.py` + `__init__.py` reexportando API. Split por domínio
  dentro do pacote deferido — ver **Pendências para o próximo ciclo**.
- **Correções pontuais validadas** (revisão de ajustes anteriores):
  - AABB do laser do Caçador (`cacador_lasers_vs_enemies`) seguia o bug
    antigo do orbital — corrigido para `min/max ± laser.w`.
  - `player_lasers_vs_boss` / `cacador_lasers_vs_boss` /
    `homing_bullets_vs_boss` adicionaram guarda `can_take_damage()` para
    não registrar boss em `hit_enemies` durante ENTERING/INTRO/TELEPORT
    (sem isso, laser ficava "trancado" e não acertava o boss vulnerável
    depois).
  - `Boss.collision_circle()` durante ENTERING retorna
    `(-1000, -1000, 0)` em vez de `(0, 0, 0)` — chamadores com AOE
    grande não tratam mais o boss como se estivesse no canto da tela.
  - `SpikeBoss.rect` adicionado como property (era só `get_rect()`); o
    fallback defensivo `if hasattr(boss, "rect") else cast(...)` foi
    removido em `player_lasers_vs_boss` e `cacador_lasers_vs_boss` — o
    protocolo `Damageable` exige `rect` e agora todos os bosses cumprem.

**Ciclo imediatamente anterior:**
- **`GameRenderer` desacoplado de `PlayingScene`** — `RenderFrame` DTO implementado
  (`game/render/render_frame.py`); `playing.py` monta `_build_render_frame()` por
  frame e passa ao renderer. Renderer não acessa mais `scene.*`.
- **`enemy_projectiles_vs_ship` aceita grid opcional** — assinatura alinhada
  com `energy_orbs_vs_ship`; filtra candidatos via id-set.
- **Import lazy de `game_events` em `collisions.py`** — movido para o topo
  do módulo; sem ciclo real.
- **`MiniShip._find_nearest_enemy` com range cap** — delega para
  `systems/targeting.py` (`find_nearest_in_list`) com `_MAX_TARGETING_RANGE_SQ`.
- **`Formation.update` migrado para swap-and-pop** — O(1) por remoção.
- **`systems/targeting.py` extraído** — `find_nearest_enemy()`,
  `find_nearest_in_list()`, `enemy_center()`; `Ship` e `MiniShip` delegam.
- **`is_boss` attribute** — substituiu heurística `"boss" in type.__name__`;
  `BossHitMixin.is_boss = True` cobre subclasses por herança; bosses
  standalone marcados explicitamente.
- **Slow-motion dispatcher polimórfico** — `update_for_game_over_slow_motion`
  reutiliza `update_in_context(ctx)` em vez da cascata `isinstance`.
- **`SpatialGrid._get_cells_for_rect` → generator** — eliminada alocação de
  `set` por chamada (deduplicação já existe em `query` via `seen`).

**Ciclos anteriores a esse:**
- **`config.py` namespace global** — substituído por dataclasses `frozen=True`
  por domínio, agregadas em `ConfigurationManager`.
- **Event Bus** — refinamentos (off/cleanup, eventos sem uso removidos,
  `LevelCleared` emitido, deduplicação de explosões, double-play do laser Magneto).
- **`PlayingScene` god object** — extraídos `BossFightController`,
  `LevelProgressionController`, `ShootingSystem`.
- **Resíduos da migração `LevelProgressionController`** — aliases e
  propriedades de compat removidos.
