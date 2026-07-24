---
name: playing-scene-extraction-roadmap
description: "Revisão de arquitetura (jul/2026): PlayingScene god-class sendo decomposta em etapas; testes de pipeline feitos; cutscene extraída; P2/atmosfera/colisões pendentes."
metadata:
  node_type: memory
  type: project
---

Revisão crítica de arquitetura + game design (2026-07-24). Dois itens priorizados
como foco: **#1** decompor a `PlayingScene` (god-class) e **#2** testar o pipeline
de progressão. Segue o padrão de extração do §9 / [[scene-decomposition-pattern]].

**#2 — CONCLUÍDO.** `tests/test_pipeline_variety.py` (24 testes): trava o teto do
§11 (`não-ocasionais <= min(estágio, teto)`) em 120 níveis × 4 presets, zero
vazamento de tema, nunca vazio, X-1 abre mundo só com swarm-base, determinismo por
nível + salt de run chega na seleção. Nota: `OCCASIONAL_THREAT` (SquareMinionBoss)
entra FORA do cap por design (`_apply_enemy_variety_cap`) — por isso Normal mostra 4
tipos em L21-24. `_global_variety_ceiling` hoje sempre retorna o teto (floor==max).

**#1 — EM ANDAMENTO. Etapa A feita:** cutscene de transição de mundo extraída para
`game/systems/world_transition_cutscene.py` (`WorldTransitionCutscene`). Cinemática
+ partículas + estado saíram da cena; o FLUXO de conclusão (atmosfera/painel/prep)
ficou como callback `_on_world_cutscene_complete`. Fachada fina: properties
`world_transition_cutscene_timer`/`_thruster_particles` (DTO de render) +
`world_transition_cutscene_active` (derivado do FSM). `ThrusterParticle` mudou para
o novo módulo (re-exportado em `scenes.playing` p/ o TYPE_CHECKING do render_frame).
Teste: `tests/test_world_transition_cutscene.py` (7, com stubs). `playing.py`
2950→2766 linhas.

**Etapa B (atmosfera) — ADIADA (2026-07-24), NÃO é bom alvo.** O mapeamento revelou
acoplamento ALTO (≠ o "baixo-médio" estimado na revisão): os 8 métodos `_*_atmosphere_*`
tocam ~20 pontos em ~10 subsistemas (renderer/spawner/roster/ship/level_controller/
entity_manager + fluxo begin_level_preparation/build_mini_ships/sync_lives/screen_shake/
world_cutscene/apply_pending_world_transition + estado pending_world_transition/
is_side_scroll/popup/difficulty/app.states). E o `AtmosphereState` é lido em 6 outros
pontos da cena. Uma extração §9 (sem referência à cena) exigiria construtor de ~15-18
callbacks → converte acoplamento intra-classe em inter-objeto PIOR (viola §1). Mesma
categoria da Fase 3 do refactor de progressão: adiada por custo>benefício. Retomar só
se a atmosfera ganhar lógica própria que justifique, ou como parte de uma reorganização
maior. Ganho leve possível sem extrair: mover a matemática pura do desmaio/re-entrada +
constantes `_ATMOSPHERE_*` para um módulo.

**Etapa C (sessão do P2) — ✅ CONCLUÍDA (2026-07-24).** `game/systems/p2_session_controller.py`
(`P2SessionController`): entrada/saída/desconexão + spawn/despawn + HUD do co-op, sem
referência à cena. Deps: roster, gamepad, entity_manager + callbacks `set_player_count`
(trio level_controller+enemy_spawner+powerup_spawner, na cena como `_set_active_player_count`),
`open_p2_modal` (o modal fica na cena pois usa `playing_scene` p/ render de fundo + perfil) e
`build_permanent_mini_ships`. `handle_event` delega via `try_handle_event(event)->bool`;
`_build_render_frame` usa `build_hud_info()`; a init (P2 sobrevive ao Continuar) chama
`spawn_p2`. Teste: `tests/test_p2_session_controller.py` (8, com stubs). `playing.py`
2737 linhas (−165 nesta etapa; ~2950→2737 no total do #1 até aqui).

**Etapa D (colisões) — ✅ CONCLUÍDA (2026-07-24) via result-DTO.**
`game/systems/collision_orchestrator.py` (`CollisionOrchestrator` + `CollisionResult`):
roda todos os passes de colisão do frame e RETORNA (score_gain já multiplicado,
enemies_destroyed, floating_scores prontos); a cena APLICA. Inverte o padrão do
RenderFrame. Ship-hits roteados via callback `on_ship_hit` DURANTE o run (imediato —
preserva ordem/invuln entre fontes de dano no mesmo frame); score/kills/floating são
diferidos ao resultado (ordem irrelevante). Deps: entity_manager, collisions, roster,
boss_controller, level_controller + acessores get_last_dt/get_multiplier_state/
get_batch_threshold. Truque de transcrição: campos nomeados IGUAIS aos da cena
(`self.entity_manager`/`collisions`/`roster`/`boss_controller`/`level_controller`)
p/ os ~180 usos ficarem verbatim; só mudaram `_handle_ship_hit`→`_on_ship_hit` e os
acessores. Quirk preservado: spike usa só o bônus (sem base multiplier). Teste:
`tests/test_collision_orchestrator.py` (6: multiplicador, batching, smoke run() com
EntityManager real). `playing.py` **2111 linhas** (−626 nesta etapa).

**#1 ENCERRADO (2026-07-24):** god-class **2950 → 2111** (−839, −28%). Extraídas A
(cutscene), C (P2), D (colisões); B (atmosfera) adiada de propósito (acoplamento alto,
§1). Sobra na cena: fluxo de transição/atmosfera, upgrades, powerups, timers, init — o
núcleo de coordenação, que é papel legítimo da cena. Não há mais bloco grande
extraível com ganho > custo.

**Outros achados da revisão (não priorizados ainda):** acessibilidade (sem daltônico
nem escala de shake/flash), `EventBus.emit` engole exceção com `print`, sem
onboarding/tutorial, diretórios mortos `Inimigos_Tema_Espaco/`+`Inimigos_Tema_Cidade/`
(só `__pycache__`), commits vagos. Bosses gigantes (2000-2580 linhas) são OK por §1
(não extrair). Colisões é coeso (uma classe, ~50 passes) apesar do tamanho.
