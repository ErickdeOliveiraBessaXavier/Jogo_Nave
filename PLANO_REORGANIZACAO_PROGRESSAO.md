# PLANO — Reorganização da Progressão (fonte única, sem duplicidade)

Plano temático (§13 do `CLAUDE.md`) para **remover duplicidade e dar fonte única**
ao sistema de progressão de níveis. Não muda balanceamento de propósito; muda
**onde** cada coisa é definida, para que adicionar boss/tema/inimigo seja uma
edição num lugar só.

Origem: análise de 2026-06-06 da relação entre `world_config.py`,
`levels/fixed_levels.py`, `levels/procedural.py` e `levels/pipeline.py`.

---

## Diagnóstico (o que está duplicado/confuso hoje)

1. **Boss sem fonte única.** Três estruturas descrevem bosses e podem discordar:
   - `WorldConfig.boss_level` + `boss_type` → boss **final** (lido em `pipeline.py:894`).
   - `FIXED_LEVELS[n].boss_type` → boss por nível (mid e, no Espaço, o final).
   - `WORLD_BOSS_ROADMAP` → roteiro declarativo, **só validado, nunca lido em runtime**
     (placeholders são *string*, não classe).
   - Consequência: 4 padrões diferentes para "boss final" (Montanha/Cidade/Vulcão via
     `WorldConfig`; Espaço via `FIXED_LEVELS` porque `world.boss_type=None`) e **1 entrada
     morta** — `FIXED_LEVELS[10]` tem adds handcrafted que `pipeline.py:894` ignora
     (o `_create_world_boss_level` vence). Editar esses adds não tem efeito, sem aviso.

2. **`FIXED_LEVELS` acumula dois papéis colados:** (a) colocar/tunar bosses
   (duplica `WorldConfig`/`_create_world_boss_level`) e (b) níveis handcrafted de
   introdução (L1 tutorial, L11 abertura do Espaço). Só (b) é insubstituível — e o
   L11 é largamente reproduzível pela rampa do pipeline (`world_entry_grace=0.70`
   no estágio 1 + variety cap `X-1 → 1 tipo`).

3. **Conhecimento de tema espalhado por ~10 estruturas em 2 arquivos**
   (`pipeline.py`: allowlist, base, fallback, signature, archetype, weight/stage
   profiles; `procedural.py`: `THEME_FEATURES`, `_STAGE_BANDED_THEMES`,
   `_configure_<tema>_spawn`), além de cascatas `if/elif theme` em
   `_create_world_boss_level` (§5 — code smell). Adicionar um tema = ~10 edições.

**O que está BOM e não muda:** a definição de inimigos por tema (allowlist,
base, fallback, signature, archetype) já é praticamente fonte única; o pipeline
declarativo `_THEME_RULES_PIPELINE` é o melhor pedaço — manter. A separação em
camadas (`fixed_levels`=dados / `procedural`=geração / `pipeline`=orquestração)
está certa. O problema é responsabilidade vazando ENTRE camadas, não nº de arquivos.

**Fora de escopo (decisão consciente):** a cascata `if boss_type == X` em
`boss_fight_controller.py:313` (construção do boss) — construtores divergem, §5
permite. Não mexer aqui.

---

## Princípio-guia

Fonte única **por conceito**, não por arquivo:
- **Boss (classe + posição):** um lugar → `WORLD_BOSS_ROADMAP`.
- **Adds do boss-fight:** um lugar → `_create_world_boss_level` (paramétrico por tema).
- **Layout handcrafted de nível não-boss:** um lugar → `FIXED_LEVELS`.
- **Conhecimento de tema:** um lugar por tema → `ThemeProfile` (Fase 3).

Distinguir dois conceitos hoje confundidos:
- `WorldConfig.boss_level` = **nível final do mundo** (transição de mundo;
  `playing.py:2318`). **Permanece.**
- "este nível tem boss?" = `get_boss_for_level(level) is not None` (mid OU final).
  **Conceito novo, resolvedor único.**

---

## Fase 1 — Boss numa fonte única ⭐ (alto valor, custo médio)

Tornar `WORLD_BOSS_ROADMAP` o **driver real** do boss; tirar essa responsabilidade
de `FIXED_LEVELS` e de `WorldConfig.boss_type`.

**Passos (em ordem):**

1. `world_config.py` — `BossSlot` carrega a **classe**, não string:
   - `boss_type: Type[Any]` (a classe que spawna — nativa ou placeholder reusado),
     `status: "implemented"|"placeholder"`, `label: str`. Remover o campo
     `placeholder: str` (vira `boss_type` real).
   - Imports de boss passam a ser necessários no módulo (já há import local em
     `_get_worlds`/`_get_procedural_sector_boss`; consolidar num helper de import
     ou trazer ao topo se não houver ciclo — §10).

2. `world_config.py` — **resolvedor único** `get_boss_for_level(level) -> Optional[Type]`:
   - Mundo nomeado: procura no `WORLD_BOSS_ROADMAP[world_id]` o slot com
     `slot.level == level`; retorna `slot.boss_type` (ou `None`).
   - Procedural: fim de setor (`level == sector_end`) → `_get_procedural_sector_boss`;
     senão `get_procedural_midboss_for_level(level)`. (Já existem; só centralizar.)

3. `world_config.py` — **remover `WorldConfig.boss_type`**. Manter `boss_level`
   (= nível final). A síntese procedural em `get_world_for_level` para de setar
   `boss_type`. Auditar leituras: `pipeline.py:894/832`, `playing.py:1186/2318`,
   `analysis.py`. Trocar leitura de classe por `get_boss_for_level`.

4. `pipeline.py:get_level_config` — unificar mid + final num caminho só:
   ```python
   boss_cls = get_boss_for_level(level_number)
   if boss_cls is not None and not force_meteor_storm:
       config = _create_world_boss_level(world, level_number, difficulty_preset, boss_cls)
       return _apply_theme_enemy_rules(config, world, difficulty_preset)
   ```
   `_create_world_boss_level` ganha o parâmetro `boss_cls` e o usa em vez de
   `world.boss_type`. Remover a injeção de mid-boss procedural feita hoje no ramo
   procedural (passa a ser coberta por este branch único).

5. `fixed_levels.py` — **remover `boss_type` de TODAS as entradas** de `FIXED_LEVELS`
   (1, 3, 6, 10, 11, 12, 16, 20, 25 e as L30/34/37 adicionadas em 2026-06-06).
   Os bosses dessas posições migram para `WORLD_BOSS_ROADMAP` (mundos 1 e 2 já têm
   os slots; conferir que classes batem). As entradas de boss em `FIXED_LEVELS` que
   só existiam para o boss **somem** (L3/6/10/12/16/20/25/30/34/37); sobram apenas
   layouts handcrafted não-boss (ver Fase 2). `LevelConfig.boss_type` **continua**
   como campo (é o contrato lido por `boss_fight_controller.py:129`) — só deixa de
   ser preenchido por literais de `FIXED_LEVELS`.

6. `world_config.py:validate_worlds` — agora o roadmap É a fonte:
   - todo mundo nomeado tem roadmap; `slots[-1].level == world.boss_level`;
     slots dentro do range; `boss_type` é classe válida.

**Tradeoff explícito a aprovar:** os adds handcrafted dos boss-levels existentes
(ex.: L16 = Meteor/Alien/EyeEnemy) passam a vir do `_create_world_boss_level`
(paramétrico por tema). É uma pequena mudança de composição em troca de
consistência total. *Alternativa* se quiser preservar adds exatos: o `BossSlot`
ganha um `enemy_layout: Optional[EnemySpawnConfig]` opcional — mas isso reintroduz
adds em duas fontes; recomendo NÃO fazer salvo necessidade comprovada.

**Definição de pronto:** `get_level_config(n).boss_type` igual ao antes para
L3/6/10/12/16/20/25/30/34/37/40/50; `validate_worlds()` OK; smoke test de boss em
setores procedurais OK; L10 deixa de ter config morta.

---

## Fase 2 — `FIXED_LEVELS` reduzido a handcraft puro (baixo custo)

1. Após Fase 1, `FIXED_LEVELS` = `{1: tutorial, 11: abertura Espaço}` (sem boss).
2. A/B headless: comparar `get_level_config(11)` SEM a entrada fixa (procedural +
   grace + rampa) com a handcrafted. Se equivalente, **remover L11**; manter só L1.
3. Documentar no topo de `fixed_levels.py` a responsabilidade única: "override
   handcrafted de LAYOUT de níveis específicos; bosses vêm do roadmap".

**Definição de pronto:** `FIXED_LEVELS` minúsculo, sem `boss_type`, docstring de
responsabilidade única.

---

## Fase 3 — `ThemeProfile` único por tema (maior valor de escala, maior custo)

Colapsar as ~10 estruturas por tema num objeto por tema. **Fazer isolado**, depois
das fases 1-2, idealmente quando for adicionar um tema novo.

1. `ThemeProfile` (`@dataclass(frozen=True)`) agregando: `base_enemy`,
   `allowlist`, `fallback`, `signature_order`, `features`, `weight_profiles`,
   `stage_profiles`, `boss_fight_adds`.
2. `THEME_PROFILES: dict[WorldTheme, ThemeProfile]`. As tabelas atuais viram
   *views* derivadas (ou são substituídas pelos acessos ao profile).
3. Dissolver a cascata `if/elif theme` de `_create_world_boss_level` (adds do
   boss vêm de `profile.boss_fight_adds`) e o dispatch `_configure_<tema>_spawn`
   (lookup por profile) — alinha com §5.
4. Adicionar tema novo = **um `ThemeProfile`** + entrada em `WORLDS` + slots no
   roadmap. Nada de caçar 10 lugares.

**Definição de pronto:** adicionar um tema fictício de teste exige só 1 profile +
1 world + 1 roadmap; nenhuma cascata `if/elif theme` restante no caminho de spawn.

---

## Ordem recomendada e checkpoints

1. **Commitar primeiro** o trabalho de mid-bosses de 2026-06-06 (já funcional) como
   checkpoint — dá City L30/34/37 jogável hoje. A Fase 1 depois migra essas
   entradas para o roadmap (elas viram redundantes, removidas no passo 1.5).
2. **Fase 1** (resolve diretamente a confusão de bosses; pré-requisito limpo).
3. **Fase 2** (baixo custo, fecha o papel do `FIXED_LEVELS`).
4. **Fase 3** (quando mexer em temas; maior commit, isolado).

## Riscos e mitigação

- **Regressão de composição em boss-levels** (Fase 1, tradeoff): validar headless
  comparando boss_type e adds antes/depois nos 10 níveis de boss.
- **Leituras esquecidas de `boss_type`**: auditadas — `pipeline`, `playing`,
  `analysis`, `boss_fight_controller`, `level_progression_controller`. Conferir
  cada uma ao remover `WorldConfig.boss_type`.
- **Ciclos de import** ao trazer classes de boss para o roadmap: usar o mesmo
  padrão de import local já presente em `world_config.py` (§10).
- Sem suíte de testes hoje (`pytest` não coleta) → cada fase fecha com smoke test
  headless dedicado (`get_level_config` em níveis-chave + `validate_worlds`).

## Não-objetivos

- Não fundir arquivos numa fonte única monolítica (fragmentaria o handcraft).
- Não mexer no balanceamento (pesos/curvas) — só em ONDE as coisas moram.
- Não tocar na construção de boss por classe em `boss_fight_controller` (§5).
