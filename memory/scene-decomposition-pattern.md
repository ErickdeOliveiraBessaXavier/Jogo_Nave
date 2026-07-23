---
name: scene-decomposition-pattern
description: Como extrair fluxos da PlayingScene em sistemas próprios, e a regra do grep-completo ao migrar estado
metadata:
  type: project
---

`PlayingScene` (~2950 linhas, era ~3100) é decomposta **por fluxo**, um sistema
de cada vez, em `game/systems/`. Segue §1 e §9 do [[CLAUDE.md]].

**Padrão (referências: `systems/revival_system.py`, `systems/upgrade_selector.py`):**

- O sistema **não referencia `PlayingScene`** (§1). Dependências pelo construtor:
  objetos de domínio (roster, gamepad, `get_slots`) + **callbacks** para o que a
  cena mantém (`sync_lives`, `rebuild_mini_ships`, `activate`).
- Getter, não referência, para dado que a cena reatribui por fase
  (`upgrade_slots` vira `get_slots=lambda: self.upgrade_slots`).
- Estado que já vive na entidade fica lá (`slot.revival_beacon`); o sistema é
  sem estado próprio quando possível. Estado só do fluxo (cursor `mode`/`index`)
  migra pro sistema e a cena lê de lá ao montar o `RenderFrame`.
- A cena mantém **fachada fina** (§9) para a API que outros já chamam
  (`slot_inside_any_beacon`, `confirm_upgrade_select`).
- Prova de sucesso: o sistema fica **testável com stubs de ~10 linhas**, sem o
  jogo. Se precisar da cena pra testar, a fronteira está errada.

**Regra do grep-completo (aprendida na marra):** ao migrar um atributo de estado
da cena pro sistema, `grep` o projeto INTEIRO pelo **nome do atributo**, não só
pelos métodos que se movem. Ex.: extrair `UpgradeSelector` moveu
`upgrade_select_mode` pra dentro do sistema, mas o `gameplay_input_handler` lia
e escrevia `scene.upgrade_select_mode` cru — quebra em runtime com pytest e ruff
**verdes**, porque nada exercitava o input handler com gamepad. O `RenderFrame`
DTO isola o render dessa classe de quebra; input handler e outros sistemas, não.
Quando houver leitor externo, preserve o nome como **property de leitura** na
fachada e exponha um método pro write (`cancel_upgrade_select`).

**Duas formas de melhorar a cena:** (1) extrair COMPORTAMENTO em sistema
próprio quando a fronteira é limpa; (2) consolidar ESTADO num dataclass quando o
comportamento é FSM-coupled mas os atributos estão soltos. A (2) limpa o
`__init__` sem os callbacks demais.

Concluído: RevivalSystem, UpgradeSelector (extração de comportamento);
**AtmosphereState** em `core/atmosphere_phase.py` (consolidação de estado: 13
atributos `_atmosphere_*`/`_in_atmosphere` → 1 dataclass, 71 refs retargeteadas
p/ `self._atmosphere.X`, métodos FSM ficaram na cena). Testes por extração.

**Não extrair COMPORTAMENTO (avaliados, FSM-coupled — §1):**
- **AtmosphereProgression**: `_start/_apply_death_penalty/_finish_atmosphere_*`
  dão `app.states.push`, `_begin_level_preparation`, `spawner.set_level`,
  `boss_controller.reset`, revivem slots — ~15 callbacks. Por isso foi feita a
  consolidação de estado (AtmosphereState), não extração.
- **Cutscene de transição de mundo** (`_*_world_transition_cutscene`): `_finish`
  FSM-coupled. Se extrair, só o animador (charge→launch + partículas).
- **Renderers de bosses**: estado privado de domínio acoplado ao FSM.

**Lição:** "candidato limpo" só se confirma LENDO os corpos dos métodos, não
pelo nome do cluster. AtmosphereProgression parecia limpo pela lista de métodos;
ao ler, era FSM-coupled — virou consolidação de estado em vez de extração.
