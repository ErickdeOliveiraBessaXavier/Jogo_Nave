# Memória do projeto — Pixel Patrol (Jogo_Nave)

Índice único das notas de contexto persistente. Convenções duráveis vivem no
`CLAUDE.md` (raiz); estas notas são decisões, gotchas e estado de áreas.
Versionado junto com o repositório.

## Arquitetura e código

- [entities-folder-structure](entities-folder-structure.md) — game/entities/ organizado por responsabilidade (player/projectiles/effects/bosses/pickups/_shared) + inimigos por tema (enemies/space|city|mountain); onde colocar arquivo novo e regra dos pontos relativos.
- [scene-decomposition-pattern](scene-decomposition-pattern.md) — extrair fluxos da PlayingScene em sistemas próprios (RevivalSystem/UpgradeSelector); regra do grep-completo ao migrar estado (input handler lê estado cru e quebra com testes verdes).
- [playing-scene-extraction-roadmap](playing-scene-extraction-roadmap.md) — revisão jul/2026: testes de pipeline feitos, cutscene extraída; etapas B/atmosfera, C/P2, D/colisões (última) pendentes + achados da revisão.
- [fire-timer-cadence-architecture](fire-timer-cadence-architecture.md) — cadência de disparo por FireTimer/carry_interval; `timer = INTERVALO` é proibido (descarta a sobra do frame); UM relógio por cadência (dois gates batem); compensação sub-frame por velocidade RELATIVA. Lista o que NÃO migrar.
- [derived-state-vs-event-edge](derived-state-vs-event-edge.md) — estado de objeto que sobrevive à cena (Background no Renderer) é derivado por frame, nunca par ligar/desligar; a borda perdida congelou o ciclo dia/noite depois de morrer no boss fight.
- [targeting-via-target-point](targeting-via-target-point.md) — mira/seleção de inimigo usa target_point + is_targetable (systems/targeting.py), nunca x+w/2; x+w/2 quebra no boss Serpente (bug recorrente).
- [enemy-health-multiplier-propagation](enemy-health-multiplier-propagation.md) — entidades emergentes recebem health_multiplier via construtor, como aggressiveness_multiplier; multiplicador que não chega na entidade é no-op.
- [music-transitions-main-thread](music-transitions-main-thread.md) — crossfade de música roda na thread principal; pygame não é thread-safe (worker thread = access violation).
- [visual-quality-system](visual-quality-system.md) — singleton visual_quality escala efeitos cosméticos por nível Alto/Médio/Baixo; estender efeito = one-liner vq.particles()/gates.
- [render-is-the-frame-budget](render-is-the-frame-budget.md) — render é 93% do frame e o fundo 50% do render; o contador do F3 saturava em 30 (dt clampado); web abre em Médio (-33%); como perfilar sem cair no driver dummy nem no guard de cena-topo.
- [upgrade-cooldown-effect-end](upgrade-cooldown-effect-end.md) — cooldown de upgrade só parte quando o efeito termina; efeito por munição/cargas (base_duration=0) precisa sobrescrever `_effect_still_running` (explosivo/descarga orbital), senão o cooldown parte na ativação.
- [cryo-bomb-cycle](cryo-bomb-cycle.md) — Cryo Shot fecha em bomba de gelo (cargas → cristalizar → estouro → fragmentos); boss cristaliza e detona mas nunca é freado, e os cacos são `Bullet` com `ice_shard`.

## Balanceamento e progressão

- [ship-balance-model](ship-balance-model.md) — balancear naves por abates/s por tier de HP (não DPS bruto); HP de inimigo não escala por nível; não buffar dano de nave lenta; dano por tiro é inteiro, então cadência e poder andam grudados.
- [ship-impact-identity](ship-impact-identity.md) — estilo de impacto por nave só em hits NÃO-letais; giro de matiz do tiro do P2 é 0.08, não 0.5.
- [level-progression-onscreen-visibility](level-progression-onscreen-visibility.md) — avanço de fase só conta hostis VISÍVEIS na tela (teste estrito), não _is_enemy_off_screen.
- [mine-explosion-respected-before-advance](mine-explosion-respected-before-advance.md) — explosões de mina ativas seguram o avanço até a animação/dano terminar.
- [death-animations-respected-before-advance](death-animations-respected-before-advance.md) — avanço espera explosões/implosões cosméticas terminarem, sem tratá-las como hostis.

## Variedade de inimigos (pipeline)

- [swarm-base-and-combination-history](swarm-base-and-combination-history.md) — filosofia "SWARM (base) + N complementares" no teto de variedade + anti-repetição do triângulo entre fases vizinhas.
- [city-variety-pyramid-rotation](city-variety-pyramid-rotation.md) — pirâmide de N: máx. 3 (Normal)/4 (Hard) variantes por nível, com rotação das assinaturas.
- [variety-cap-exclui-specials-raros](variety-cap-exclui-specials-raros.md) — o variety cap exclui inimigos raros (spawn_time alto); garantir via THEME_SIGNATURE_ENEMIES.
- [variety-per-run-salt-and-pending-debut](variety-per-run-salt-and-pending-debut.md) — semente de variedade por-partida + estreia garantida por assinatura (implementadas).
- [new-theme-specials-gate-after-trio](new-theme-specials-gate-after-trio.md) — adicionar inimigo a tema existente: gatear após o trio de introdução + registrar na ordem; resto é automático (config global).

## Inimigos e bosses (temas)

- [boss-single-source-roadmap](boss-single-source-roadmap.md) — classe do boss só em WORLD_BOSS_ROADMAP via get_boss_for_level; nunca em WorldConfig nem FIXED_LEVELS.
- [progression-refactor-closed](progression-refactor-closed.md) — refactor de fonte única de boss ENCERRADO (Fases 1-2 feitas); Fase 3 ThemeProfile adiada até adicionar tema novo.
- [orbital-turret-zoneamento](orbital-turret-zoneamento.md) — OrbitalTurret de zoneamento (olho + 3 esferas, orbes destrutíveis → campos elétricos com paralisia).
- [metropolis-overlord-city-boss](metropolis-overlord-city-boss.md) — 1º boss nativo do CITY (nível 30); FSM escudo vai-e-volta, Fase 2 minas + lasers, Fase 3 segmentação.
- [boss-partes-fora-do-soquete](boss-partes-fora-do-soquete.md) — parte que sai do corpo (Sentença/órbita da Tríade): volta por reencaixe de DESVIO (nunca reatribuir o seno); máscara de união só vale no soquete — fora dele, buffer largo 1×/frame; "para o tiro" ≠ "recebe dano".
- [city-mine-neon-residue](city-mine-neon-residue.md) — CityMine = subclasse ExplosiveMine + flag spawns_neon_residue; secundárias via ExplosiveEffect estendido.
- [city-neon-design-intent](city-neon-design-intent.md) — decisões deliberadas do tema City Neon (Mundo 3, níveis 26-35); não tratar como bugs.

## UI, menus e temas visuais

- [menu-ui-scale-convention](menu-ui-scale-convention.md) — menus e HUD escalam UI por ui_scale = SCREEN_WIDTH/1280 (§12 do CLAUDE.md).
- [controller-first-menu-ux](controller-first-menu-ux.md) — priorizar o jogador de controle nos menus (D-pad focus, realce, sem legenda no rodapé).
- [retro-background-scale-city-only](retro-background-scale-city-only.md) — escala do Fundo Retrô corrigida só no City; volcanic/mountains têm o mesmo desvio mas a estética ampliada é intencional.
- [i18n-translation-system](i18n-translation-system.md) — i18n PT/EN via singleton t() + tabelas por idioma; só o menu convertido, resto pendente.

## Build e web

- [itch-publishing-workflow](itch-publishing-workflow.md) — publicação no itch.io via butler (3 canais: Windows/Linux/Web), versão única em VERSION.
- [web-no-save-persistence](web-no-save-persistence.md) — web não persiste save (MEMFS volátil no emscripten); persistência real é pendente.
- [web-cdn-runtime-firefox](web-cdn-runtime-firefox.md) — RESOLVIDO: o runtime (~21 MB) cortava no Firefox ao vir do pygame-web.github.io; agora é self-hosted no bundle por web_selfhost_runtime.ps1 (build_web.ps1 -Build). COOP/COEP e browserfs.min.js descartados.
