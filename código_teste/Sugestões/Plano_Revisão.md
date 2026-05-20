# Plano de Revisão — Space Shooter

Próximo ciclo de revisão técnica. Item levantado, avaliado, classificado e fechado
quando concluído. O arquivo deve refletir o estado atual — atualize gravidade/status
conforme o trabalho avança.

---

## Escopo

Avaliação focada em código de produção (`game/`) e infraestrutura de build/scripts.
Itens fora do escopo: assets binários, documentos em `código_teste/`, ferramentas
de profiling não usadas em runtime.

---

## Critérios de gravidade

- **Crítico** — viola um princípio do CLAUDE.md (coupling, side-effects em render,
  global state), causa bug observável, ou bloqueia evolução de outra área.
- **Médio** — não bloqueia, mas degrada legibilidade/testabilidade ou ferre
  composição/extensão.
- **Baixo** — polimento, nomenclatura, remoção de comentário redundante.

---

## Backlog

### Crítico

<!-- Adicionar item:
#### 1. <título curto>
**Sintoma:** <o que se observa no código / runtime>
**Causa:** <por que está assim>
**Direção:** <ação concreta, idealmente um trecho before/after>
**Impacto:** <escopo da mudança — arquivos, sistemas afetados>
**Status:** Pendente | Em progresso | Concluído
-->

_(vazio)_

### Médio

_(vazio)_

### Baixo

_(vazio)_

---

## Decisões deliberadamente adiadas

Registre aqui itens válidos que **não** serão executados neste ciclo, com a
justificativa. Evita re-aparecerem como "novidade" em revisões futuras.

<!-- Exemplo:
- **HUD via eventos (`ScoreGained`)** — adiado até a extração do renderer.
  Re-introduzir o evento agora exigiria subscriber com estado próprio + desacoplar
  renderer do scene state. Sem ganho enquanto o HUD for renderizado em `playing.py`.
-->

_(vazio)_

---

## Status resumido

| # | Item | Gravidade | Status |
|---|------|-----------|--------|
| — | — | — | — |

---

## Histórico de ciclos anteriores

Os relatórios `Melhorias_Código_Avaliação.txt`, `_02.txt` e `_03.txt` foram
arquivados após conclusão das ações deles. Resumo do que ficou:

- **PlayingScene god object** — extraídos `BossFightController`,
  `LevelProgressionController`, `ShootingSystem`. Cena reduzida e domínios
  isolados por sua coerência interna.
- **`config.py` namespace global** — substituído por dataclasses `frozen=True`
  por domínio (`DisplayConfig`, `GameplayConfig`, `MeteorConfig`, `AlienConfig`,
  `PowerUpConfig`, `BossConfig` + variantes, `FormationConfig`, `VisualEffectConfig`,
  `ScoringConfig`, `ParticleConfig`), agregadas em `ConfigurationManager`.
- **Event Bus** — refinamentos (off/cleanup, eventos sem uso removidos,
  `LevelCleared` emitido, deduplicação de explosões, double-play do laser Magneto).
- **Resíduos da migração `LevelProgressionController`** — `_base_score_multiplier`
  alias e propriedades de compat (`enemies_destroyed_in_level`, `enemies_to_clear`,
  `has_boss`) removidos; setter `level_config` removido.
