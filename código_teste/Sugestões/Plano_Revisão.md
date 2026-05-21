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

**Status:** Pendente

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

**Status:** Pendente

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

**Status:** Pendente

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

**Status:** Pendente

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

**Status:** Pendente

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
| 1 | `Ship` acumula render, movimento, powerups e targeting | Crítico | Pendente |
| 2 | `PlayingScene` concentra input, powerups, cheats e transições | Crítico | Pendente |
| 3 | `levels.py` mistura dados, procedural e pipeline | Médio | Pendente |
| 4 | `collisions.py` — extrair helpers de física | Médio | Pendente |
| 5 | `entity_manager.update()` longo (~260 LOC) | Médio | Pendente |
| 6 | Bloco de bosses — constantes inline e responsabilidades | Baixo | Pendente |

---

## Histórico de ciclos anteriores

Relatórios `Melhorias_Código_Avaliação.txt`, `_02.txt` e `_03.txt` foram
arquivados após conclusão. Ciclos recentes encerraram com:

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
