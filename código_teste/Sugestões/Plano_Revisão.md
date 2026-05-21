# Plano de Revisão — Space Shooter (Ciclo Atual)

Itens levantados após análise do código de produção (`game/`). Cada item foi
classificado pela gravidade definida no CLAUDE.md e acompanha causa, impacto
técnico e direção concreta de melhoria.

---

## Escopo

Avaliação focada em `game/systems/`, `game/entities/`, `game/render/` e
`game/scenes/playing.py`. Infraestrutura de build/scripts fora do escopo.

---

## Critérios de gravidade

- **Crítico** — viola princípio do CLAUDE.md (coupling, side-effects em render,
  global state), causa bug observável, ou bloqueia evolução de outra área.
- **Médio** — não bloqueia, mas degrada legibilidade/testabilidade ou fere
  composição/extensão.
- **Baixo** — polimento, nomenclatura, remoção de comentário redundante.

---

## Backlog

### Crítico

#### 1. `GameRenderer` acessa atributos internos de `PlayingScene` diretamente

**Sintoma:** `game_renderer.py` lê `scene.last_dt`, `scene.state`,
`scene.screen_shake_timer`, `scene.screen_shake_intensity`,
`scene.boss_controller.warning_timer`, `scene.start_fade_active`,
`scene.start_fade_alpha`, `scene.preparation_time_left`, `scene.show_fps`,
`scene.show_enemy_hitboxes`, `scene.score`, `scene.lives`,
`scene.total_enemies_destroyed`, `scene.score_multiplier_active` e outros —
praticamente qualquer variável de estado que a cena possui.

**Causa:** O renderer foi extraído da cena para separar responsabilidades, mas
continua acoplado ao contrato interno de `PlayingScene` em vez de a uma
interface de dados explícita. Qualquer renomeação de atributo na cena quebra o
renderer silenciosamente.

**Direção:** Definir um dataclass `RenderFrame` (ou similar) que a cena monta
a cada frame e passa ao renderer. O renderer passa a depender desse DTO, não
da cena.

```python
# Antes (renderer.py)
dt = scene.last_dt
if scene.screen_shake_timer <= 0:
    ...

# Depois
@dataclass
class RenderFrame:
    dt: float
    shake_timer: float
    shake_intensity: int
    state: GameState
    score: int
    lives: int
    ...

# playing.py monta e passa
frame = self._build_render_frame()
self.game_renderer.render(frame, surface)
```

**Impacto:** `game_renderer.py`, `playing.py`. Isola o contrato de renderização
e torna `PlayingScene` refatorável sem risco de regressão silenciosa no render.

**Status:** Concluído. Novo módulo `game/render/render_frame.py` com dataclass
frozen de 25 campos (scalars + refs a sistemas estáveis: ship, entity_manager,
boss_controller). `GameRenderer.render(frame, surface)` substitui
`render(scene, surface)`; helpers internos (`_compute_shake_offset`,
`_render_upgrades_hud`) também consomem o DTO. `PlayingScene._build_render_frame()`
monta o snapshot por frame. Cobertura verificada: 25/25 campos declarados são
lidos; zero refs residuais a `scene.*` no renderer.

---

#### 2. `_apply_hit` em `Collisions` faz import lazy dentro de hot path

**Sintoma:** Em `collisions.py`, `_apply_hit` e `_apply_ship_contact`
executam `from ..events import game_events as events` dentro do corpo do
método, chamado centenas de vezes por frame (uma vez por projétil × inimigo).

**Causa:** Import foi inserido para resolver referência circular, mas não foi
movido para o nível de módulo ou resolvido pela raiz (re-arquitetura de imports).

**Direção:** Mover o import para o nível de módulo com `TYPE_CHECKING` guard
onde necessário, ou centralizar os tipos de evento num módulo sem dependências
de runtime pesadas.

```python
# Antes (dentro de _apply_hit, chamado todo frame)
from ..events import game_events as events
self._event_bus.emit(events.EnemyDestroyed(...))

# Depois (topo de collisions.py)
from ..events import game_events as events   # import único, em módulo
```

**Impacto:** `systems/collisions.py`. Elimina overhead de resolução de módulo
no hot path de colisão sem alterar comportamento.

**Status:** Concluído

---

#### 3. `enemy_projectiles_vs_ship` ignora a spatial grid já existente

**Sintoma:** O método em `collisions.py` itera a lista inteira de projéteis
de inimigos com loop linear, com comentário justificando que "listas são
pequenas". A `entity_manager` já constrói `enemy_projectile_grid` a cada
frame inserindo `alien_bullets`, `serpent_bullets` e `energy_orbs`.

**Causa:** O método não recebe a grid como parâmetro e o chamador
(`playing.py`) não a passa.

**Direção:** Aceitar a grid como parâmetro opcional (mantém compatibilidade)
e usá-la quando disponível, o que o método `energy_orbs_vs_ship` já faz
corretamente — padronizar.

```python
# Antes
def enemy_projectiles_vs_ship(self, ship, projectiles):
    for p in projectiles:  # O(n) sempre
        ...

# Depois
def enemy_projectiles_vs_ship(self, ship, projectiles, grid=None):
    if grid is not None:
        candidates = grid.query(ship_rect.x - pad, ...)
    else:
        candidates = projectiles
    for p in candidates:
        ...
```

**Impacto:** `systems/collisions.py`, `scenes/playing.py` (passar a grid na
chamada). Reduz colisões redundantes em fases com muitos projéteis de inimigos.

**Status:** Concluído. Assinatura agora espelha `energy_orbs_vs_ship`: grid
opcional, default mantém o comportamento antigo. Como o `enemy_projectile_grid`
mistura `alien_bullets`, `serpent_bullets` e `energy_orbs`, a filtragem por
pertencimento à lista usa id-set (`{id(p) for p in projectiles}`). Call sites
em `playing.py` passam `em.enemy_projectile_grid`. Aplicado como consistência
de API — ganho de perf depende do tamanho da lista (irrelevante em fases
leves, melhora quando há muitos projéteis longe da nave).

---

### Médio

#### 4. `MiniShip._find_nearest_enemy` faz O(n) scan sem limit de range

**Sintoma:** `mini_ship.py` itera todos os inimigos passados para encontrar o
mais próximo, sem raio de busca. Em fases com muitos inimigos e dois MiniShips
ativos, isso são dois scans completos por cooldown de tiro (≈0.75 s).

**Causa:** A lista de inimigos é passada inteira pelo chamador sem filtro
prévio. Não há uso da spatial grid já disponível no `EntityManager`.

**Direção:** Adicionar raio de busca máximo (ex.: 400 px) e fazer early-exit.
Se o `EntityManager` for acessível no contexto, substituir pelo grid query.

```python
MAX_TARGETING_RANGE_SQ = 400 ** 2

def _find_nearest_enemy(self, enemies):
    nearest = None
    min_d = MAX_TARGETING_RANGE_SQ   # só alvos dentro do range
    for e in enemies:
        ...
        if dist_sq < min_d:
            min_d = dist_sq
            nearest = e
    return nearest
```

**Impacto:** `entities/mini_ship.py`. Sem mudança de interface pública.

**Status:** Concluído (junto com #6 — MiniShip delega para `find_nearest_in_list`
com `max_range_sq=400²`)

---

#### 5. `Formation.update` remove inimigos de `self.enemies` durante iteração com `self.enemies[:]`

**Sintoma:** Em `formation.py`, `update()` itera `self.enemies[:]` e chama
`self.enemies.remove(enemy)` para inimigos mortos. Isso cria uma cópia a cada
frame por formação ativa e realiza busca linear O(n) no remove.

**Causa:** Padrão copy-then-remove, amplamente usado no codebase em outros
pontos que já foram migrados para `_filter_dead_inplace` no `EntityManager`.

**Direção:** Substituir pelo padrão swap-and-pop já existente no projeto, ou
acumular índices mortos e remover ao fim do loop.

```python
# Antes
for enemy in self.enemies[:]:
    if enemy.dead:
        self.enemies.remove(enemy)  # O(n) por remoção
        continue
    ...

# Depois
i = 0
while i < len(self.enemies):
    enemy = self.enemies[i]
    if enemy.dead:
        self.enemies[i] = self.enemies[-1]
        self.enemies.pop()
    else:
        enemy.update(dt)
        ...
        i += 1
```

**Impacto:** `entities/formation.py`. Risco baixo — mudança local.

**Status:** Concluído

---

#### 6. `Ship._find_nearest_enemy` duplica lógica já existente em `MiniShip._find_nearest_enemy`

**Sintoma:** `ship.py` e `mini_ship.py` contêm implementações separadas de
"achar o inimigo mais próximo de uma posição", com pequenas variações de
interface mas lógica idêntica (dist_sq, skip dead, verificar boss).

**Causa:** A funcionalidade foi adicionada independentemente nos dois arquivos
sem extração para utilitário compartilhado.

**Direção:** Extrair para `systems/targeting.py` (ou similar) uma função pura:

```python
def find_nearest_enemy(
    from_x: float,
    from_y: float,
    entity_manager: EntityManager,
    max_range_sq: float = float("inf"),
) -> Any | None: ...
```

`Ship` e `MiniShip` delegam para essa função. `MiniShip` passa
`MAX_TARGETING_RANGE_SQ` como `max_range_sq`.

**Impacto:** `entities/ship.py`, `entities/mini_ship.py`. Novo arquivo
`systems/targeting.py`. Sem mudança de comportamento.

**Status:** Concluído

---

#### 7. `Collisions._apply_hit` emite `EnemyDestroyed` com heurística de nome frágil

**Sintoma:** O evento `EnemyDestroyed` é suprimido para bosses com:
```python
if "boss" not in type(target).__name__.lower()
```
Isso é uma heurística baseada em convenção de nomenclatura. Uma classe
`ExplosiveMine` que internamente seja um "mini-boss" mas não tenha "boss" no
nome emite o evento indevidamente. Uma classe de boss fora da convenção
(ex.: `Leviathan`) suprime o evento incorretamente.

**Causa:** Sem interface formal que declare se um inimigo é um boss ou não.

**Direção:** Adicionar atributo de classe ou propriedade ao protocolo `Enemy`:

```python
class Enemy(Protocol):
    is_boss: bool   # ou property
    ...
```

E substituir a heurística:
```python
if result.killed and not getattr(target, "is_boss", False):
    self._event_bus.emit(events.EnemyDestroyed(...))
```

**Impacto:** `systems/collisions.py`, `systems/collision_protocols.py`. Todas
as classes de boss devem declarar `is_boss = True`.

**Status:** Concluído. `BossHitMixin.is_boss = True` cobre `Boss` e `SpikeBoss`
por herança; classes standalone (`SlimeBoss`, `GiantMeteorBoss`,
`CloudArchmageBoss`, `MountainSerpentBoss`, `StoneGolemBoss`) ganharam
declaração explícita. `SquareMinionBoss` **não** recebeu `is_boss=True` — apesar
do nome, é inimigo comum spawnável (a heurística antiga o classificava
incorretamente; comportamento agora é o correto: emite `EnemyDestroyed`).

---

#### 8. `update_for_game_over_slow_motion` em `EntityManager` usa `isinstance` em cascata como dispatcher

**Sintoma:** O método itera uma lista combinada de todas as entidades e decide
qual overload de `update()` chamar com `isinstance(e, EyeEnemy)`,
`isinstance(e, GuidedMeteor)`, `isinstance(e, ElementalRobot)`, etc.

**Causa:** Método alternativo de slow-motion adicionado como patch sem
aproveitar o protocolo de update já definido nas entidades.

**Direção:** Cada entidade deve ter um método `update_slow(dt)` ou o
`update()` regular deve aceitar o dt reduzido uniformemente. O dispatcher
some e o método fica:

```python
def update_for_game_over_slow_motion(self, dt, player_x, player_y):
    slow_dt = dt * SLOW_FACTOR
    for g in self._all_entity_groups():
        for e in g:
            e.update(slow_dt)   # cada entidade controla seu próprio ritmo
```

**Impacto:** `systems/entity_manager.py`. Risco médio — requer que as
entidades com assinatura diferente de `update` sejam adaptadas.

**Status:** Concluído. Reutilizado o pattern `update_in_context(ctx)` já
existente para o regular `update()`. Slow-motion constrói um `EnemyUpdateContext`
com `sdt == dt` (sem EMP/ice) e os inimigos heterogêneos viram o dispatch via
método polimórfico. `MiniShip` mantém chamada explícita (precisa de listas
vazias de alvos/balas durante death sequence). Demais grupos têm assinatura
`update(dt)` uniforme.

---

### Baixo

#### 9. `SpatialGrid._get_cells_for_rect` aloca `set` a cada chamada

**Sintoma:** Toda inserção e query cria um `set` de coordenadas de célula via
comprehension. Em fases densas, isso é chamado centenas de vezes por frame.

**Causa:** Implementação direta sem caching.

**Direção:** Retornar um generator ou acumular em lista local ao invés de set.
Alternativamente, aceitar duplicatas no resultado e deduplica na query (onde
`seen` já existe).

```python
# Simples: trocar set por itertools.product
def _get_cells_for_rect(self, x, y, w, h):
    left = int(x // self.cell_size)
    right = int((x + w) // self.cell_size)
    top = int(y // self.cell_size)
    bottom = int((y + h) // self.cell_size)
    for cx in range(left, right + 1):
        for cy in range(top, bottom + 1):
            yield (cx, cy)
```

As chamadas em `insert` e `query` iteram diretamente sem materializar o set.

**Impacto:** `core/spatial_grid.py`. Mudança segura e localizada.

**Status:** Concluído

---

#### 10. `AutoPlay` em `main_menu.py` usa `Config.` com import legado

**Reavaliação:** A premissa do item está incorreta. `main_menu.py:11` já
importa `from ..core.config import config as Config`, que é o
`ConfigurationManager` introduzido no ciclo anterior. Os acessos
`Config.MIN_METEOR_SIZE`, `Config.MAX_METEOR_SIZE`, `Config.SCREEN_WIDTH`
funcionam via `ConfigurationManager.__getattr__` percorrendo os domínios — é
o comportamento desenhado, não um vestígio de import legado.

Se o objetivo for forçar acesso por domínio (`Config.meteors.MIN_METEOR_SIZE`,
`Config.display.SCREEN_WIDTH`), isso é uma decisão arquitetural global que
exigiria migrar todos os call sites do projeto, não apenas `main_menu.py`. Fica
como item para um eventual ciclo futuro de "limpeza do flat namespace".

**Status:** Descartado (premissa incorreta)

---

## Decisões deliberadamente adiadas

- **`RenderFrame` DTO completo** — o item 1 pode ser implementado
  incrementalmente: começar pelos atributos mais acessados (shake, fade, state)
  e expandir. Não bloquear o item esperando cobertura 100%.

- **Refatoração de `update_for_game_over_slow_motion`** — o item 8 requer que
  entidades com assinatura de `update` incompatível (ex.: `GuidedMeteor`,
  `ElementalRobot`) recebam adaptadores. Pode ser feito separado do restante
  do ciclo sem bloquear.

---

## Status resumido

| # | Item | Gravidade | Status |
|---|------|-----------|--------|
| 1 | `GameRenderer` acessa estado interno de `PlayingScene` diretamente | Crítico | Concluído |
| 2 | Import lazy de `game_events` dentro do hot path de colisão | Crítico | Concluído |
| 3 | `enemy_projectiles_vs_ship` não usa `enemy_projectile_grid` | Crítico | Concluído |
| 4 | `MiniShip._find_nearest_enemy` O(n) sem range limit | Médio | Concluído |
| 5 | `Formation.update` copy-remove pattern ainda não migrado | Médio | Concluído |
| 6 | Lógica de targeting duplicada em `Ship` e `MiniShip` | Médio | Concluído |
| 7 | Supressão de `EnemyDestroyed` por heurística de nome frágil | Médio | Concluído |
| 8 | `update_for_game_over_slow_motion` usa `isinstance` como dispatcher | Médio | Concluído |
| 9 | `SpatialGrid._get_cells_for_rect` aloca `set` por chamada | Baixo | Concluído |
| 10 | `AutoPlay` usa import legado de `Config` | Baixo | Descartado |

---

## Histórico de ciclos anteriores

Os relatórios `Melhorias_Código_Avaliação.txt`, `_02.txt` e `_03.txt` foram
arquivados após conclusão das ações deles. Resumo do que ficou:

- **PlayingScene god object** — extraídos `BossFightController`,
  `LevelProgressionController`, `ShootingSystem`. Cena reduzida e domínios
  isolados por sua coerência interna.
- **`config.py` namespace global** — substituído por dataclasses `frozen=True`
  por domínio (`DisplayConfig`, `GameplayConfig`, `MeteorConfig`, `AlienConfig`,
  `PowerUpConfig`, `BossConfig` + variantes, `FormationConfig`,
  `VisualEffectConfig`, `ScoringConfig`, `ParticleConfig`), agregadas em
  `ConfigurationManager`.
- **Event Bus** — refinamentos (off/cleanup, eventos sem uso removidos,
  `LevelCleared` emitido, deduplicação de explosões, double-play do laser
  Magneto).
- **Resíduos da migração `LevelProgressionController`** — `_base_score_multiplier`
  alias e propriedades de compat removidos; setter `level_config` removido.