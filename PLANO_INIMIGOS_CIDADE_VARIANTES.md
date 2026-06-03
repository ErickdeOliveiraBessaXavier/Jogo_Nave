# PLANO — Variantes de Inimigos do Bioma CITY

Plano temático (§13 do `CLAUDE.md`) para a **2ª leva de inimigos da CITY**:
variantes que estendem as 6 unidades do `PROPOSTA_INIMIGOS_CIDADE.md` (todas já
implementadas), preenchendo **nichos mecânicos ainda não cobertos**.

Roster atual cobre: enxame, sniper de linha, perseguidor de dash, colosso tanky,
armadilha orbital, parede vertical e mini-chefe de fusão. Faltam os nichos
abaixo.

---

## Catálogo das variantes

| # | Variante | Linhagem | Nicho inédito na CITY | Esforço |
|---|----------|----------|------------------------|---------|
| 1 | **Jammer Node** (Glitch simpl.) | Cyber-Captor | suprime os tiros da nave numa área | Baixo |
| 2 | **Artilheiro** | Neon Sniper | AoE telegrafada (negação de área) | Baixo-Médio |
| 3 | **Escudeiro** (Riot Van) | Police Interceptor | escudo móvel que protege aliados | Médio |
| 4 | **Splitter Tank** | Cyber Tank | multiplica em unidades menores na morte | Médio |
| 5 | **Rebocador** (Sapper) | City Drone | cura/blindagem de aliados | Médio-Alto |
| 6 | **Refletor** (Mirror Pylon) | Tesla Twins | reflete projéteis da nave | Alto |

### Glitch → "Jammer Node" (simplificado)
O Glitch original (inverter controles, embaralhar HUD, desativar powerup) foi
**descartado por complexidade** (mexia em input/HUD/powerups + restauração
temporizada + coop). Substituído por: **nó que anula a ofensiva numa região**.
- **Movimento:** *Orbiting* (orbita um ponto no alto; não desce).
- **Campo estático circular:** tiros da nave que entram nele **fizzlam** (somem),
  reusando a mecânica de bloqueio do feixe do Tesla generalizada (Fase 0).
- **Counterplay:** reposicionar para atirar de um ângulo livre, ou furar o nó.
- **Morte:** *EMP pop* curto (reusa `CaptorEMP`/`_trigger_captor_emp`).
- **Custo:** zero toque em input/HUD/powerup.

---

## Fase 0 — Infra compartilhada: bloqueio de projétil genérico ✅
Jammer, Escudeiro e Refletor precisam interferir nos tiros da nave. Generalizar
o que estava hardcoded como `projectiles_vs_tesla_beams`:
- `collisions.py`: passe único `projectiles_vs_blocker_fields`, duck-typed (§5),
  consumindo `enemy.projectile_fields()` que retorna formas tagueadas
  (`("seg", ...)` / `("circle", ...)`).
- `tesla_twin.py`: migrar `active_beam_segment()` → `projectile_fields()`.
- `playing.py`: atualizar a chamada (já roda antes de `projectiles_vs_enemies`).
- **Validação:** Tesla continua bloqueando (regressão zero). ✅

## Esqueleto comum (cada variante repete)
1. `*_pixel_map.py` — sprite em camadas, surface cacheada (§7).
2. Classe em `Inimigos_Tema_Cidade/` herda `EnemyHitMixin`; `update_in_context`
   (§5), `collision_circle`, `on_hit`/`take_damage` (§8), `draw` (§3).
3. Coordenador opcional (padrão `ChannelingGroup`/`TeslaLink`, §1) se houver
   comportamento de grupo (Rebocador, Escudeiro).
4. Integração no `spawner.py`: import, alias em `_enemy_type_key`, contagem em
   `_count_enemies_by_type`, `SPAWNER_CAP_*` + `_is_hard_capped`/
   `_should_spawn_enemy`, entrada em `MIN_SPAWN_GAP_BY_TYPE`, `_spawn_*` +
   dispatch em `_spawn_enemy_of_type`.
5. Pesos de aparição CITY no `pipeline.py`.
6. `EntityManager`: efeito de morte especial e/ou novos buffers, se necessário.
7. Validação headless (importa, spawna, caps não estouram; 720p/1080p §12).

---

## Fases por variante (ordem de execução)

### Fase 1 — Jammer Node  ✅
Reusa Fase 0 (campo circular), órbita do Captor e `CaptorEMP` na morte.
- [x] Fase 0 (infra de bloqueio genérico)
- [x] `jammer_node_pixel_map.py` (nó octogonal, núcleo magenta, 4 antenas)
- [x] classe `JammerNode` (órbita, campo com flicker glitch, EMP pop na morte)
- [x] integração spawner/pipeline (cap 2, gate 0.45, signature CITY)
- [x] validação headless (spawn, bloqueio de tiro, aparição CITY late, draw, EMP)

### Fase 2 — Artilheiro (MortarDrone)  ✅
Perch no alto + bombardeio de área telegrafado: durante o *aim* desenha o círculo
no chão, ao fim detona `ctx.new_area_blasts` + `ctx.new_explosions` (sem infra
nova). Acento laranja. Gate 0.35, cap 2.

### Fase 3 — Escudeiro (RiotVan)  ✅
Furgão que avança com escudo frontal (segmento via Fase 0) bloqueando tiros e
protegendo aliados atrás. Counterplay: flanquear por cima/baixo. Gate 0.55, cap 1.

### Fase 4 — Splitter Tank  ✅
Juggernaut que se parte em 3 unidades menores (tier 1) na morte, via
`triggers_special_death` → `trigger_death_sequence` (empurra filhos em `enemies`).
Costura de fratura que pisca conforme ferido. Gate 0.55, cap 1 (conta filhos).

### Fase 5 — Rebocador (SapperDrone)  ✅
Suporte: engata cabo num aliado e injeta HP de blindagem (overheal) até teto por
alvo. Incremento direto de `health` (público, §1). Núcleo verde-ciano. Gate 0.45,
cap 2.

### Fase 6 — Refletor (MirrorPylon)  ✅
Pilar com face espelhada frontal que **reflete** tiros: novo passe
`Collisions.projectiles_vs_reflectors` mata o projétil e gera um `NeonBolt`
inimigo de volta (espalhamento conforme onde acertou). Contrato duck-typed
`reflect_field()`. Counterplay: flanquear. Gate 0.55, cap 1.

---

## Status: todas as 6 variantes implementadas ✅
Validação por sanity de compilação + spawn/mecânica individual + cobertura. Todas
aparecem na **CITY procedural** (46+). **Pendente para a fase de testes/tuning:**

- **Distribuição no mundo handcrafted (26–35):** com 10 assinaturas CITY
  disputando ~2 vagas/nível (variety cap 3, determinístico por nível), algumas
  variantes novas não caem nos 10 níveis handcrafted (ex.: Jammer não apareceu em
  26–35 no NORMAL). São alcançáveis na CITY procedural, mas a 1ª passada pelo
  mundo CITY mostra só um subconjunto. Tuning a considerar: subir o variety cap
  da CITY late, reordenar/gatear assinaturas, ou aceitar a rotação.
- **Playtest de feel/balanceamento** de cada variante (HP, gates, raios, cadência,
  flicker do Jammer, teto do Sapper, velocidade do bolt refletido).
- **Validação headless 576p/720p/1080p** (UI/posições, §12) e regressão geral.
- Atualizar `PROPOSTA_INIMIGOS_CIDADE.md` com as 6 no formato do catálogo.

---

## Marcos de validação
- Após Fase 0: partida CITY confirma Tesla ainda bloqueia. ✅
- Após cada variante: headless spawn + 720p/1080p (UI/posições, §12) + checar
  caps (não estoura tela) + regressão das fases anteriores.

## Decisões registradas
- Glitch simplificado para Jammer Node (ver acima) — fantasia de "interferência"
  sem mexer em input/HUD/powerup.
- Ordem por reuso + dependência: Jammer e Artilheiro primeiro (validam infra e
  reuso de zonas); Refletor por último (reflexão é a mecânica mais arriscada).
