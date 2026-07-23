---
name: city-variety-pyramid-rotation
description: "Regra de design \"pirâmide de N\" — máx. 3 (Normal)/4 (Hard/Pesadelo) variantes de inimigo por nível, com rotação das assinaturas."
metadata: 
  node_type: memory
  type: project
  originSessionId: a533f15b-88b0-43cf-a670-4a2a739d3db7
---

**Regra de design do dono:** nunca mais de **3 variantes de inimigo ativas por
nível** (a "pirâmide de três"); novos inimigos entram gradualmente enquanto os
antigos perdem relevância. Hard/Pesadelo permitem 4.

Implementado em `pipeline._apply_enemy_variety_cap` (P1 "Opção A", jun/2026):

- O cap da banda de estágio (`MAX_ENEMY_VARIETY_BY_STAGE`: early/mid/late) dá a
  rampa inicial; as assinaturas presentes ampliam o cap, **mas o total é clampado
  ao teto rígido `MAX_ENEMY_VARIETY_BY_DIFFICULTY`** (Normal 3, Hard/Pesadelo 4) —
  `cap = min(cap + len(signatures), hard_max)`.
- Seleção quando há excesso: base (`THEME_BASE_ENEMY`, volume) sempre; depois
  assinaturas por loteria ponderada por **recência** (peso `i+1` pela posição na
  tupla `THEME_SIGNATURE_ENEMIES`, ordenada antigo→novo → recém-liberadas
  favorecidas); por fim, vagas restantes pela loteria `1/spawn_time`.
- Seed determinístico por nível (`level*7919 + adler32(theme)`) → o trio
  **rotaciona** entre níveis: variedade alta ENTRE níveis, ≤ teto POR nível.

**Why:** o mecanismo antigo somava as assinaturas ao cap sem clamp; como o CITY
declara 4 assinaturas, o pool chegava a **5 tipos simultâneos** do nível 31 em
diante (estágio 6, quando Captor ≥0.45 e Tank ≥0.55 desbloqueiam juntos),
furando a regra dos 3. Verificado empiricamente via `get_level_config`.

**How to apply:** mantenha a ordem antigo→novo em `THEME_SIGNATURE_ENEMIES`.
Ver [[variety-cap-exclui-specials-raros]] e [[city-neon-design-intent]].

⚠️ **Atualizado em 2026-06-06 (reescrita focada):** os mecanismos citados acima
(`MAX_ENEMY_VARIETY_BY_STAGE`, `MAX_ENEMY_VARIETY_BY_DIFFICULTY`, clamp aditivo,
peso de assinatura por rank `i+1`, loteria `1/spawn_time`) foram REMOVIDOS. Agora
tudo vem do bloco global "ENCOUNTER COMPOSITION CONFIG" em pipeline.py: teto =
`_global_variety_ceiling(|pool|)` (CITY pool 12 → 4 Normal / 5 Hard, sem override),
peso achatado + spotlight que decai + recência forte (janela 3) + `VETERAN_RESERVE`.
A regra "pirâmide" continua valendo como TETO, mas dirigida pelo pool. Empiricamente
o CITY rotaciona as 11 assinaturas equilibradamente (2–6× em 15 níveis). Detalhes em
[[new-theme-specials-gate-after-trio]].
