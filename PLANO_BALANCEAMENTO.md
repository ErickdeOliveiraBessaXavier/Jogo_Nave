# PLANO — Balanceamento do Ecossistema de Inimigos

Plano temático (§13 do `CLAUDE.md`) para o **balanceamento do sistema de
encontros**: rotação, frequência, pesos de spawn, variedade e composição de
arquétipos ao longo da campanha.

Origem: revisão data-driven de 2026-06 (composição pós-pipeline dos 45 níveis em
Normal/Hardcore + simulação real do `EnemySpawner`). Metodologia: *share* de
spawn = `1/spawn_time` normalizado; cobertura = nº de níveis em que o tipo
aparece pós-`variety_cap`.

---

## Escala de dificuldade — validada ✅

Scaling coerente e propagado end-to-end (§11):

- **HP efetivo** = preset (0.8/1.0/1.3/1.5) × ramp de estágio (+0→15% no mundo,
  reseta a cada mundo) × coop (+15%/jogador extra). Boss coop +40%/extra.
- **Cap dinâmico** = base_preset + world_bonus(0-4) + stage_bonus(0-4) ×
  coop(+20%/extra).
- **Coop**: clear ×1.35, spawn ×1.20, cap ×1.20, HP ×1.15 por jogador extra.
- **Hardcore/Pesadelo abrem o teto de variedade para 4** (vs 3) — dificuldade
  maior entrega mais variedade, não só mais HP. Acerto de design.

Conclusão: a curva de dificuldade está sólida. Os problemas estão na
**composição e exposição de conteúdo**.

---

## Mapa de arquétipos (`ENEMY_ARCHETYPE` em `pipeline.py`)

| Mundo | volume | sniper | rush | tank/elite | area_denial | support | summoner | shield |
|---|---|---|---|---|---|---|---|---|
| Montanha | RockGlider, (Propeller=swarm) | StoneSentry | — | ElementalRobot | — | MountainMage | — | — |
| Espaço | Meteor, (Satellite=hazard) | EyeEnemy | Alien | — | — | — | SquareMinionBoss | — |
| Cidade | CityDrone | NeonSniper | PoliceInterceptor | CyberTank | Captor, Mortar, Tesla | Jammer, Sapper | Cargo, Splitter | MirrorPylon |
| Vulcão | Meteor | EyeEnemy | Alien | — | — | — | SquareMinionBoss | — |

Colisões de papel (mesmo arquétipo) só existem na **Cidade** → a triangulação do
variety cap age naturalmente lá.

---

## Achados e status

### P1 — Sub-exposição da linhagem da Cidade — ✅ corrigido (parcial)
**Problema:** com teto global 3, 7 dos 12 inimigos da Cidade apareciam 1×/campanha;
toda a tier "miniboss" (CyberTank/Cargo/Splitter/Mirror) era vista 1× cada.

**Correção implementada (`pipeline.py`):**
- ~~`THEME_VARIETY_CAP_OVERRIDE`: teto CITY = 4/5.~~ **REVERTIDO (jun/2026):** o teto
  global voltou a **3 (Normal/Casual) / 4 (Hardcore/Pesadelo)** sob a filosofia
  "SWARM + N complementares" (o base do tema conta como 1 slot). Sem override por
  tema — `VARIETY_CAP_MAX_BY_DIFFICULTY` global. A sub-exposição da tier miniboss
  passa a ser atacada pela **rotação** (recência + histórico de combinação), não
  por mais slots simultâneos. Ver `memory/swarm-base-and-combination-history`.
- **Seleção complementar (triangulação):** `_apply_enemy_variety_cap` monta
  encontros por papel — `ENEMY_ARCHETYPE` + `ROLE_REPEAT_PENALTY` (escalonado por
  ocorrência, `PENALTY ** nº`). Loteria ponderada por assinatura/spotlight,
  penalizada por papel repetido. Resultado: cada nível traz SWARM (drone) + 2
  complementares de papéis **distintos** no Normal (+1 no Hardcore) — ex.:
  drone + support + tank.

**Resíduo (backlog):** há 11 specials para ~9 estágios não-boss; mesmo com teto 4
alguns ainda aparecem 1-2×/campanha. Tensão conteúdo-vs-pacing inerente. Opções
futuras: (a) mais estágios na Cidade; (b) curar o roster; (c) janela de rotação
por recência para evitar L33≈L34. **Não é regressão** — exposição total subiu.

### P2 — Vulcão sem identidade própria — ⛔ aberto (conteúdo)
**Problema:** L36-45 = Meteor+Alien+EyeEnemy em todos os 10 estágios. Zero inimigo
exclusivo; é o mundo mais repetitivo, e é o 4º (deveria ser clímax).

**Mitigação imediata aplicada (P3):** invertido o anti-padrão que *boostava* o base
(Meteor) no mid/late do Vulcão — agora taper + reforço de Alien/Eye, então pelo
menos não é idêntico ao Espaço.

**Correção real (backlog de conteúdo):** criar 2-3 inimigos lava-temáticos
exclusivos (ex.: area-denial de magma, swarm de brasas, tank de obsidiana).
Enquanto não houver, o Vulcão segue genérico.

### P3 — Flood do inimigo-base — ✅ corrigido (tuning)
**Problema:** base ocupava 82-86% dos eventos de spawn (peso `1/spawn_time`: base
~1.2s vs specials 8-30s).

**Correção implementada:** bandas **"late"** do perfil `moderate`
(`ENEMY_STAGE_WEIGHT_PROFILES`): taper do base (CityDrone 0.80, RockGlider 0.88,
Meteor 0.90-0.92) + reforço dos specials (1.20-1.35). Sem aumentar pressão total
(o `spawn_multiplier`/diretor governa o volume; só redistribui QUEM nasce).

**Efeito medido (spawner real, City L34):** drones 81.5% → **71%**, com os 3
pesados complementares presentes. Vulcão L44: Meteor 49% → 40%.

### P4 — Intros de mundo chapadas — ℹ️ deliberado
X-1 = 100% base, X-2 = base + 1 special a ~6%. É a rampa X-1→1 tipo (§11, evitar
pico de complexidade na entrada). Trade-off legítimo; custo = repetição nos 2
primeiros estágios. Sem ação por ora.

### P5 — Repetição entre estágios consecutivos — ✅ aliviado via P1/P3
Era consequência de poucas vagas + base dominante. A triangulação + teto 4 + taper
diversificam estágios vizinhos. Resíduo: cauda da Cidade (L33≈L34) ainda repete os
heavies mais novos — ver resíduo de P1.

---

## Resumo do que mudou no código (commit desta revisão)

`game/core/levels/pipeline.py`:
- `ENEMY_ARCHETYPE`, `_enemy_role`, `ROLE_REPEAT_PENALTY` — mapa de papéis.
- `THEME_VARIETY_CAP_OVERRIDE` — teto de variedade por tema (CITY 4/5).
- `_apply_enemy_variety_cap` — seleção complementar consciente de arquétipo.
- `ENEMY_STAGE_WEIGHT_PROFILES["moderate"]` — bandas late rebalanceadas (P3).

## Backlog priorizado

| # | Item | Esforço | Tipo |
|---|------|---------|------|
| P2 | Inimigos exclusivos do Vulcão | Alto | Conteúdo |
| P1-resíduo | Rotação por recência na cauda da Cidade | Baixo | Tuning |
| P2/Espaço | Mais identidade ao Espaço além do trio genérico | Médio | Conteúdo |
