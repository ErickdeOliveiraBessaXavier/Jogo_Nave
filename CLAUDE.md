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

## Diretrizes Pylance / Type Safety

Regras consultadas ao receber um warning do Pylance. Cada uma tem **trigger**
(quando aparece), **árvore de decisão** (ordem de preferência) e exemplo
**❌ antes / ✅ depois**. Antes de "só renomear" o warning, percorra a árvore.

---

### 1. `reportPrivateUsage` em facades com componentes extraídos

**Quando acontece:** Um componente irmão (`ShipPowerups`, `PowerupSystem`,
`GameplayInputHandler`, etc.) acessa `_attr` ou `_method` de outro objeto
(`Ship`, `PlayingScene`, etc.).

**Como decidir** (nesta ordem):

1. **Remover** se for wrapper morto (delegator de 1 linha).
2. **Mover** ownership se o atributo logicamente pertence ao componente:
   - Lookup tables Config-derivadas → para o componente.
   - Estado do domínio do componente (ex.: `mouse_history` em movimento) →
     para o `__init__` do componente.
3. **Renomear** (drop do `_`) somente quando o atributo é API legítima
   facade↔componente. O `_` original era engano — não é privado de
   verdade, é "package-private".

**Anti-padrão:** suprimir o warning via config do pyright sem analisar
ownership — esconde o sinal útil que aponta fronteira borrada.

```python
# ❌ Antes (wrapper morto na Ship)
class Ship:
    def _find_nearest_enemy(self, x, y, em):
        from ..systems.targeting import find_nearest_enemy
        return find_nearest_enemy(x, y, em)

# Componente:
nearest = ship._find_nearest_enemy(ball_x, ball_y, em)  # ⚠ private access

# ✅ Depois (remoção)
# Ship sem o wrapper. Componente importa direto:
from ..systems.targeting import find_nearest_enemy
nearest = find_nearest_enemy(ball_x, ball_y, em)
```

---

### 2. `reportConstantRedefinition` em atributos de instância

**Quando acontece:** `self.X = ...` ou `self._X = ...` com nome 100% maiúsculo.
Pylance trata uppercase como constante por convenção PEP 8.

**Como decidir:** sempre renomear para nome semântico em snake_case
(`self.scale`, `self._scale`), nunca uma letra avulsa. Letras avulsas
geralmente vêm de gambiarra local que vazou para atributo.

```python
# ❌ Antes
self.S = S          # ⚠ "S" parece constante de classe
self._S = S         # mesma coisa

# ✅ Depois
self.scale = S      # nome semântico, lowercase
self._scale = S
```

---

### 3. `reportIncompatibleMethodOverride` / `reportIncompatibleVariableOverride`

**Quando acontece:**
- Subclasse omite parâmetro da assinatura da base (LSP).
- Subclasse troca `attr: T` por `@property def attr() -> T`.

**Como decidir:**
- **Método**: aceitar todos os parâmetros da base, mesmo que só os repasse
  com default (`super().reset(..., aggressiveness_multiplier=mult)`).
- **Atributo vs property**: se as subclasses precisam ser property
  (computado), declarar como `@property` abstrata no Mixin/base e levantar
  `NotImplementedError`. Nunca declarar como atributo simples se vai ser
  property nas filhas.

```python
# ❌ Antes (mixin com atributo, subclasse com property)
class EnemyHitMixin:
    rect: pygame.Rect

class StoneSentry(EnemyHitMixin):
    @property
    def rect(self) -> pygame.Rect:  # ⚠ incompatible override
        return pygame.Rect(...)

# ✅ Depois
class EnemyHitMixin:
    @property
    def rect(self) -> pygame.Rect:
        raise NotImplementedError
```

---

### 4. `reportUnknownVariableType` em `field(default_factory=list)`

**Quando acontece:** Dataclass field com `default_factory=list` (sem
parâmetro de tipo). Pylance vê `list[Unknown]` e perde a info do tipo
declarado.

**Como decidir:** use `default_factory=list[T]` (PEP 585, Python 3.9+).
O generics subscritável funciona como callable em runtime.

```python
# ❌ Antes
_slots: List[PlayerSlot] = field(default_factory=list)  # ⚠ Unknown

# ✅ Depois
_slots: List[PlayerSlot] = field(default_factory=list[PlayerSlot])
```

---

### 5. `reportUnusedImport`

**Quando acontece:** Import órfão após remoção do código que o usava.

**Como decidir:** após qualquer remoção/refactor que tire o uso de um
símbolo, varrer os imports do arquivo. Se virou warning, deletar — NÃO
deixar "por garantia". Se outro arquivo precisa do símbolo, ele que importe.

```python
# ❌ Antes (pygame era usado no fallback que foi removido)
import pygame                 # ⚠ não acessado
from .config import config as Config

class BlinkDashUpgrade(...):
    def on_activate_effect(self, ctx):
        ship.activate_dash(...)  # não usa pygame

# ✅ Depois
from .config import config as Config
```

---

### 6. Anti-padrão: `setattr`/`getattr`/`hasattr` defensivos mortos

**Quando acontece:** Código usa `setattr(obj, "attr", x)` ou
`hasattr(obj, "attr")` quando o atributo é garantido pela classe.
Geralmente herdado de código exploratório / defensive copy-paste.

**Como decidir:**
- `setattr(ship, "speed", x)` → `ship.speed = x` (acesso direto).
- `getattr(ship, "speed", default)` → `ship.speed` se sempre existe;
  manter apenas em fronteira (input externo, plugin opcional).
- `if hasattr(ship, "metodo"):` → remover o `if` se `metodo` é parte do
  contrato público da classe. Manter apenas para duck typing real.
- Bloco `try/except (AttributeError, TypeError): pass` ao redor de chamada
  conhecida → silencia bugs. Remover ou tratar especificamente.

```python
# ❌ Antes
if hasattr(ship, "activate_dash"):
    ship.activate_dash(duration)
else:
    setattr(ship, "dash_timer", duration)
    if not hasattr(ship, "original_speed"):
        setattr(ship, "original_speed", getattr(ship, "speed", 300))

# ✅ Depois (Ship sempre tem activate_dash e original_speed)
ship.activate_dash(duration)
```

---

### 7. Armadilha de `replace_all` com nomes que se sobrepõem

**Quando acontece:** Rename em batch com `replace_all` quando o nome
curto é substring do longo. Ex.: `_upgrade_select_mode` vive dentro de
`_toggle_upgrade_select_mode`.

**Como decidir:**

1. **Listar todos** os nomes a renomear e identificar substring overlaps.
2. **Renomear os longos primeiro** — mas atenção: depois de renomear
   `_toggle_upgrade_select_mode` → `toggle_upgrade_select_mode`, o curto
   `_upgrade_select_mode` ainda casa como substring de
   `toggle_upgrade_select_mode` e vai gerar `toggleupgrade_select_mode` (!).
3. **Validar com `hasattr(Cls, 'novo_nome')`** depois do batch. Se False,
   buscar `novonome` (sem underscore intermediário) no arquivo.

```python
# Ordem correta + validação
# 1. _toggle_upgrade_select_mode → toggle_upgrade_select_mode
# 2. _activate_stored_powerup_for → activate_stored_powerup_for
# 3. _upgrade_select_mode → upgrade_select_mode  ⚠ pode quebrar #1!
# 4. python -c "assert hasattr(Cls, 'toggle_upgrade_select_mode')"
```

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

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

**Status:** Resolvido (verificado 2026-05-24)

---

#### 10. `AutoPlay` em `main_menu.py` usa `Config.` com import legado

**Sintoma:** `main_menu.py` importa e usa `Config.MIN_METEOR_SIZE`,
`Config.MAX_METEOR_SIZE`, `Config.SCREEN_WIDTH` diretamente sem passar pelo
`ConfigurationManager` introduzido no ciclo anterior.

**Causa:** `AutoPlay` foi escrito antes ou em paralelo à migração e não foi
atualizado.

**Direção:** Substituir os acessos diretos pelo proxy padrão do projeto:

```python
from ..core.config import config as Config
```

Verificar se este import já existe no topo do arquivo ou se ainda usa o import
legado.

**Impacto:** `scenes/main_menu.py`. Sem impacto em runtime, mas mantém
consistência com o padrão estabelecido.

**Status:** Resolvido (verificado 2026-05-24)

---

## Decisões deliberadamente adiadas

- **`RenderFrame` DTO completo** — concluído: `game_renderer.py` consome um
  `RenderFrame` (ver `render/render_frame.py`) e não acessa `PlayingScene`.

- **Refatoração de `update_for_game_over_slow_motion`** — concluído: o dispatch
  dos inimigos virou polimórfico via `update_in_context(ctx)`, sem cascata de
  `isinstance`.

---

## Status resumido

| # | Item | Gravidade | Status |
|---|------|-----------|--------|
| 1 | `GameRenderer` acessa estado interno de `PlayingScene` diretamente | Crítico | Resolvido |
| 2 | Import lazy de `game_events` dentro do hot path de colisão | Crítico | Resolvido |
| 3 | `enemy_projectiles_vs_ship` não usa `enemy_projectile_grid` | Crítico | Resolvido |
| 4 | `MiniShip._find_nearest_enemy` O(n) sem range limit | Médio | Resolvido |
| 5 | `Formation.update` copy-remove pattern ainda não migrado | Médio | Resolvido |
| 6 | Lógica de targeting duplicada em `Ship` e `MiniShip` | Médio | Resolvido |
| 7 | Supressão de `EnemyDestroyed` por heurística de nome frágil | Médio | Resolvido |
| 8 | `update_for_game_over_slow_motion` usa `isinstance` como dispatcher | Médio | Resolvido |
| 9 | `SpatialGrid._get_cells_for_rect` aloca `set` por chamada | Baixo | Resolvido |
| 10 | `AutoPlay` usa import legado de `Config` | Baixo | Resolvido |

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

### Ciclo 2026-05-24

- **Backlog deste plano (itens 1–10) verificado e concluído.** Todos os 10
  itens já estavam implementados no código (RenderFrame DTO, remoção do import
  lazy de eventos, grid no `enemy_projectiles_vs_ship`, range no MiniShip,
  swap-and-pop na Formation, `targeting.find_nearest_enemy` compartilhado,
  atributo `is_boss`, dispatch via `update_in_context`, generator no
  `SpatialGrid`, proxy `Config` no AutoPlay). Tabela atualizada para Resolvido.
- **Correções de bugs (fora do backlog), aplicadas neste ciclo:**
  - Chain Shot do P2 não ativava (gate de chain por bala via `owner_ship` em
    `projectiles_vs_enemies`, não mais pela nave do P1).
  - Blocos laterais da Serpente não voltavam após a vulnerabilidade
    (`SerpentBlock.should_remove` restaurado: corrente principal nunca é
    removida; fragmentos sim).
  - Cannon Towers: voltou a invocar 2 torres nas laterais inferiores (15%/85%),
    não 1 na posição do jogador.
  - Estoque/Hangar: scroll por controle (auto-scroll de borda + D-pad/setas).
  - Crash do Mountain Geode (`random.randint` com float — `shake_intensity`
    coagido a int).
  - Drift do cursor no arranque do gamepad (RS/LT neutralizados até
    `layout_detected`).
  - `LevelConfig` virou dataclass de verdade (`dataclasses.replace` quebrava no
    ajuste dinâmico de dificuldade e no saneamento de formations).
  - EMP voltou a desacelerar (`emp_slow_factor` setado pelo upgrade; `_emp_state`
    devolve o fator mesmo inativo, restaurando também o linger).