---
name: metropolis-overlord-city-boss
description: "Metropolis Overlord — 1º boss nativo do tema CITY (nível 30); progressão com escudo vai-e-volta, Fase 2 baseada em minas + lasers rotativos, Fase 3 = segmentação."
metadata: 
  node_type: memory
  type: project
  originSessionId: ee207f59-a94b-4cc8-badc-82b12395100e
---

`MetropolisOverlordBoss` é o **primeiro chefe nativo do tema CITY**, no **slot 30**
do `WORLD_BOSS_ROADMAP` (`world_config._get_boss_roadmap`, status "implemented",
substituiu o placeholder SpikeBoss). Origem: `código_teste/PROPOSTA_BOSSES_CIDADE.md`.

Decisão do usuário (2026-06-12): apesar de a proposta descrever um boss "ápice/final",
ele entra como o **opener** da Cidade (nível 30), não no final (40). Tuning de
dificuldade fica mais sensível por isso — Fase 1 deliberadamente branda.

Arquivos (em `game/entities/enemies/city/`): `metropolis_overlord_boss.py`
(FSM, BossProtocol), `metropolis_sentinel.py` (4 sentinelas da Fase 1/interlúdio, orbitam o
PERÍMETRO inteiro por comprimento de arco — velocidade uniforme `BASE_SPEED=0.12`
inalterada, ancoradas às bordas; **REFATORADA 2026-06-16** mesma qualidade da
CoreSentryDrone: paleta 3-tons por papel `_ROLE_PALETTE` (neon/missile/laser/emp),
esfera em camadas + halo + anel hexagonal + satélites + filamentos; FSM de combate
`_S_IDLE→_S_AIM(telegrafo)→_S_FIRE→_S_RECOVER` com alvo TRAVADO; telegrafo por papel
(neon=linha de mira, missile=anel/chevrons, laser=coluna-alvo, emp=anel de área);
materialização de nascimento (3 estágios) + morte impactante (implosão→fragmentos+
descarga+afterglow, `DEATH_BURST=0.5` → `dead` no fim, boss aguarda a anim p/ colapsar)),
`metropolis_segment.py` (3 triângulos da segmentação), `metropolis_projectiles.py`
(NeonBurstShot, MicroMissile, VerticalLaser, EMPPulse), `metropolis_drone.py`
(`EnergyTriangleDrone` — drones-triângulo da Fase 2), `metropolis_overlord_pixel_map.py`
(triângulo + `draw_plasma_sphere`). Wiring: roadmap + branch em
`BossFightController._spawn_boss` + Union de `EntityManager.boss`. `fixed_levels[30]` é só
layout (classe injetada pelo pipeline via `get_boss_for_level`).

**FSM ATUAL (refatorada 2026-06-16, "escudo vai-e-volta"):** INTRO_RISE → INTRO_DESCEND →
PHASE1 (sentinelas = ESCUDO/invuln) → SHIELD_COLLAPSE(next=PHASE2) → **PHASE2 (centro +
lasers rotativos + minas; gate = 5 explosões de mina)** → **SHIELD_REBUILD(next=INTERLUDE)
[colapso INVERTIDO]** → **INTERLUDE (2ª onda de sentinelas, padrão Fase 1)** →
SHIELD_COLLAPSE(next=SEGMENTATION) → SEGMENTATION (Fase 3 final). Os gatilhos do escudo
têm sucessor configurável: `_trigger_shield_collapse(next)`/`_trigger_shield_rebuild(next)`,
`_after_collapse`/`_after_rebuild`.

**O CORPO NUNCA é mirável a tiro em fase alguma** (`can_take_damage()` sempre False;
`rect`/`collision_circle` off-screen → tiros atravessam). O desmonte-a-tiro antigo, a
DERIVA da Fase 2 e o NeonBurstShot leak foram **REMOVIDOS**. **O boss NÃO ataca diretamente
na Fase 2** (2026-06-16): removidas as ondas de `EnergyTriangleDrone` que ele lançava — a
ofensiva secundária vem **só das 3 sentinelas `CoreSentryDrone`**. (`EnergyTriangleDrone`
existe em `metropolis_drone.py` mas o boss não o usa mais.)

**MECÂNICA CENTRAL (2026-06-14, pedido do usuário "destruir máquina camada por camada"):**
a progressão é 100% legível na pixel art, não em HP oculto.
- **Fase 1 = ESCUDO:** o **próprio contorno neon (`E`) do pixel art É o escudo** — NÃO há
  overlay/barreira extra (usuário rejeitou: "o escudo já está no pixel art como azul").
  Energizado = `_edge_color()` neon pulsante (`_shield_energy==1.0` enquanto ≥1 sentinela
  viva). Sentinelas são **geradoras**: ao cair a última → `_SHIELD_COLLAPSE`.
- **COLAPSO DO ESCUDO pixel-a-pixel** (2026-06-14, mesma filosofia física do resto: "tudo
  que protege o boss é desmontado na tela, não por mudança de estado invisível"). Dura
  `SHIELD_COLLAPSE_DUR=2.5s`. As células `E` (mapa interno) são pré-ordenadas por ângulo
  (`_edge_cells_order`, `_edge_threshold`): uma **frente de rachadura varre a borda**
  (`_collapse_edge_color` por célula: neon dissipando → branco-quente na frente → `EDGE_INERT`
  atrás). Conforme a frente cruza cada célula, ejeta um **caco de energia floaty**
  (`_spawn_edge_shard`, `_ArmorFragment` com `gravity=140`, cor `E`/`EDGE_GLOW`). Nos ~60%
  finais, **arcos elétricos** instáveis (`_update_shield_arcs`/`_jagged_arc` no update →
  `_draw_shield_arcs`, §3). Atrás da frente a célula **SOME de vez** — `_edge_draw_color`
  retorna `None` e a célula não é desenhada (usuário: "o contorno deve ir embora tbm, não
  ficar essa borda cinza"). Na Fase 2+ NENHUMA célula `E` é desenhada — o contorno foi
  destruído por completo; a silhueta passa a ser só o casco de placas `P` + núcleos.
  `EDGE_INERT` foi REMOVIDO (não há mais borda inerte). Só ao fim do colapso
  `can_take_damage()` vira True. `_ArmorFragment` ganhou params `gravity`/`life`.
- **SHIELD_REBUILD = colapso INVERTIDO** (2026-06-16): reusa `_edge_cells_order`/
  `_edge_threshold` em ORDEM INVERSA — a frente varre de volta e cada célula `E` REAPARECE
  (branco-quente → neon assentado), cacos CONVERGEM p/ a borda (`_spawn_rebuild_shard`,
  inverso de `_spawn_edge_shard`: velocidade p/ dentro, `gravity=-40`). `_edge_draw_color`
  trata `_SHIELD_REBUILD` como espelho (`front = 1 - th`). Ao fim, escudo 100% reativado e
  `_sentinels_spawned` rearmado p/ a 2ª onda. Mesma `SHIELD_COLLAPSE_DUR=2.5s`.
- **Fase 2 = LASERS ROTATIVOS + DRONES + MINAS** (2026-06-16, "fase estratégica, por
  posicionamento, não por DPS"). Equilíbrio pedido: **lasers = ameaça PRINCIPAL, drones =
  pressão SECUNDÁRIA, minas = mecânica ESTRATÉGICA p/ ferir o boss**. Boss faz lerp ao
  **centro da tela** (`_settle_to_center`, `PHASE2_SETTLE_SPEED=420`) e trava.
  - **PRINCIPAL = 3 lasers rotativos contínuos** (`MetropolisOrbitalBeam`, novo
    `metropolis_beam.py`, **subclasse de `BossLaser`** → vive em `em.boss_lasers` via
    `result.new_lasers`, atinge a nave por `laser_vs_ship`/`clipline`). Um por orb (base
    0/120/240°), **cada um na COR do seu núcleo** (cyan/magenta/amber via `PLASMA_THEMES`),
    **mesma espessura** (`BEAM_W=13`), giram em **UMA direção FIXA** (`ANG_SPEED=0.42`, lento/
    cadenciado p/ leitura — reduzido de 0.9→0.42; SEM inverter sentido). **Ciclo de vida próprio com apresentação** (estética neon): CHARGING
    (`CHARGE_TIME=0.7s`, build-up — flare condensando + cacos convergindo, `self.w=0` → NÃO
    causa dano, é telégrafo) → ACTIVE → FADING (`FADE_TIME=0.6s`, dissipa progressivamente).
    O boss chama `begin_fade()` (não mata abrupto) e os feixes terminam o fade sozinhos em
    `em.boss_lasers`. **Pulsação VISUAL contínua na fase ativa** (não muda colisão: `self.w`
    fixo em 13; só `_visual_w` oscila ±~2.3px): brilho respira ~78–100% + jitter (instabilidade),
    nós de energia correndo p/ fora (`_draw_energy_pulses`), filamentos de distorção, raiz/origem
    mais luminosas, faíscas. Partículas avançam no `update` (§3); flicker de filamento usa random
    no draw (crepitar, padrão dos drones). Refs em `self._beams`.
  - **SECUNDÁRIA = 3 sentinelas `CoreSentryDrone`** (única ofensiva além de lasers/minas;
    o boss não atira). Orbitam o boss central (um por núcleo; `ORBIT_SPEED` 0.42), arremessam
    `EnergyShardTriangle` da sua cor. **RESPAWN**: gerenciadas por SLOTS no boss
    (`_sentry_slots`: theme/base_angle fixos + drone|None + respawn_t). Destruída (quando
    `should_remove()`), renasce após `SENTRY_RESPAWN_TIME=10s` com a mesma animação de criação
    (`_update_core_sentries(dt,result)`); os slots são limpos no gate (encerra respawns).
    **CoreSentryDrone TOTALMENTE REFATORADA** (2026-06-16): FSM de combate legível
    `_S_IDLE→_S_AIM(telegrafo)→_S_FIRE→_S_RECOVER` (`_update_combat`), alvo TRAVADO no início
    da preparação (telegrafo honesto), órbita desacelera ao mirar. **Telegrafo distinto por
    cor** (`_draw_telegraph`): cyan=linha de mira reta, magenta=anel+chevrons girando,
    amber=zona de impacto na área. Estados visualmente distintos (energia/brilho/vibração).
    **Criação** em 3 estágios (condensação→arcos→ESTABILIZAÇÃO c/ flicker, `BIRTH_TIME=0.7`).
    **Atividade**: respiração, satélites orbitando, anel hexagonal (`_ngon`), filamentos,
    halo pulsante. **Destruição** refatorada (`DEATH_BURST=0.55`): implosão→ESTOURO com
    FRAGMENTOS triangulares girando (`_spawn_death_fragments`/`_update_death_frags`) + onda
    de choque + descarga + estática + afterglow residual.
  - **ESTRATÉGICA = minas da City** (`CityMine`, REUSO total: queda 50px/s, fuse 3s ao ser
    destruída a tiro, explosão raio ~240px, resíduos). **TETO RÍGIDO `MAX_ACTIVE_MINES=2`**
    simultâneas (`_prune_active_mines` libera o slot quando uma detona/`dead` ou sai da tela;
    `self._active_mines`): uma nova só surge quando uma das atuais some, com atraso
    `MINE_SPAWN_INTERVAL=3.0s/aggr` (1ª aos 2s) — `_make_mine` do topo, x enviesado ao centro
    e a uma **distância mínima** das ativas (`MIN_MINE_SEPARATION_FRAC=0.23`*W; subtrai zonas
    proibidas do intervalo de spawn e sorteia no restante — evita acúmulos/áreas injustas).
    **DANO SÓ POR MINA:**
    cada `MineExplosion` cujo disco cobre o centro conta 1 acerto (`_count_mine_hits`,
    `MINE_HIT_RADIUS=90`). **Gate = `MINE_HITS_TO_ADVANCE=5`** → SHIELD_REBUILD; cada acerto
    erode a carcaça (`_destroy_cells_near`) + flash. **BUG corrigido:** dedup por `id()` da
    explosão PODA p/ ids vivos a cada frame (`intersection_update`), senão `id()` reciclado
    após GC faria undercount (fase exigiria >5 minas).
- **INTERLUDE = padrão Fase 1** (`_update_interlude`): 2ª onda de `_spawn_sentinels`; matar
  todas → `_trigger_shield_collapse(_SEGMENTATION)`. Boss invulnerável enquanto houver sentinela.
- **Fase 3 = SEGMENTATION direta** (2026-06-16): ao cair o 2º escudo, `_update_segmentation`
  chama `_collapse_remaining_cells()` (explode o resto da carcaça) + `_spawn_segments` (3
  segmentos orbitais, lógica inalterada). NÃO há mais fase de desmonte-a-tiro nem
  `SEGMENT_THRESHOLD`/`_destroyed_fraction`/`_armor_tier`/instabilidade (removidos).
- `pmap` ganhou só `EDGE_INERT` (cor do contorno quando o escudo cai). Smoke headless
  cobre todas as transições + draw por estado (validado).

Teste rápido: a **arena de teste CITY** (`THEME_TEST_LEVELS[CITY]` em fixed_levels,
`TEST_ARENA_ENABLED`) pega o boss do **template da arena, não do roadmap** — está
apontada para o MetropolisOverlordBoss (reverter para GiantMeteorBoss ou desligar o
flag antes de jogar a campanha).

Decisões de arquitetura (esqueleto rodável; smoke tests passam):
- Sentinelas e seus projéteis vivem em **`em.enemies`** (roteados por `ctx.new_enemies` /
  `ctx.entity_manager.enemies.append`), reusando colisão/draw/cleanup — zero plumbing nova.
- **Anti-softlock** (ver [[level-progression-onscreen-visibility]]): sentinelas patrulham
  segmentos com inset das bordas (sempre on-screen/alcançáveis); o boss só checa o gate.
- Fase 1 = corpo **invulnerável e não-mirável** (`can_take_damage` False; `rect`/
  `collision_circle` devolvem offscreen) até as 4 sentinelas morrerem.
- **Design visual = "Reator Triangular"** (pedido do usuário): grande triângulo tecnológico
  SIMÉTRICO (ápice afiado no topo, gerado por `_build_maps()` com colunas ímpares=25) como
  estrutura de contenção de **3 núcleos energéticos** em arranjo triforce. As esferas dominam;
  carcaça fosca/secundária. WIDTH=250, HEIGHT=210, PIXEL_SCALE=10 (mapa 25x21). Chars do mapa:
  `E` contorno neon (persiste), `P` placa externa destrutível, `G` frame interno escuro.
- **Destruição por camadas dirigida por HP** (hitbox única, Fase 2): no `draw`, interna (G+E)
  sempre por baixo; placas P por cima saem de fora p/ dentro (`_shell_order` por distância do
  centro) conforme HP cai 100%→`CORE_FRACTION`(20%); cada placa vira `_ArmorFragment` (voa).
  Geração no `update` (`_update_shell_destruction`), nunca no `draw` (§3).
- **3 núcleos de plasma vivo** = procedurais. `pmap.draw_plasma_sphere` (módulo pixel_map,
  reusado por boss e segmentos): fluido por **metaballs** orbitantes em células chunky (pixel
  art) sobre gradiente neon 3-paradas (`pmap.PLASMA_THEMES` cyan/magenta/amber). **SEM halo de
  glow E SEM aro de contenção** (ambos removidos a pedido 2026-06-14: "anel branco encapsulava,
  adiciona ruído"); só o plasma limpo, o campo já escurece nas bordas. Animação só via
  `anim_time` (§3). **Proporção:** `SPHERE_DEFS` rel_r reduzido 0.135→0.11 p/ mais espaço
  negativo dentro do triângulo (núcleos lidos individualmente, não dominam a silhueta).
- **SEGMENTATION (fase final)**: ao atingir `CORE_FRACTION`, o boss vira coordenador invisível
  e não-mirável; cria **3 `MetropolisSegment`** (triângulos menores, 1 núcleo cada) em
  `em.enemies`, orbitando um ponto invisível (centro da arena, raio ~28% do min(W,H)), 120°
  apart, cada um com ataque próprio (cyan=VerticalLaser, magenta=MicroMissile, amber=EMPPulse+
  leque). Cada segmento tem HP próprio (~18% do max). O coordenador morre quando os 3 caem.
  (Substituiu o antigo PHASE3 de City Beam/drones/regen.)

TODO/pontos abertos do parecer crítico (ainda não implementados):
- **EMPPulse**: o debuff de "lentidão nos projéteis do jogador" é mecânica reversa do EMP
  atual (jogador→inimigos) e está **stub** (só dano de contato). Falta plumbing em Ship/bullets.
- Visual procedural simples (sem pixel-map dedicado); sem música própria (cai em MusicState.BOSS).
- Tuning de HP/cadência/ativação é preliminar.
