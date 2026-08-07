# CLAUDE.md — Diretrizes do Projeto Pixel Patrol

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
  `isinstance`. Padrão de referência: `getattr(boss, "BOSS_TYPE_NAME", None)` —
  ex.: a música de boss é descoberta pela pasta `audio/music/bosses/<BOSS_TYPE_NAME>/`,
  sem mapa por boss no código.
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
- **Por que a regra existe** (medido): abaixo de ~50 elementos os dois padrões
  empatam — o swap-and-pop chega a perder por pouco em listas minúsculas. O
  ganho está na cauda: 2× em 100 itens, 6,7× em 200, 9× em 800. A regra vale
  para listas **sem teto de crescimento**, que é o caso de efeitos e projéteis
  em combate intenso. Não vale a pena reescrever uma lista comprovadamente
  pequena e limitada só para seguir o padrão.

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
- **Extração de fluxo da `PlayingScene`** (padrão de referência: `RevivalSystem`,
  `UpgradeSelector`): o sistema **não referencia a cena** (§1); dependências
  entram pelo construtor — objetos de domínio + **callbacks** para o que a cena
  mantém (`sync_lives`, `activate`). Estado que já vive na entidade fica lá
  (`slot.revival_beacon`); a cena expõe **fachada fina** para a API que outros
  já chamam. Prova de sucesso: o sistema fica **testável com stubs mínimos**,
  sem instanciar o jogo.
- **Ao migrar estado para um sistema, `grep` o projeto INTEIRO pelo nome do
  atributo — não só pelos métodos que se movem.** Um leitor/escritor externo do
  atributo cru (ex.: `gameplay_input_handler` mexendo em `scene.upgrade_select_mode`)
  quebra em runtime mesmo com os testes e o lint verdes, porque nada o
  exercitava. O DTO de render (`RenderFrame`) já isola o render dessa quebra; o
  input handler e outros sistemas, não. Preserve o nome como property de
  leitura na fachada quando houver leitores externos.

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
- **Curva global de introdução de variedade.** Todo mundo apresenta os inimigos
  em rampa pelo **índice absoluto do estágio**: `X-1` no máx. 1 tipo, `X-2` no
  máx. 2, `X-3+` o teto da dificuldade. Regra única em
  `_apply_enemy_variety_cap` (`pipeline.py`): `cap = min(estágio_absoluto, teto)`,
  com `teto = VARIETY_CAP_MAX_BY_DIFFICULTY` (3 Normal/Casual, 4 Hardcore/
  Pesadelo). É **só teto** (limite superior): se o pool do tema liberou menos
  tipos, mostra menos — sem pico de complexidade ao entrar num mundo novo.
  Aplica-se a **todos** os caminhos (procedural, meteor_storm e fixed levels);
  nenhum nível deve burlar o pipeline `_apply_theme_enemy_rules`. A *contagem* é
  teto global; a *disponibilidade* (quando cada tipo entra no pool) usa o gate de
  **estágio absoluto** (`stage_number`) para o trio de introdução — 2º tipo em
  `stage>=2`, 3º em `stage>=3` — em `procedural._configure_*_spawn`, para a regra
  valer em qualquer tamanho de mundo. A **frequência** de cada tipo continua
  escalando por `stage_progress`. Tipos tardios/minibosses seguem gate por
  `stage_progress`.
- **Filosofia "SWARM + N complementares".** O teto conta o **base do tema**
  (Meteor/RockGlider/CityDrone, papel `volume`) como 1 slot: o base é o SWARM —
  a massa sempre presente e mais frequente (menor `spawn_time`), garantida em
  `_select_variety_subset` (adicionado primeiro). Logo `cap` 3 → swarm + 2
  complementares (Normal/Casual) e `cap` 4 → swarm + 3 (Hardcore/Pesadelo).
  Nenhuma fase é "só de specials"; os specials **complementam** o swarm. A
  triangulação por papel (`ENEMY_ARCHETYPE` + `ROLE_REPEAT_PENALTY` escalonado)
  favorece papéis distintos (pressão + controle + ameaça especializada).
- **Histórico de combinação (anti-repetição do triângulo).** Além da recência
  POR TIPO, o **conjunto de specials** não repete a fase imediatamente anterior
  (proibição dura via re-sorteio com seed perturbado) e evita as
  `COMBINATION_HISTORY` fases recentes em best-effort. Resolvido recursivamente
  e memoizado, ancorado no `start_level` do mundo. Exato quando o pool é igual
  entre fases vizinhas; resíduos só quando o pool **não pode** variar (pool de
  specials ≤ vagas — ex.: Vulcão só tem Alien+EyeEnemy) ou no exato boundary de
  desbloqueio de um special (pool cresceu). Repetição forçada por falta de pool
  é **gap de conteúdo** (faltam inimigos no tema), não bug do algoritmo.

---

## §12 — Escala de UI por resolução

**UI desenhada em pixels do design base (1280×720) escala por `ui_scale`.**

- O jogo roda com `pygame.SCALED`: gameplay desenha numa resolução lógica fixa
  e o pygame escala o frame inteiro para a tela física (mantendo 16:9, com
  letterbox). Posições de **mundo/spawn** já usam fração de `Config.SCREEN_WIDTH`
  — adaptam-se sozinhas. Tamanhos de **UI** (fontes, caixas, slots, offsets)
  são pixels fixos e **não** se adaptam quando a resolução lógica muda
  (`settings.py` oferece 576p→1080p; aplicada no restart via `set_screen_resolution`).
- Convenção: `self.ui_scale = Config.SCREEN_WIDTH / 1280.0` (um fator serve aos
  dois eixos por ser 16:9) e todo pixel fixo é multiplicado por ele via o helper
  `self._s(valor) -> int(valor * ui_scale)`. Fontes:
  `get_font(max(8, int(base * ui_scale)))`. Em 720p `ui_scale == 1.0` → layout
  idêntico ao design, sem regressão.
- A base `Scene` (`core/state.py`) já provê `ui_scale` e `_s` no `__init__` —
  toda cena que chama `super().__init__(app)` herda. Classes de UI que **não**
  são `Scene` (renderers como `GameRenderer`/`Renderer`, views, widgets,
  diálogos) declaram o próprio `ui_scale`/`_s` com a mesma fórmula.
- Não escalar espessura de borda (1–3px, piso visual) nem amplitude de animação
  cosmética.
- Validar headless em 576p/720p/1080p antes de fechar: nada estoura a tela e
  720p não muda. Detalhe e telas pendentes em `memory/menu-ui-scale-convention`.

---

## §13 — Documentos do projeto

- **`CLAUDE.md`** (este arquivo): princípios duráveis. Muda raramente.
  **Versionado** — é a única fonte das convenções que o código cita ~300 vezes,
  e precisa viajar com o repositório entre máquinas.
- **`memory/`**: contexto persistente entre sessões (decisões, convenções
  específicas, estado de áreas).
- **`NOVO_PLANO_DE_REVISÃO.MD`**: backlog de revisão técnica do ciclo atual,
  com gravidade e status.
- **`PLANO_*.MD`**: planos temáticos (multiplayer, balanceamento, pendências).
- Os itens acima, exceto este arquivo, estão no `.gitignore` — são locais por
  decisão. Quem clonar o repositório não os encontra; ao citá-los em comentário
  de código, lembre que o leitor pode não ter acesso.
- Critérios de gravidade da revisão referenciam este arquivo: **Crítico** =
  viola um princípio daqui, causa bug observável, ou bloqueia evolução.
  **Médio** = degrada legibilidade/testabilidade/composição. **Baixo** =
  polimento.

---

## §14 — Cadência e tempo independentes de frame rate

**Evento periódico acumula tempo; nunca reatribui o intervalo cheio.**

- **Proibido:** `timer -= dt; if timer <= 0: agir(); timer = INTERVALO`. O
  disparo só acontece em fronteira de frame, então o timer não zera exato —
  estoura e fica negativo. Reatribuir o intervalo **descarta essa sobra**, o
  período real vira um número inteiro de frames e o evento rende **menos** que o
  configurado. Medido: Estilete a 8,5 tiros/s em vez de 9,35 (quando ele ainda
  era `fire_rate_mult=1.87`; hoje é 1.60); rajada do CyberTank 25% lenta a
  30fps. O erro é invisível em teste manual porque é pequeno e sistemático.
- **Armas** usam `FireTimer` (`core/fire_timer.py`): `advance(dt, intervalo)` +
  `while consume(intervalo)`. O `while` (não `if`) emite todos os tiros que
  couberem no passo — é o que evita perder disparos quando o intervalo é menor
  que o `dt`.
- **Compensação sub-frame:** o `overshoot` do `FireTimer` é há quanto tempo o
  disparo já era devido; aplicá-lo como deslocamento inicial do projétil torna o
  espaçamento no ar uniforme. É esse espaçamento que o olho lê como ritmo —
  ninguém vê o instante da emissão, e sim a fila de projéteis na tela.
  A conta usa **velocidade relativa** (`emission_offset`, em `core/fire_timer.py`):
  `(v_projétil − v_emissor) × overshoot`. O emissor também estava em outro lugar
  quando o tiro era devido; compensar só o projétil corrige o eixo de voo e deixa
  o eixo do movimento do emissor com o mesmo erro de quantização — o defeito
  original, apenas girado 90°. Medido no Estilete em strafe: 4,2% de variação de
  espaçamento a 60fps e 8,4% a 30fps, contra **0,00px** com velocidade relativa.
  Com emissor parado a fórmula degenera no caso antigo, então não há caso a
  distinguir.
- **Um relógio por cadência.** Nunca empilhe um segundo gate periódico sobre o
  `FireTimer`. **Dois gates independentes não se somam — eles batem:** o evento
  só ocorre quando as duas janelas coincidem no mesmo frame, e a cadência real
  vira o batimento entre elas, não a configurada. Medido: o auto-fire mantinha
  um relógio próprio (janela de 1 frame a cada 0,1s, com o `timer = 0` proibido
  acima) e cobrava de **todas** as naves — Estilete 8,00/s configurado rendendo
  5,71/s, Padrão 5,00 → 4,29, Aríete/Caçador 3,75 → 2,86. Pior: só o Estilete
  ficava **irregular** (vãos alternando 7 e 14 frames, pares colados com vão
  dobrado), porque a razão entre a cadência dele e a janela era a única do
  elenco a cair numa alternância 2:1. Nas outras o batimento só cobrava
  cadência sem quebrar o ritmo — por isso passou anos despercebido e o sintoma
  parecia ser "da nave". Gatilho (auto-fire, botão segurado, IA) diz **se** quer
  atirar; o `FireTimer` diz **quando**.
- **Gastar o timer sem ler o `overshoot` é meio-caminho, e não avisa.** Dá para
  chamar `consume()` e descartar o valor — foi o que o `fire_berserk` fez por
  todo o tempo em que existiu, deixando a Estrela Espiral sem compensação
  nenhuma enquanto o `fire()` ao lado compensava. Varrido por
  `test_conventions.test_quem_consome_firetimer_compensa_a_emissao`; exceção
  legítima entra na allowlist do teste com o motivo (hoje: `Wingman` e
  `MiniShip`, que miram alvo móvel e não formam fila visível de projéteis).
- **Eventos periódicos simples** de entidade (rajada, pulso de área) usam
  `carry_interval(restante, intervalo)` — mesma matemática, sem o aparato de
  arma.
- **Não migrar** timers que não são cadência: FSM com sentinela, timer que
  alimenta animação de carga (o `charge_ratio` lê o tempo restante), ou evento
  *gated* por estado — nesse último, o crédito acumulado com o gate fechado
  dispararia tudo no instante em que ele abre. Casos avaliados e mantidos:
  `Alien`, `StoneSentry`, `CyberTank` RAILCANNON, `SpikeBoss`,
  `MountainSerpentBoss`.
- O `dt` do loop é clampado em `_MAX_FRAME_DT` (1/30) em `app.py`: abaixo de
  30fps o jogo inteiro entra em câmera lenta, de propósito, para um frame longo
  não teleportar a física. **Não** compensar isso dentro de um sistema
  específico — a decisão é global e todos os sistemas desaceleram juntos.

---

## §15 — Persistência

**Escrita de dados do jogador é atômica. Nunca direto sobre o arquivo real.**

- Gravar com `open(path, "w")` deixa um arquivo truncado se o processo morrer no
  meio — crash, queda de energia, fechar a janela durante um auto-save. O
  perfil vira ilegível e o jogador perde moedas, naves, mundos e estatísticas
  de uma vez. É a pior falha possível em retenção, e silenciosa.
- Sequência obrigatória (`PlayerProfile._write_profile_atomic`): grava em
  `.tmp` → `flush()` + `os.fsync()` → promove o arquivo íntegro atual a
  `.bak.json` → `os.replace(tmp, final)`. O `os.replace` é **atômico** em POSIX
  e Windows: ou o antigo continua inteiro, ou o novo está completo.
- O `load` tem cadeia de recuperação: principal → `.bak.json` → defaults. Um
  arquivo ilegível é preservado como `.corrupt.json` para diagnóstico, sem
  sobrescrever o backup (que é o último estado **bom** conhecido).
- Vale para qualquer dado durável novo (saves de partida, replays, telemetria).
  Auto-save durante gameplay é o caso mais crítico: a janela de escrita
  coincide com o jogador podendo fechar o jogo a qualquer momento.

---

## §16 — Testes

**Lógica pura e convenções têm testes; o CI os roda em cada push.**

- Testes ficam em `tests/`, rodam **headless** (SDL dummy via
  `tests/conftest.py`) e não abrem janela nem exigem áudio. `python -m pytest`.
- O alvo é **lógica pura** — o que dá para testar sem instanciar o jogo inteiro:
  contratos de cadência (`FireTimer`), persistência atômica, invariantes de
  balanceamento, filtros de entidade. Não perseguir cobertura de render/cena;
  o retorno não paga o custo de mockar pygame.
- **Testes de convenção** (`tests/test_conventions.py`) varrem o código-fonte
  atrás dos anti-padrões que este documento proíbe (§6 `lst[:]`+`remove`, §1
  acesso a `_privado` entre sistemas, §2 `bus.on` sem `off`). São o que impede
  a erosão de voltar entre sessões. Exceção legítima entra na allowlist
  explícita do teste, com o motivo — nunca afrouxe a varredura.
- Invariante de balanceamento é **faixa**, não número exato: o teste trava
  outliers grosseiros (uma nave 2× ou 0,5×), não o micro-ajuste, que muda
  sempre.
- O CI (`.github/workflows/ci.yml`) roda `ruff check` + `pytest` no push/PR.
  Verde é pré-requisito de merge. Antes de abrir PR, reproduza local:
  `ruff check game tests && python -m pytest`.

---

## §17 — Transição de cena

**Navegação passa pelo router. Nenhuma cena desenha o próprio fade de troca.**

- Trocar de tela é `app.go_to(fábrica)` / `app.go_back()` / `app.open_overlay(fábrica)`.
  Chamar `states.switch/push/pop` direto (fora do `app.py`) pula o fade **e** o
  bloqueio de input da fase de saída. Varrido por `test_conventions`.
- O argumento é uma **fábrica**, não uma cena pronta: a construção roda no pico
  do fade, então o custo de montar cenas caras (`PlayingScene`) fica escondido
  atrás do preto em vez de travar um frame visível.
- Dois estilos. `BLACK` (padrão) escurece → troca → clareia; é a troca de tela
  de verdade. `DIM` troca na hora e não pinta véu: é para quando a cena que
  entra **continua desenhando** a de baixo (pausa, game over, modal do P2) —
  ali um preto no meio pisca em vez de suavizar. A cena DIM anima a própria
  escurecida lendo `app.transition.enter_progress`, sem timer próprio.
- **Por que a regra existe** (medido): antes havia **sete** implementações
  paralelas de fade e quatro telas sem nenhuma. Duas consequências reais —
  o overlay do Game Over ficou 100% invisível porque o buffer compartilhado de
  fade carregava um `set_alpha(0)` residual de outra tela, e Settings/
  Statistics/Upgrades vazavam uma `MainMenuScene` na pilha por visita (faziam
  `switch` de uma cena que tinha sido `push`ada).
- Distinga **transição de cena** de **animação interna da tela**. O crossfade
  entre as views do `MainMenu` (menu ↔ mundos ↔ dificuldade) não empilha nem
  troca cena: é intra-cena e não passa pelo router. O reveal de 2s do Game Over
  é conteúdo da tela, não transição. Só navegação vai pelo `SceneTransition`.
- Buffer de fade compartilhado (`get_fade_scratch`) devolve sempre com
  `set_alpha(255)`. `set_alpha` persiste no objeto `Surface` e `fill()` escreve
  o alpha *por pixel*, não o de superfície — quem esquecia disso herdava o
  alpha do consumidor anterior.

---

## §18 — Preferências e volume

**Uma instância de `UserPreferences` por arquivo. Mudar o número de volume não
muda o som — reaplique aos objetos carregados.**

- `app.preferences` é a instância viva; telas que editam preferências recebem
  **essa**, não constroem a própria sobre o mesmo JSON. Duas cópias divergem em
  memória: a tela salva a dela, o resto do jogo lê a antiga, e um
  `app.preferences.save()` qualquer (hot-plug de controle) regrava o valor
  velho por cima da escolha do jogador.
- `pygame.mixer.Sound` guarda o volume **dentro do objeto**, gravado no
  `load_sfx()` da carga. Escrever `sound_manager.sfx_volume` não alcança um som
  já carregado — todo caminho que mexe em volume termina em
  `_update_all_volumes()`. Vale para qualquer preferência aplicada a recursos
  já materializados, não só áudio.
- **Por que a regra existe** (medido): o `sound_manager` é singleton construído
  no import, antes de as preferências existirem, então os SFX nascem com o
  volume de fábrica. O `load_config` do boot só atualizava os campos → em todo
  boot o jogo tocava os efeitos ~3× mais alto que o configurado (0,2969 medido
  contra 0,1000 pedido) **enquanto a tela exibia o valor certo**. Só mexer no
  slider consertava, até o próximo boot — por isso passou tanto tempo
  despercebido.
- Música já segue o padrão certo e é a referência: `music_target_volume()` é
  recalculado antes de cada `play`, então não existe estado assado para
  dessincronizar.
- Teste o **estado real do mixer**, não o campo. O campo era justamente o que
  estava correto enquanto o jogador ouvia outra coisa (`tests/test_audio_config.py`).

---

## §19 — Foco, hover e entrada por dispositivo

**O destaque muda a borda que o elemento já tem. Nenhuma segunda moldura.**

- Hover (cursor sobre o elemento) e foco (teclado/controle) são o **mesmo
  estado** — "é isto que responde se você confirmar" — e recebem o mesmo
  desenho. Fonte única: `FOCUS_HIGHLIGHT` + `interactive_border_color`
  (`scenes/ui_helpers.py`); `draw_bordered_button(..., focused=...)` é o botão
  padrão do jogo. Telas que navegam por foco próprio
  (`owns_gamepad_navigation`, sem cursor virtual) passam `focused=`.
- **Proibido:** desenhar um contorno EXTRA (anel, halo, retângulo inflado) por
  cima de um componente que já tem borda. O foco altera cor/espessura/brilho
  do que está lá. Um elemento sem borda (o preview da nave) acende o que ele
  já desenha — no caso, o holofote.
- **Por que a regra existe** (medido): a tela de Aprimoramentos tinha o próprio
  `_draw_focus_ring` — anel pulsante **ciano**, uma cor que não aparece em mais
  nenhuma tela — desenhado por fora da borda do card, do slot e da aba. O
  resultado era borda dupla em cinco componentes e um estilo de seleção que
  ninguém mais no jogo usava. Convivia com uma segunda lógica de seleção
  (traço azul de "selecionado") no mesmo card, então dois contornos concorriam
  na mesma célula.
- **Cadência de repetição é uma só.** Segurar a seta com o mouse, segurar o
  analógico e segurar o D-pad usam `NAV_INITIAL_DELAY`/`NAV_REPEAT_RATE` da
  cena. Ritmos diferentes por dispositivo leem como três interfaces.
- **Roda do mouse é `pygame.MOUSEWHEEL`.** Os botões 4/5 são da era do
  pygame 1 e o SDL2 não os emite — código que os espera não roda nunca e o
  sintoma é "a roda não faz nada" enquanto o controle funciona. `MOUSEWHEEL`
  não carrega posição: use `pygame.mouse.get_pos()`.
- **Indicador que rola/aciona é BOTÃO.** Se a tela desenha uma seta de rolagem,
  ela tem alvo de clique — e o alvo sai do **mesmo helper de geometria** que o
  render usa (`detail_arrow_rects`). Desenhar num lugar e testar o clique em
  outro é como a seta virou enfeite não-clicável.
- **`A` aciona o FOCO, nunca "o que estiver sob o cursor".** Tela sem foco
  próprio herda o cursor virtual do app, e ele entra onde a tela anterior o
  deixou — em geral fora do modal. Aí `A` não acha nada sob o ponteiro e cai no
  fallback: no modal pré-jogo, apertar `A` "para escolher" **começava a
  partida**. Quem tem foco explícito (`owns_gamepad_navigation`) trata
  `JOYHATMOTION` e faz o polling do analógico por conta (o app não move cursor
  ali) e abre com o primeiro elemento já destacado.
- **Duas fontes de movimento não convivem.** Ligar o Modo Controle Xbox
  **desliga** o `mouse_control`, e o toggle do mouse fica travado enquanto isso
  (`UserPreferences.set_gamepad_enabled` / `mouse_control_locked`). A regra mora
  na preferência, não na tela: são três caminhos que ligam o controle
  (Configurações, modal de controles, auto-ligar do hot-plug) e a exclusão
  precisa valer nos três. **Por quê:** o analógico só vence enquanto está
  inclinado (`ShipMovement._move_impl`); soltar o stick devolvia a nave para
  debaixo de um ponteiro parado, e a nave "escapava" sem nada explicando.
  Varrido por `tests/test_control_exclusivity.py` (atribuição crua a
  `gamepad_enabled` é erro).
- **Bumpers seguem a convenção do gênero:** LB volta, RB avança. Vale para
  qualquer cursor navegável por bumper.
- **"Disponível" é `is_ready`, não `cooldown_left <= 0`.** O cooldown de um
  upgrade só parte quando o efeito TERMINA (§ `ActiveUpgrade.update`), então
  entre ativar e acabar ele tem cooldown zero **e** não pode ser usado. HUD e
  cursor de seleção consultam `is_ready`; `can_activate` é `is_ready` mais o que
  depende do mundo. Subclasse com regra própria sobrescreve `is_ready` — nunca
  duplica a lista de condições em `can_activate`.

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
- [ ] Cadência por `FireTimer`/`carry_interval`; nenhum `timer = INTERVALO`
- [ ] Um só relógio por cadência — nenhum gate periódico empilhado sobre o `FireTimer`
- [ ] Quem chama `consume()` aplica `emission_offset` (velocidade **relativa**)
- [ ] Persistência com escrita atômica (`.tmp` + `os.replace`), nunca sobre o arquivo real
- [ ] UI (fontes/caixas/offsets) escalada por `ui_scale`; validada fora de 720p
- [ ] Navegação por `app.go_to`/`go_back`/`open_overlay`; nenhuma cena desenha fade de troca
- [ ] Preferência aplicada a recurso já carregado é reaplicada (volume → `_update_all_volumes`)
- [ ] Foco/hover mudam a borda existente (`interactive_border_color`); nenhum anel por cima
- [ ] Roda do mouse por `MOUSEWHEEL`; indicador clicável compartilha geometria com o render
- [ ] Controle e mouse não movem a nave juntos (`set_gamepad_enabled`); LB volta / RB avança
- [ ] Disponibilidade de upgrade por `is_ready` (cooldown zero ≠ pronto durante o efeito)
- [ ] `ruff check game tests` limpo e `pytest` verde antes do PR