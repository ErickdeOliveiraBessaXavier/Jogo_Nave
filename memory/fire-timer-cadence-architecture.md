---
name: fire-timer-cadence-architecture
description: Padrão obrigatório de cadência de disparo (FireTimer/carry_interval) e por que `timer = INTERVALO` é proibido
metadata:
  type: project
---

Todo reagendamento periódico usa `game/core/fire_timer.py`. O padrão `timer -= dt; if timer <= 0: agir(); timer = INTERVALO` é **proibido**: ele descarta a sobra do frame, o intervalo real vira um número inteiro de frames e o evento rende MENOS que o configurado (medido: Estilete a 8.5/s em vez de 9.35; rajada do CyberTank 25% lenta a 30fps).

- **`FireTimer`** — armas. Acumula tempo em vez de descontar. `advance(dt, interval)` + `while consume(interval)`. Expõe `overshoot`, que deve ser aplicado como deslocamento inicial do projétil (`bullet.x += bullet.vx * overshoot`) — é o que torna o espaçamento no ar uniforme, e é isso que o olho lê como ritmo. O `while` (não `if`) evita perder disparos quando o intervalo é menor que o `dt`. Usado por ShootingSystem (tiro normal + Berserk), MiniShip, Wingman. Chaves em `WeakKeyDictionary` (nunca `id(ship)` — o CPython reusa endereços).
- **`carry_interval(remaining, interval)`** — eventos periódicos simples de entidade (rajada de inimigo, pulso de área). Usado por CyberTank (gatling) e FusedDrone.

**Não migrar** (avaliado e rejeitado): Alien (FSM com sentinela `inf`), StoneSentry e CyberTank RAILCANNON (o timer também alimenta a animação de carga — `charge_ratio` lê o tempo restante), SpikeBoss e MountainSerpentBoss (evento gated por estado; crédito acumulado dispararia no instante em que o gate abre). Nesses o timer não é cadência.

O `dt` do loop é clampado em `_MAX_FRAME_DT = 1/30` (app.py): abaixo de 30fps o jogo inteiro entra em câmera lenta. Isso é intencional, não é bug de disparo — nunca "corrigir" compensando no sistema de tiro.

Relacionado: [[ship-balance-model]].
