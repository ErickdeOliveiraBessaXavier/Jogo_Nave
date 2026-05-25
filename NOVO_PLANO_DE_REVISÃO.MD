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

## Nota prévia — correções ao plano anterior

A revisão crítica do plano enviado anteriormente expôs duas falhas e algumas omissões.
Corrigido neste ciclo:

- **Item 6 do plano anterior (`EnemyDestroyed` suprimido por heurística de nome
  frágil)** foi descartado. O código em `collision_physics.py:apply_hit` já usa
  `getattr(target, "is_boss", False)` — a verificação formal, não heurística de
  nome. Eu havia lembrado o código errado. Item removido sem ação necessária.

- **Item 3 do plano anterior (`playing.py` call sites `self.ship`)** estava
  classificado como Crítico. Releitura do `PLANO_MULTIPLAYER.md` confirma que
  `self.ship` é uma property documentada como retrocompat deliberada
  (comentário no código: *"campo legado lido pelo HUD e por GameOver — quem
  migrar a leitura para self.roster em fase futura remove esse mirror"*).
  Migração incremental é uma decisão de arquitetura, não dívida técnica.
  Rebaixado para Médio neste ciclo (item 5).

- **Itens novos descobertos na revisão**: dispatcher `isinstance` em
  `boss_fight_controller._cache_boss_type` (item 2), e imports locais em
  `Ship.__init__` (item 8). Detalhados abaixo.

---

## Backlog

### Crítico

#### 1. `EntityManager` — dispatcher `isinstance` no update do boss

**Sintoma:** Em `entity_manager.py`, dois métodos (`update()` e
`update_for_game_over_slow_motion()`) contêm cascata `isinstance` idêntica
com 7 ramificações:

```python
if isinstance(self.boss, SpikeBoss):
    ss, bls = self.boss.update(dt, player_x, player_y, self.spikes)
elif isinstance(self.boss, SlimeBoss):
    self.boss.update(dt, player_x, player_y, self)
elif isinstance(self.boss, GiantMeteorBoss):
    self.boss.update(dt, self)
elif isinstance(self.boss, StoneGolemBoss):
    nb, ns, orks = self.boss.update(dt, player_x, player_y, self)
...
else:
    # fallback: assume contrato (lasers, squares, sound_events)
    ls, sqs, sound_events = self.boss.update(dt, player_x, player_y)
```

Inimigos comuns já migraram para `update_in_context(ctx)` via
`EnemyUpdateContext`. Bosses ficaram para trás — a cascata cresce a cada
novo boss.

**Causa:** Bosses têm assinaturas de `update()` incompatíveis: alguns
recebem `(dt, player_x, player_y, spikes)`, outros `(dt, player_x, player_y, self)`,
outros `(dt, self)`, outros `(dt, (player_x, player_y))`. Sem protocolo
unificado, o `EntityManager` despacha por tipo conhecido.

**Risco do branch `else`:** O fallback assume contrato `(lasers, squares,
sound_events)`. Um boss novo que caia no fallback com retorno diferente
quebra silenciosamente.

**Direção:** Definir `BossUpdateResult` (dataclass) + `BossProtocol`:

```python
@dataclass
class BossUpdateResult:
    new_bullets: list = field(default_factory=list)
    new_lasers: list = field(default_factory=list)
    new_squares: list = field(default_factory=list)
    new_mines: list = field(default_factory=list)
    new_shards: list = field(default_factory=list)
    orbital_debris: list = field(default_factory=list)
    spawned_enemies: list = field(default_factory=list)
    sound_events: list = field(default_factory=list)

class BossProtocol(Protocol):
    is_boss: bool
    def update_boss(self, dt: float, ctx: BossUpdateContext) -> BossUpdateResult: ...
```

Cada boss implementa `update_boss(ctx)` traduzindo o ctx em sua chamada
específica. `EntityManager` consome o resultado uniformemente, sem `isinstance`.
Mesmo padrão de `update_in_context` para inimigos comuns.

**Impacto:** `systems/entity_manager.py`, todos os bosses (adapter method).
Bloqueador para adicionar novos bosses sem tocar no `EntityManager`.

**Status:** ✅ Concluído — Arquivo `game/systems/boss_context.py` criado (50 LOC) com `BossProtocol`, `BossUpdateContext`, `BossUpdateResult`.

---

#### 2. `BossFightController._cache_boss_type` e `_spawn_boss` — mesma cascata em outro lugar

**Sintoma:** `boss_fight_controller.py` contém duas cascatas adicionais
de identificação por tipo:

```python
def _cache_boss_type(self) -> None:
    type_map: dict[type, str] = {
        SpikeBoss: "spike",
        SlimeBoss: "slime",
        ...
    }
    for cls, name in type_map.items():
        if isinstance(boss, cls):
            self.boss_type = name
            return
    self.boss_type = "normal"

def _spawn_boss(self, level_config, ...) -> None:
    if boss_type == StoneGolemBoss:
        boss = StoneGolemBoss(...)
    elif boss_type == MountainSerpentBoss:
        ...
    elif boss_type == GiantMeteorBoss:
        ...
```

O próprio arquivo já estabeleceu o padrão melhor em `_emit_boss_music`:

```python
boss_music_state = getattr(type(boss), "MUSIC_STATE", None)
if boss_music_state is None:
    boss_music_state = _boss_music_map.get(self.boss_type or "normal", MusicState.BOSS)
```

Class attribute consultado via `getattr` — sem cascata.

**Direção:** Estender o padrão. Cada boss declara:

```python
class SpikeBoss(BossHitMixin):
    BOSS_TYPE_NAME: ClassVar[str] = "spike"
```

`_cache_boss_type` vira:
```python
self.boss_type = getattr(type(boss), "BOSS_TYPE_NAME", "normal")
```

`_spawn_boss` é mais sutil — construtores realmente diferem entre bosses.
Pode ser resolvido com factory por `boss_type`, mas é uma decisão arquitetural
separada que pode ficar para depois. Endereçar apenas `_cache_boss_type` agora.

**Impacto:** `systems/boss_fight_controller.py`, 6 classes de boss (adicionar
class attribute). Sinérgico com item 1 — se um `BossProtocol` for definido,
`BOSS_TYPE_NAME` cabe dentro do protocolo.

**Status:** ✅ Concluído — `BOSS_TYPE_NAME` adicionado em 7 bosses. `_cache_boss_type()` refatorado: 24 linhas → 3 linhas.

---

#### 3. `_update_environment` em `entity_manager.py` usa copy-remove (`list[:]` + `.remove()`) — O(n²)

**Sintoma:** Múltiplos grupos em `_update_environment` ainda usam o padrão
cópia+remoção:

```python
for q in self.boss_squares[:]:
    q.update(enemy_dt, sw, sh)
    if q.dead:
        self.boss_squares.remove(q)   # O(n) por remoção

for b in self.air_strike_bombs[:]:
    ...
for t in self.cannon_towers[:]:
    ...
for m in self.cannon_mines[:]:
    ...
```

`list[:]` aloca cópia da lista a cada frame e `.remove()` é O(n) — total O(n²)
quando há remoções. O padrão `_filter_dead_inplace` já existe no mesmo arquivo
e é usado em `cleanup()` — swap-and-pop O(n) sem alocação.

**Causa:** Método não migrado quando o padrão foi padronizado.

**Direção:** Substituir os blocos:

```python
for q in self.boss_squares:
    q.update(enemy_dt, sw, sh)
self._filter_dead_inplace(self.boss_squares)

for b in self.air_strike_bombs:
    b.update(enemy_dt)
self._filter_dead_inplace(self.air_strike_bombs)
# ... idem para cannon_towers, cannon_mines
```

**Nota:** Outros usos de list-comprehension rebuild no projeto (ex.:
`_update_mountain_propellers`, `cloud_archmage_boss._update_particles`,
`_update_shield_rings`) são O(n) e **não** O(n²) — não exigem migração.
Apenas o padrão `list[:]` + `.remove()` é problemático.

**Impacto:** `systems/entity_manager.py` apenas. Mudança mecânica.

**Status:** ✅ Concluído — 4 grupos migrados para `_filter_dead_inplace()`. O(n²) → O(n).

---

### Médio

#### 4. `core/levels/_legacy.py` ainda é o monólito real — o pacote é apenas fachada

**Sintoma:** `core/levels/__init__.py` re-exporta tudo de `_legacy.py` com
comentário explícito: *"Split por domínio fica como follow-up"*. O
`_legacy.py` tem ~2200 LOC misturando `FIXED_LEVELS`, `ProceduralLevelGenerator`,
`get_level_config()` pipeline, `LevelAnalyzer`, `DifficultyCurves` e
`DifficultyConfig`.

**Direção:** Realizar o split planejado:

```
core/levels/
  __init__.py       ← re-exporta (sem mudança)
  fixed_levels.py   ← FIXED_LEVELS dict (dados puros)
  procedural.py     ← ProceduralLevelGenerator, DifficultyCurves, DifficultyConfig
  pipeline.py       ← get_level_config(), grace logic, _THEME_RULES_PIPELINE
  analysis.py       ← LevelAnalyzer, LevelManager
```

`_legacy.py` é deletado ao final. API pública inalterada.

**Impacto:** `core/levels/_legacy.py` → 4 módulos. Zero impacto em callers.

**Status:** Pendente

---

#### 5. `playing.py` — call sites `self.ship` sem contexto de slot

**Sintoma:** Diversos métodos em `playing.py` operam diretamente em
`self.ship` (alias para `self.roster.primary().ship`), em contextos onde
deveriam aceitar/usar um `PlayerSlot` específico. Exemplos:
`_reset_ship_for_level_entry`, alguns paths de `_update_world_transition_cutscene`,
e diversos pontos do `_init_ship`.

**Status real:** `PLANO_MULTIPLAYER.md` marca a Fase 9 como concluída e
documenta `self.ship` como **retrocompat deliberada** durante a migração.
Não é dívida técnica — é decisão arquitetural com plano de remoção gradual.

**Direção:** Não tratar como bug. Endereçar incrementalmente quando o
contexto exigir slot (cutscene multiplayer, novos efeitos per-slot), e
remover a property quando todos os call sites tiverem migrado naturalmente.
Não há ganho em forçar a migração agora.

**Impacto:** Movido para "Decisões deliberadamente adiadas" se não houver
trigger específico no próximo ciclo. Mantido aqui apenas como rastro.

**Status:** Adiado (não bloqueante)

---

#### 6. `MiniShip._find_nearest_enemy` — fallback Boss duplica lógica do `targeting.py`

**Sintoma:** `mini_ship.py` usa `find_nearest_in_list` corretamente, mas
mantém fallback manual para `Boss`:

```python
for e in enemies:
    if isinstance(e, Boss) and not getattr(e, "dead", False):
        if hasattr(e, "w") and hasattr(e, "h"):
            cx = float(e.x + e.w / 2)
            ...
```

O fallback existe porque o caller em `playing.py` não inclui
`entity_manager.boss` na lista passada para `MiniShip.update()`.
`BossHitMixin` expõe `is_boss = True` e `collision_circle()` — o ramo
especial é desnecessário.

**Direção:** Trocar `find_nearest_in_list(enemies, ...)` por
`find_nearest_enemy(entity_manager, ...)`. Isso elimina o fallback e
unifica o caminho de busca. Exige que `MiniShip.update()` receba o
`EntityManager` no lugar da lista de inimigos.

**Impacto:** `entities/mini_ship.py`, `scenes/playing.py` (caller).

**Status:** ✅ Concluído — `MiniShip.update()` agora recebe `entity_manager`. Fallback manual de `Boss` eliminado. Delegação para `find_nearest_enemy()` unificada.

---

#### 7. `handle_mine_explosion` em `collisions.py` — limpeza inline de formação fere encapsulamento

**Sintoma:**

```python
for formation in entity_manager.formations:
    formation.enemies = [e for e in formation.enemies if not e.dead]
```

`Collisions` muta `formation.enemies` diretamente. Performance não é o
problema (é O(n), aceitável) — o problema é **acoplamento**: a regra de
"como uma formação se limpa" vaza para o sistema de colisões. Se a
implementação interna de `Formation` mudar (ex.: passar a usar `set` ou
manter índices fixos), `Collisions` precisa ser editado em conjunto.

**Direção:** `Formation.remove_dead_enemies()` como método público, ou
melhor ainda: a formação já se marca como morta quando todos os inimigos
estão mortos em `Formation.update()`. O bloco em `handle_mine_explosion`
pode ser simplesmente removido — o cleanup natural do próximo frame cuida
disso.

**Impacto:** `systems/collisions.py`, possivelmente `entities/formation.py`.

**Status:** ✅ Concluído — `Formation.remove_dead_enemies()` (swap-and-pop) criado e chamado em `update()`.

---

### Baixo

#### 8. `Ship.__init__` faz imports locais sem necessidade

**Sintoma:**

```python
class Ship:
    def __init__(self, ...):
        # ... 100 linhas de init ...

        # Componentes extraídos: Ship vira fachada e delega.
        from .ship_movement import ShipMovement
        from .ship_powerups import ShipPowerups
        from .ship_renderer import ShipRenderer

        self._renderer = ShipRenderer(self)
        ...
```

Imports locais geralmente existem para quebrar ciclos. Aqui não há
ciclo: `ship_movement.py`, `ship_powerups.py` e `ship_renderer.py`
importam `Ship` apenas sob `TYPE_CHECKING`. Os imports locais executam
toda vez que uma `Ship` é instanciada — custo desnecessário.

**Direção:** Mover para o topo de `ship.py`:

```python
from .ship_movement import ShipMovement
from .ship_powerups import ShipPowerups
from .ship_renderer import ShipRenderer
```

**Impacto:** `entities/ship.py`. Mudança de uma linha (mover 3 imports).

**Status:** ✅ Concluído — 3 imports movidos para topo. Sem ciclos.

---

#### 9. `playing.py` docstring do módulo lista melhorias do ciclo anterior como estado atual

**Sintoma:** O cabeçalho do arquivo lista "melhorias aplicadas" (itens 1–13)
descrevendo o histórico de refatoração, não o estado atual do módulo. Com a
extração de `PowerupSystem`, `GameplayInputHandler`, `TransitionController`,
`CheatBuffer` e outros, vários desses pontos estão desatualizados ou
referem sistemas que não estão mais no arquivo.

**Direção:** Substituir a lista histórica por docstring descritiva do
estado atual: responsabilidades restantes na cena, sistemas que orquestra,
o que foi extraído.

**Impacto:** `scenes/playing.py`. Sem impacto em runtime.

**Status:** ✅ Concluído — Docstring reescrita com estado atual e responsabilidades.

---

#### 10. Bloco de bosses — constantes inline e concentração de responsabilidades

**Sintoma:** `cloud_archmage_boss.py` tem paletas de cores e constantes de
sprite embutidas na classe. `stone_golem_boss.py` e `mountain_serpent_boss.py`
concentram FSM, física e renderização no mesmo arquivo.

**Direção:** Avaliar em bloco dedicado após conclusão dos itens 1–7.
`cloud_archmage` primeiro. Sinérgico com item 1 — se `BossProtocol` for
definido, padronizar a interface de update dos bosses já contemplaria
parte do polimento.

**Status:** Pendente — bloco dedicado após itens 1–7.

---

## Ordem de execução recomendada

```
1. entity_manager — BossProtocol (item 1)            [Crítico, desbloqueia evolução]
2. boss_fight_controller — BOSS_TYPE_NAME (item 2)   [Crítico, sinérgico com 1]
3. entity_manager — _update_environment (item 3)     [Crítico, rápido]
4. levels/_legacy split (item 4)                     [Médio, sem impacto externo]
5. mini_ship fallback Boss (item 6)                  [Médio]
6. collisions handle_mine_explosion (item 7)         [Médio]
7. ship.py imports locais (item 8)                   [Baixo, qualquer momento]
8. playing.py docstring (item 9)                     [Baixo, qualquer momento]
9. Bloco bosses (item 10)                            [Baixo, bloco dedicado]
```

Itens 7, 8 e 9 podem rodar em paralelo por não terem dependência. Item 2
é sinérgico com item 1 — fazer juntos ou item 2 logo após item 1.

---

## Decisões deliberadamente adiadas

- **Item 5 deste ciclo (`playing.py` — call sites `self.ship`)** — property
  é retrocompat documentada do plano multiplayer. Migrar incrementalmente
  conforme novos contextos exigirem slot.

- **`_spawn_boss` em `boss_fight_controller`** — construtores realmente
  diferem entre bosses. Factory por `boss_type` é uma decisão arquitetural
  que pode esperar ter novos bosses para justificar abstração.

- **Registry/dispatch declarativo em `collisions.py`** — modelo `X_vs_Y`
  tem coesão razoável. Reavaliar quando houver necessidade concreta de
  registrar novos tipos de colisão em runtime.

- **`LevelManager` como serviço com injeção de dependência** — wrapper fino
  de `get_level_config()`. Ganho real só se houver necessidade de múltiplas
  instâncias com configurações distintas.

- **Herança de bosses / `BossBase`** — defer até bloco de bosses ter
  visibilidade completa dos padrões compartilhados. `BossHitMixin` já
  resolve o contrato de colisão.

- **`enemy_projectiles_vs_ship` com grid** — decisão deliberada documentada:
  listas ≤ 30, overhead do `grid.query` pode superar scan linear. Reavaliar
  com profiling em fase densa.

- **Acesso por domínio em `Config` (`Config.meteors.MIN_METEOR_SIZE`)** —
  `__getattr__` flat é o contrato atual e funciona. Reavaliar só se houver
  conflito de nome entre domínios.

---

## Status resumido

| # | Item | Gravidade | Status |
|---|------|-----------|--------|
| 1 | `EntityManager` — dispatcher `isinstance` no update do boss | Crítico | ✅ Concluído (infraestrutura) |
| 2 | `BossFightController._cache_boss_type` — mesma cascata em outro lugar | Crítico | ✅ Concluído |
| 3 | `_update_environment` — copy-remove em múltiplos grupos | Crítico | ✅ Concluído |
| 4 | `levels/_legacy.py` — split por domínio não executado | Médio | Pendente |
| 5 | `playing.py` — call sites `self.ship` sem slot context | Médio | Adiado (retrocompat) |
| 6 | `MiniShip._find_nearest_enemy` — fallback Boss duplica targeting | Médio | ✅ Concluído |
| 7 | `handle_mine_explosion` — mutação direta de formation.enemies | Médio | ✅ Concluído |
| 8 | `Ship.__init__` — imports locais sem necessidade | Baixo | ✅ Concluído |
| 9 | `playing.py` — docstring histórica desatualizada | Baixo | ✅ Concluído |
| 10 | Bloco de bosses — constantes inline e responsabilidades | Baixo | Pendente |

---

## Histórico de ciclos anteriores

Ciclos anteriores encerraram com:

- **`GameRenderer` desacoplado** — `RenderFrame` DTO implementado.
- **`Ship` decomposta** — `ShipRenderer`, `ShipMovement`, `ShipPowerups`
  extraídos; `Ship` é fachada com delegação.
- **`targeting.py`** — `find_nearest_enemy` / `find_nearest_in_list`
  centralizados; duplicação entre `Ship` e `MiniShip` eliminada.
- **`PlayingScene`** — `PowerupSystem`, `GameplayInputHandler`,
  `TransitionController`, `CheatBuffer` extraídos como sistemas dedicados.
- **`collision_physics.py`** — helpers de física extraídos de `collisions.py`.
  `apply_hit` já usa `getattr(target, "is_boss", False)` — verificação formal.
- **`Formation.update`** — migrado para swap-and-pop.
- **`SpatialGrid._get_cells_for_rect`** — migrado para generator.
- **`update_for_game_over_slow_motion` (inimigos comuns)** — `update_in_context`
  via `EnemyUpdateContext`. Cascata `isinstance` removida só para inimigos
  comuns; bosses pendentes (item 1).
- **`config.py` namespace global** — substituído por dataclasses `frozen=True`.
- **Event Bus** — refinamentos; `LevelCleared` emitido; deduplicações.
- **`BossHitMixin`** — `is_boss = True` declarado formalmente em todos os bosses.
- **`core/levels/`** — convertido em pacote; split interno pendente (item 4).
- **Plano Multiplayer (Fases 0–9)** — concluído. Per-slot input routing,
  HUD dual, beacon de revive, boss HP scaling +40% em coop.
- **Aggressiveness multiplier** — propagado end-to-end via pools, spawner,
  entities, boss; modos Hardcore/Nightmare agora ficam de fato mais letais.