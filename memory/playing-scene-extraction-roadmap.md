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

**Etapas pendentes do #1 (ordem):** B) interstício de atmosfera (`_*_atmosphere_*`,
~230 linhas, acoplamento baixo-médio); C) sessão do P2 (`_is_p2_*`/`_spawn_p2`/
modal, médio); D) orquestração de colisões (`_check_*`/`_handle_collisions`, ~600
linhas, ALTO acoplamento — **deixar por último**, com a rede de testes reforçada).

**Outros achados da revisão (não priorizados ainda):** acessibilidade (sem daltônico
nem escala de shake/flash), `EventBus.emit` engole exceção com `print`, sem
onboarding/tutorial, diretórios mortos `Inimigos_Tema_Espaco/`+`Inimigos_Tema_Cidade/`
(só `__pycache__`), commits vagos. Bosses gigantes (2000-2580 linhas) são OK por §1
(não extrair). Colisões é coeso (uma classe, ~50 passes) apesar do tamanho.
