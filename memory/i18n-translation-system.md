---
name: i18n-translation-system
description: "Sistema de tradução (i18n) PT/EN — singleton t(), tabelas por idioma, tela de escolha no 1º boot; como estender às demais telas"
metadata: 
  node_type: memory
  type: project
  originSessionId: 90d01301-68d5-453d-97b9-33906a995d32
---

Sistema de idioma PT/EN (fundação — Fase 1+2 de um plano faseado). Padrão do
projeto: singleton mutável aplicado no boot, lido por frame.

**Arquitetura:**
- `game/core/i18n.py` — singleton `i18n` + função livre `t(key, **kwargs)`.
  Fallback em cascata: idioma atual → base (`DEFAULT_LANGUAGE="pt"`) → a própria
  chave (chave crua na tela = tradução faltando). `t` interpola via `str.format`.
- `game/core/translations/` — pacote: `pt.py` (`PT`), `en.py` (`EN`), `__init__`
  expõe `TABLES`, `LANGUAGES` (lista `(código, rótulo nativo)`), `DEFAULT_LANGUAGE`.
  Chaves no formato `area.item` (ex.: `menu.start`). Nomes próprios ("Pixel
  Patrol") NÃO se traduzem. Toda chave DEVE existir nos dois dicts (paridade).

**Uso (one-liner por call site):** `from ..core.i18n import t` → `t("menu.start")`.
Importar em `core/*`/`scenes/*`/`entities/*` não cria ciclo.

**Persistência/boot:** `UserPreferences.language` (`""` = ainda não escolhido →
dispara a tela de idioma). `app.py` chama `i18n.set_language(prefs.language or
"pt")` no boot (perto de visual_quality), ANTES de montar cenas. Em seguida
decide a cena inicial: `language in ("pt","en")` → `MainMenuScene`, senão
`LanguageSelectionScene` (`game/scenes/language_selection.py`, bilíngue/neutra;
ao confirmar salva pref + `set_language` + `switch(MainMenuScene)`).

**GOTCHA — troca ao vivo:** os menus PRÉ-RENDERIZAM glifos por caractere na
construção (ex.: `Button.glyphs_*` em main_menu). Trocar idioma em runtime exige
remontar. Decisão: escolher no 1º boot; trocar depois deve reusar o popup de
"reiniciar p/ aplicar" (padrão da troca de resolução em settings). Seletor de
idioma no Settings ainda NÃO existe — é a próxima fase.

**Helpers extra:** `fmt_num(n)` / `i18n.format_number(n)` — separador de milhar
por idioma (PT `.`, EN `,`); usar em score/contadores. `t_or(key, default)` /
`i18n.has(key)` — traduz com fallback a um default externo (dados dinâmicos sem
chave, ex.: mundos procedurais). Namespace `common.*` para palavras reusadas
(back/continue/settings/menu/yes/no/ok).

**GOTCHAs de conversão:** (1) variável local chamada `t` sombreia o
`from ..core.i18n import t` (achado em `statistics._render_high_scores_tab`:
`t = pygame.time.get_ticks()` tornava TODO `t(...)` da função unbound local →
crash). Renomear a local. (2) placeholder de interpolação NÃO pode se chamar
`{key}` — colide com o 1º parâmetro `key` de `t(key, **kwargs)` (achado nas
ability lines do upgrades). Usei `{keys}`.

**Estado da migração (varredura em andamento):** CONVERTIDAS: menu principal,
`paused`, `game_over` (widget de iniciais incluso), `controls_modal`,
`difficulty_selection`, `settings` (incl. popups/toggles/controles),
`world_selection` (chrome + nomes/desc dos 4 mundos via `world.<id>.name|desc`
lidos no `WorldCard` com `t_or` p/ fallback dos procedurais), `statistics`
(3 abas + filtros + dialog; `StatTab` teve os `.value` trocados p/ IDs estáveis
`overview/levels/high_scores`, rótulo via `_TAB_LABEL_KEYS`; dificuldade via
`_difficulty_label`). Dados de dificuldade exibidos via `t(f"difficulty.
{preset.value}.name|desc")` (dict `PRESETS` mantém PT mas a UI ignora; `.value`
estável p/ save). Também CONVERTIDAS: `world_transition` (stages + nome/desc do
mundo via `t_or`), `p2_ship_select` (título + dicas), `upgrades_selection`
(título, headers Arsenal/Estoque/Hangar/Atributos, barras, stat labels, ability
lines dinâmicas, tooltip stat lines, floating messages, saldo, back). CATÁLOGO DE
DADOS convertido via helpers nos módulos de dados (traduzem no display, dados PT
ficam como fallback via `t_or`): `core/ship_types.py` → `ship_display_name`,
`ship_tags` (map `_TAG_KEYS` PT→slug `ship.tag.*`), `format_ship_description`
(desc `ship.<id>.desc` + tokens `ship.token.*`); nomes de upgrade (`meta.name`
tipo "SHLD/HEAL/EMP") são CÓDIGOS, ficam sem traduzir — só `upgrade_desc(meta)`
= `upgrade.<icon_id>.desc`; recomendações em `meta_progression._generate_
recommendations` via `stats.rec.*` (gerado por frame, live). `ship_types`/`upgrades`
importam i18n (sem ciclo — i18n só importa translations). HUD convertido em
`render/renderer.py` (`hud.*`): score/lives/enemies/stage/difficulty + linhas de
efeito + "COMBATE!"/"DIFICULDADE:" do preparation. Templates com `{}` posicional
(score/lives/enemies) passam por `_render_text_cached` que faz `.format(valor)`;
`t("hud.score")` devolve "Pontos: {}" e o helper formata. `game_renderer.py` NÃO
precisou de tradução: labels de `POWERUP_UI_DATA` não são renderizados (só
symbol/color), e "WARNING!"/"PRESS START"/"ALTITUDE"/"RE-ENTRY"/"P2" são inglês
estilizado já usado no build PT (mantidos). Placeholder de segundos é `{sec}`
(não `{t}`, que colidiria). Gotcha do `t` local reincidiu em `renderer.preparation`
(`t = get_ticks()`) e no closure `line` — renomeados p/ `anim_t`/`surf`. FALTA
só: textos de boss (entities). Ao concluir, adicionar teste automatizado de
paridade PT/EN. Ver [[visual-quality-system]].
