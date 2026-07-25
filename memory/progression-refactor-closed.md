---
name: progression-refactor-closed
description: "Refactor de progressão (fonte única de boss) ENCERRADO; Fase 3 ThemeProfile adiada de propósito — forcing function é adicionar tema novo."
metadata:
  node_type: memory
  type: project
---

O `PLANO_REORGANIZACAO_PROGRESSAO.md` foi **encerrado e apagado** em 2026-07-24
(decisão do usuário). Resumo do que ficou:

**Concluído (verificado no código, 2026-07-24):**
- **Fase 1 — boss em fonte única.** `get_boss_for_level(level)` em
  `world_config.py:307` é o resolvedor único (mid+final, nomeado+procedural).
  `WorldConfig.boss_type` foi removido; `boss_level` (= nível final) permanece. O
  `boss_type` que sobra em `boss_fight_controller.py` é contrato de runtime,
  legítimo. `pipeline.get_level_config` usa o branch único de boss. Ver
  [[boss-single-source-roadmap]].
- **Fase 2 — `FIXED_LEVELS` como handcraft puro.** Sem `boss_type` em nenhuma
  entrada; classe do boss vem do roadmap. L10 morto consertado.

**Fase 3 (`ThemeProfile` único por tema) — ADIADA DE PROPÓSITO, não é dívida.**
Colapsaria ~10 estruturas de peso/spawn por tema num objeto único e dissolveria
duas cascatas ainda de pé:
- `_create_world_boss_level` (`pipeline.py:1133`) — 4 ramos, cada um só um dict
  de adds por tema (divergência rasa e real).
- dispatch `_configure_<tema>_spawn` (`procedural.py:971-998`) — 4 chamadas com
  **assinaturas diferentes** (mountains/starfield recebem `stage_number`; city
  não). Não é dispatch uniforme mascarado.

Por que fica adiada: (1) não é bug nem bloqueio, é infra especulativa p/ escala;
(2) risco de regressão sutil de balanceamento (colapsa ~10 tabelas de peso),
invisível em teste manual; (3) `CLAUDE.md §5` permite as cascatas atuais —
construtores/assinaturas realmente divergem. **Forcing function para retomar:
quando for adicionar um tema novo.** Aí a Fase 3 se paga (adicionar tema = 1
profile + 1 world + 1 slot no roadmap, em vez de caçar ~10 lugares).

Relacionado: [[new-theme-specials-gate-after-trio]] (o outro lado de "adicionar
tema/inimigo"), [[swarm-base-and-combination-history]].
