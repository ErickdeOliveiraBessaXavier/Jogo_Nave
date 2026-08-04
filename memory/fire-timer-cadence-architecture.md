---
name: fire-timer-cadence-architecture
description: Padrão obrigatório de cadência de disparo (FireTimer/carry_interval), por que `timer = INTERVALO` é proibido, por que só pode haver UM relógio por cadência e como se compensa a emissão sub-frame
metadata:
  type: project
---

Todo reagendamento periódico usa `game/core/fire_timer.py`. O padrão `timer -= dt; if timer <= 0: agir(); timer = INTERVALO` é **proibido**: ele descarta a sobra do frame, o intervalo real vira um número inteiro de frames e o evento rende MENOS que o configurado (medido: Estilete a 8.5/s em vez de 9.35 — na época em que ele era `fire_rate_mult=1.87`, hoje 1.60; rajada do CyberTank 25% lenta a 30fps).

- **`FireTimer`** — armas. Acumula tempo em vez de descontar. `advance(dt, interval)` + `while consume(interval)`. Expõe `overshoot`, que deve virar deslocamento inicial do projétil via `emission_offset` — é o que torna o espaçamento no ar uniforme, e é isso que o olho lê como ritmo. O `while` (não `if`) evita perder disparos quando o intervalo é menor que o `dt`. Usado por ShootingSystem (tiro normal + Berserk), MiniShip, Wingman. Chaves em `WeakKeyDictionary` (nunca `id(ship)` — o CPython reusa endereços).
- **`emission_offset(v_proj, v_emissor, overshoot)`** — velocidade **RELATIVA**, não a do projétil sozinha. O emissor também estava em outro lugar quando o tiro era devido; compensar só o projétil corrige o eixo de voo e deixa o eixo do movimento do emissor com o mesmo erro de quantização (o defeito original girado 90°). Medido no Estilete em strafe: 4,2% de variação a 60fps e 8,4% a 30fps → **0,00px**. Com emissor parado degenera na fórmula antiga. A `Ship` publica a própria velocidade em `emit_velocity`, medida por Δposição/dt numa casca em volta de `_move_impl` — casca e não linha no fim, porque dash e stun têm `return` antecipado, e **medida** e não derivada do input, porque `_keep_in_bounds` clampa depois (na borda da tela a nave não anda, e derivar do input jogaria a bala para fora dela).
- **`carry_interval(remaining, interval)`** — eventos periódicos simples de entidade (rajada de inimigo, pulso de área). Usado por CyberTank (gatling) e FusedDrone.

**Um relógio por cadência.** Nunca empilhar um segundo gate periódico sobre o `FireTimer`: dois gates independentes não se somam, eles **batem** — o tiro só sai quando as duas janelas coincidem no frame, e a cadência real vira o batimento. O auto-fire tinha um relógio próprio (janela de 1 frame a cada 0,1s, com o `timer = 0` proibido) e cobrava de todo o elenco: Estilete 8,00/s rendendo 5,71/s, Padrão 5,00→4,29, Aríete/Caçador 3,75→2,86. Só o Estilete ficava **irregular** (vãos alternando 7 e 14 frames — pares colados com vão dobrado), porque a razão entre a cadência dele e a janela era a única a cair numa alternância 2:1; nas outras o batimento só cobrava cadência sem quebrar o ritmo, e por isso o sintoma parecia ser "da nave". Gatilho diz **se**; o `FireTimer` diz **quando**.

**Gastar o timer sem ler o `overshoot` não avisa.** `fire_berserk` consumiu e descartou o valor por todo o tempo em que existiu — a Estrela Espiral saía sem compensação alguma enquanto o `fire()` ao lado compensava. Varrido por `test_conventions.test_quem_consome_firetimer_compensa_a_emissao`; allowlist hoje: `Wingman` e `MiniShip` (miram alvo móvel, não formam fila visível de projéteis).

Resíduo conhecido e aceito: com `dt` **irregular** sobram ~2,2px de variação, porque o projétil recém-nascido também leva um `dt` inteiro no `entity_manager.update` do frame em que nasce (com `dt` constante o extra é igual para todos e some). Descontar esse `dt` zera o resíduo, mas acoplaria a matemática à ordem do loop; e é ruído, não o padrão periódico que o olho pega. Travado em `test_dt_irregular_fica_no_limite_fisico`, com limite derivado da física.

**Não migrar** (avaliado e rejeitado): Alien (FSM com sentinela `inf`), StoneSentry e CyberTank RAILCANNON (o timer também alimenta a animação de carga — `charge_ratio` lê o tempo restante), SpikeBoss e MountainSerpentBoss (evento gated por estado; crédito acumulado dispararia no instante em que o gate abre). Nesses o timer não é cadência.

O `dt` do loop é clampado em `_MAX_FRAME_DT = 1/30` (app.py): abaixo de 30fps o jogo inteiro entra em câmera lenta. Isso é intencional, não é bug de disparo — nunca "corrigir" compensando no sistema de tiro.

Relacionado: [[ship-balance-model]].
