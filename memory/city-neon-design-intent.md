---
name: city-neon-design-intent
description: "Decisões de design deliberadas do tema City Neon (Mundo 3, níveis 26-35) — não tratar como bugs de balanceamento."
metadata: 
  node_type: memory
  type: project
  originSessionId: a533f15b-88b0-43cf-a670-4a2a739d3db7
---

Esclarecimentos do dono na revisão de balanceamento do CITY (jun/2026). São
**escolhas deliberadas**, não problemas a corrigir:

- **Boss = `GiantMeteorBoss` é provisório.** Os bosses próprios da City Neon
  ainda não foram desenvolvidos; reusa o do Mundo 2 até implementar os dele.
  (Marcado como provisório em `world_config.py`.)
- **Abertura magra é intencional.** Níveis 26-29 com só 2 tipos (Drone + Sniper)
  é proposital: introduzir cada mundo gradualmente, controlar a curva e evitar
  picos abruptos no início — mesmo assumindo jogador já experiente.
- **FusedDrone flat por design.** Não escala por estágio (mesmo em L26 e L35) de
  propósito. (Agora escala com a dificuldade na vida-**base** via
  [[enemy-health-multiplier-propagation]], mas continua sem escalar por estágio.)
- **Arquétipo de "suporte" (buff/escudo/cura de aliados) é lacuna conhecida e
  planejada** para etapa futura — a canalização Drone→FusedDrone é auto-evolução,
  não suporte a terceiros.

Papéis atuais bem diferenciados (sem redundância grave): Drone=volume,
Sniper=pressão à distância, Police=perseguição/dash, Captor=controle/lock,
Tank=elite/mini-boss, FusedDrone=elite emergente, **TeslaTwin=barreira/negação
de espaço**. Regra de variedade em [[city-variety-pyramid-rotation]].

**Tesla Twins** (6º inimigo, implementado jun/2026): par "Barreira Vertical"
(gêmeos topo+base ligados por arco vertical via `TeslaLink`, §1). Feixe sempre
ON sem brecha → counterplay é **abater um gêmeo** (dispara "Short Circuit": o
sobrevivente sobrecarrega vermelho, cospe bolts 2s e se autodestrói). Avança p/
a esquerda como parede. Gate 0.45 (meio do mundo, junto do Captor); cap = 1 par
(`SPAWNER_CAP_TESLA_TWIN=2`). Dano do feixe via `area_blast` (roteador de
explosão de mina). Autodestruição usa o buffer `ctx.new_explosions` (mecanismo
genérico novo: entidade pede explosão no próprio update, drenado pelo
EntityManager via `spawn_explosion` — para mortes sem `on_hit`).
