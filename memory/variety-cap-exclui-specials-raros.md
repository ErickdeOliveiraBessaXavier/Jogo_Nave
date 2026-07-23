---
name: variety-cap-exclui-specials-raros
description: O variety cap do pipeline procedural exclui inimigos raros (spawn_time alto); use THEME_SIGNATURE_ENEMIES para garantir.
metadata: 
  node_type: memory
  type: project
  originSessionId: 7be3c0a8-500b-43ab-abb2-7949ea3e47a7
---

Ao adicionar um inimigo **especial/raro** a um tema, registrá-lo nas tabelas
(allowlist, pesos, `_configure_*_spawn`) **não basta** para ele aparecer no jogo.

`pipeline._apply_enemy_variety_cap` corta o pool de cada nível para N tipos
(`MAX_ENEMY_VARIETY_BY_STAGE`: Normal = early 1 / mid 2 / late 3) e escolhe os
tipos por **loteria ponderada em `1/spawn_time`**. Inimigo raro = `spawn_time`
alto = peso minúsculo → quase nunca sobrevive ao corte. Só o `THEME_BASE_ENEMY`
do tema é garantido.

**Why:** o Neon Sniper (CITY) não aparecia mesmo configurado — peso ~50-100×
menor que Alien/Meteor o eliminava do pool em todo nível.

**How to apply:** para um special "assinatura" do tema, adicione-o em
`pipeline.THEME_SIGNATURE_ENEMIES[tema] = (Classe, ...)`. **ORDEM IMPORTA**: a
tupla vai do mais antigo (desbloqueado cedo) ao mais novo (tarde) — o índice é
usado como peso de recência na rotação. O variety cap dá **prioridade** às
assinaturas sobre a loteria, mas **respeita o teto rígido** (ver
[[city-variety-pyramid-rotation]]) — não é mais puramente aditivo (mudou em jun/2026).
E configure um `spawn_time` direto e sadio (ex.: 10–15s), nunca a fórmula
`base*(2/weight)` com tier "strong" + unlock tardio, que explode para >200s.
A frequência em tela é controlada pelo cap do spawner (`SPAWNER_CAP_*`), não por
um spawn_time gigante. Ver também [[death-animations-respected-before-advance]].

⚠️ **Atualizado em 2026-06-06:** o modelo de seleção foi centralizado/reescrito
(bloco "ENCOUNTER COMPOSITION CONFIG" em pipeline.py). NÃO existe mais loteria
`1/spawn_time` (peso agora é achatado/baseline), nem `MAX_ENEMY_VARIETY_BY_STAGE`
ou prioridade permanente de assinatura. O teto é global dirigido pelo pool e a
assinatura recebe **spotlight que decai**. O essencial deste memo continua válido:
registrar em `THEME_SIGNATURE_ENEMIES` (ordem de introdução) + spawn_time direto.
Detalhes em [[new-theme-specials-gate-after-trio]].
