# CLAUDE.md — Diretrizes do Projeto Space Shooter

Documento de **princípios e convenções** do projeto. Não é arquivo de
planejamento — itens de revisão, backlog e status vivem em
`NOVO_PLANO_DE_REVISÃO.MD` e nos planos temáticos (`PLANO_MULTIPLAYER.md`,
`PLANO_BALANCEAMENTO.md`, etc).

Estas regras refletem padrões que o código **já estabeleceu**. Código novo
deve segui-los; código existente que os viola é candidato a revisão.

---

## §1 — Acoplamento e fronteiras

**Sistemas se comunicam por contratos explícitos, não por acesso a estado interno.**

- Um sistema não lê atributos privados (`_x`) de outro objeto. Acesso a
  privado dentro da própria classe é legítimo; entre objetos irmãos é
  fronteira borrada (o `reportPrivateUsage` do type checker sinaliza isso).
- A `PlayingScene` passa dados aos sistemas via DTO ou parâmetros, não
  expondo `self` para leitura difusa. Padrão de referência: `RenderFrame`
  — a cena monta o snapshot, o `GameRenderer` consome o DTO sem tocar na cena.
- Controladores extraídos da cena (`BossFightController`,
  `LevelProgressionController`) **não referenciam `PlayingScene`**. Comunicam
  por callbacks, retornos tipados (enums de status) e atributos públicos
  lidos pela cena.
- Antes de extrair um `*Renderer` de uma classe, verifique se o render lê
  estado **público e limpo** (caso `ShipRenderer`) ou estado **privado de
  domínio** acoplado ao FSM (caso bosses). No segundo, extrair converte
  acoplamento intra-classe legítimo em acoplamento inter-objeto pior — não
  faça sem ganho concreto.

---

## §2 — Comunicação por eventos

**Áudio, efeitos visuais e reações desacopladas passam pelo `EventBus`.**

- Gameplay **emite** eventos tipados (dataclasses em `game_events.py`); não
  chama `sound_manager` ou cria efeitos diretamente quando há um evento
  adequado. Quem reage são os sistemas inscritos (`SoundSystem`,
  `EffectsSystem`).
- Eventos são **dataclasses tipadas**, nunca dicts ou strings soltas. Novo
  tipo de comunicação → nova dataclass em `game_events.py`.
- Todo sistema que faz `bus.on(...)` **precisa** ter `cleanup()` que faz o
  `bus.off(...)` correspondente. Handler registrado sem remoção é memory leak
  quando o sistema é destruído (ver `SoundSystem.cleanup`, `EffectsSystem.cleanup`).
- `emit` não deve assumir ordem de subscribers nem que algum exista.

---

## §3 — Render sem efeitos colaterais

**`draw()` desenha. Não muta estado, não emite eventos, não dispara som.**

- Métodos de render leem estado e desenham na surface. Qualquer mutação
  (avançar timer, marcar morto, tocar som) pertence ao `update()`.
- Acúmulo de tempo para animação no draw usa um acumulador próprio
  (`self.draw_time` na `Ship`) alimentado pelo update — nunca `time.time()`
  direto, que quebra com pausa e slow-motion.

---

## §4 — Estado global

**Sem namespace global mutável. Configuração é imutável e por domínio.**

- `Config` é composto por dataclasses `frozen=True` por domínio
  (`DisplayConfig`, `GameplayConfig`, `MeteorConfig`, ...) agregadas em
  `ConfigurationManager`. Acesso atual é flat via `__getattr__`
  (`Config.SCREEN_WIDTH`) — contrato estabelecido, manter.
- Não introduza variáveis de módulo mutáveis para carregar estado de jogo.
  Estado de partida vive na cena ou nos sistemas; estado de jogador no
  `PlayerSlot`/`PlayerRoster`.

---

## §5 — Polimorfismo sobre `isinstance`

**Despache por método polimórfico ou class attribute, não por cascata de tipo.**

- Loops sobre entidades heterogêneas usam um protocolo de update uniforme.
  Padrão de referência: `EnemyUpdateContext` + `update_in_context(ctx)` —
  adicionar um inimigo novo exige só implementar o método na classe, nada
  muda no `EntityManager`.
- Identificação de tipo por class attribute consultado via `getattr`, não por
  `isinstance`. Padrão de referência: `getattr(type(boss), "MUSIC_STATE", None)`.
- Distinção de boss usa o atributo formal `is_boss` (de `BossHitMixin`), nunca
  heurística de nome (`"boss" in type(x).__name__.lower()`).
- Cascata `isinstance`/`if type ==` é code smell. Aceitável só quando
  construtores realmente divergem e não há abstração que justifique o custo
  (ver `_spawn_boss` — adiado deliberadamente).

---

## §6 — Mutação de listas no hot path

**Remoção de mortos é swap-and-pop in-place, não cópia + `.remove()`.**

- Padrão canônico: `EntityManager._filter_dead_inplace` (swap-and-pop, O(n),
  sem alocação). Use-o ou o equivalente inline:
  ```python
  i = 0
  while i < len(lst):
      if lst[i].dead:
          lst[i] = lst[-1]
          lst.pop()
      else:
          i += 1
  ```
- **Proibido no hot path:** `for x in lst[:]: ... lst.remove(x)`. Aloca cópia
  por frame e `.remove()` é O(n) → total O(n²).
- List comprehension de rebuild (`lst = [x for x in lst if not x.dead]`) é
  O(n) e aceitável fora do hot path (one-shot events, listas de partículas).
  Não confundir com o padrão O(n²) acima.

---

## §7 — Alocação por frame

**Hot path não aloca o que pode ser reutilizado.**

- Entidades de alta rotatividade (meteoros, balas, explosões, rock gliders)
  usam **object pools** (`MeteorPool`, `BulletPool`, `ExplosionPool`,
  `RockGliderPool`). Pool tem `get()` (reusa free-list ou cria) e `release()`
  (devolve marcando inativo). Free-list LIFO para spawn O(1).
- `rect` persistente atualizado in-place, não recriado por frame.
- Em loops quentes, faça bind local de globals/métodos repetidos
  (`cos = math.cos`) antes do loop.
- Geometria de grid via generator (`yield`), sem materializar `set`
  intermediário por chamada.

---

## §8 — Colisões

**Colisão espacial usa a spatial grid; dano passa por um roteador único.**

- Consultas de vizinhança usam `SpatialGrid.query`, não scan linear — exceto
  onde o overhead da grid supera o scan (listas comprovadamente ≤ ~30
  elementos, decisão documentada no ponto do código).
- Aplicação de dano passa por `CollisionPhysics.apply_hit` → `target.on_hit()`,
  que retorna `HitResult`. Não duplicar lógica de dano/score/explosão fora
  desse roteador.
- Som de hit vem de `HitResult.sound` (callable bound, ver `hit_sounds.py`),
  não de dispatch por string.

---

## §9 — Composição sobre herança

**Classe grande se decompõe por composição com delegação, mantendo a fachada.**

- Padrão de referência: `Ship` é fachada que delega para `ShipMovement`,
  `ShipRenderer`, `ShipPowerups`. A API pública externa não muda; os
  componentes recebem a `Ship` e operam sobre o estado dela.
- Estado compartilhado pode permanecer na fachada (lido por código externo);
  os componentes centralizam a **lógica coesa**, não necessariamente os dados.
- Mixins para contrato compartilhado entre uma família (ex.: `BossHitMixin`
  dá `is_boss`, `on_hit`, `collision_circle` fallback a todos os bosses).

---

## §10 — Imports

- Imports no topo do módulo. Import local (dentro de função) **só** para
  quebrar ciclo real de importação — não por hábito. Sub-módulo que só
  precisa de um tipo para anotação usa `TYPE_CHECKING`.
- Não fazer import dentro de `__init__` para resolver dependência que poderia
  estar no topo (custo por instanciação, sem ciclo que justifique).

---

## §11 — Wellbeing do código / bem-estar do jogador

- Sons, dificuldade e feedback escalam por configuração (`aggressiveness_multiplier`,
  presets de dificuldade), propagados **end-to-end** até a entidade — não
  parável no spawner. Multiplicador que não chega na entidade é no-op silencioso.
- Retrocompat deliberada (ex.: property `self.ship` durante migração
  multiplayer) é documentada no código com a razão e o plano de remoção. Não
  é dívida técnica enquanto rastreada.

---

## §12 — Documentos do projeto

- **`CLAUDE.md`** (este arquivo): princípios duráveis. Muda raramente.
- **`memory/`**: contexto persistente entre sessões (decisões, convenções
  específicas, estado de áreas).
- **`NOVO_PLANO_DE_REVISÃO.MD`**: backlog de revisão técnica do ciclo atual,
  com gravidade e status.
- **`PLANO_*.MD`**: planos temáticos (multiplayer, balanceamento, pendências).
- Critérios de gravidade da revisão referenciam este arquivo: **Crítico** =
  viola um princípio daqui, causa bug observável, ou bloqueia evolução.
  **Médio** = degrada legibilidade/testabilidade/composição. **Baixo** =
  polimento.

---

## Resumo (checklist de PR)

- [ ] Nenhum sistema lê privado (`_x`) de outro objeto
- [ ] Reações desacopladas (som/efeito) via `EventBus`; handler tem `cleanup()`
- [ ] `draw()` não muta estado nem emite eventos
- [ ] Sem estado global mutável; config por domínio imutável
- [ ] Despacho por polimorfismo/class attribute, não `isinstance`
- [ ] Remoção de mortos por swap-and-pop, sem `lst[:]` + `.remove()` no hot path
- [ ] Entidades de alta rotatividade usam pool; sem alocação evitável por frame
- [ ] Colisão via spatial grid; dano via `apply_hit`/`HitResult`
- [ ] Classe grande decomposta por composição, fachada preservada
- [ ] Imports no topo; local só para ciclo real