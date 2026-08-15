---
name: upgrade-cooldown-effect-end
description: Cooldown de upgrade só parte quando o efeito TERMINA; efeito por munição/cargas (base_duration=0) precisa sobrescrever _effect_still_running, senão o cooldown parte na ativação.
metadata:
  type: project
---

Regra: o cooldown de um `ActiveUpgrade` (`game/core/upgrades.py`) só começa
quando o efeito **termina de fato**, nunca na ativação — a recarga vem DEPOIS da
duração, não em paralelo (ver `activate()` + `update()`).

O `update()` da classe base decide o fim do efeito por um hook
**`_effect_still_running(ctx)`** (default: `duration_left > 0.0`, temporal). O
cooldown parte no tick em que esse hook vira False.

**Gotcha (corrigido nesta sessão):** upgrades cujo efeito é medido em
**munição/cargas**, não em tempo, têm `base_duration=0`. Sem override, o hook
default vê `duration_left==0` já no 1º tick e **dispara o cooldown na ativação**,
enquanto o jogador ainda gasta as balas. Foi o bug reportado no **tiro explosivo**
(`EXPLOSIVE_SHOT`) e na **Descarga Orbital** (`ORBITAL_DISCHARGE`, ex-`LASER_SHOT`).

Correção: cada um sobrescreve `_effect_still_running` para consultar o estado
REAL da nave:
- `ExplosiveShotUpgrade` → `ship.explosive_shots_active` (cai em
  `consume_explosive_shot` ao gastar a 15ª bala).
- `OrbitalDischargeUpgrade` → `ship.orbital_discharge_active` (cai ao descarregar
  os orbes).

É o mesmo princípio que o `ShieldBurstUpgrade` já aplicava à mão (cooldown ao
consumir o escudo, monitorando `ship.has_shield`).

**Ao adicionar upgrade novo:** se o efeito NÃO é por tempo (é por munição,
cargas, ou um recurso monitorado na nave), sobrescreva `_effect_still_running`.
Se for genuinamente instantâneo (Heal) ou fire-and-forget (Air Strike, Cannon
Tower), o default está certo — cooldown parte no tick seguinte.

Testes: `tests/test_upgrade_cooldown.py` (casos temporal, instantâneo, explosivo
por munição, descarga orbital por cargas).
