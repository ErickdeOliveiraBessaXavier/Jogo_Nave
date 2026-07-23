---
name: orbital-turret-zoneamento
description: "OrbitalTurret reformulado como inimigo de zoneamento (olho + 3 esferas, orbes destrutíveis → campos elétricos com debuff de paralisia)"
metadata: 
  node_type: memory
  type: project
  originSessionId: b9628b84-e528-473b-9fa6-47100ee0a764
---

`OrbitalTurret` (STARFIELD) foi reformulado de "sniper de rajada de plasma" para
inimigo de **negação de espaço**.

**Visual/colisão:** núcleo = olho energético (pixel-map em `orbital_turret_pixel_map.py`,
camadas `hull`/`eye`, pupila rastreia o jogador) orbitado por **3 esferas elétricas**
procedurais (arcos/cintilação/estática). Colisão pela silhueta real via
`collision_circles()` = olho + 3 esferas (não hitbox genérica). SIZE subiu 44→88.

**Ataque:** as 3 esferas carregam **em sequência** e disparam **uma a uma**
(`OrbitalEnergyOrb`, em `orbital_energy_orb.py`). O orbe **memoriza a posição do
jogador no disparo** e viaja em linha reta até lá (não persegue). É **destrutível**
pelos tiros da nave (`Collisions.player_shots_vs_orbital_orbs` — balas por rect,
laser por ponto-segmento).

**Campo:** orbe que sobrevive e chega ao ponto vira `ElectricFieldZone`
(`electric_field_zone.py`), com 3 fases — `expand` (telegrama, sem dano) →
`active` (~2.5s de dano contínuo + debuff) → `dissipate` (~0.7s, encolhe/enfraquece,
sem dano). Só `active` (`damaging`) fere.

**Debuff de paralisia (na `Ship`):** `electric_debuff_timer` (10s "carregado") +
`electric_stun_timer` (movimento travado, 1.5–3s). Enquanto carregado, rola a cada
0.5s 15% de chance de descarga que paralisa. Movimento bloqueado em
`ship_movement.move`/`try_dash`; rolagem em `ship_powerups._update_electric_debuff`;
feedback visual distinto em `ship_renderer._draw_electric_debuff` (crepitação leve vs
gaiola intensa).

**Arquitetura:** orbes e campos são listas próprias no `EntityManager`
(`orbital_orbs`/`electric_fields`), NÃO entram em `enemies` — assim não seguram a
progressão de fase (que só conta hostis em `enemies`/formations/boulders). Emissão
via buffer do contexto `EnemyUpdateContext.new_orbital_orbs`; conversão orbe→campo
em `EntityManager._update_orbital_orbs`. Campo aplica dano à nave via
`Collisions.electric_fields_vs_ships` (molde do `fire_zones_vs_entities`, retorna
`ship_hits`). Ver [[level-progression-onscreen-visibility]].
