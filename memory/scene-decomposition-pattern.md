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

**Não extrair:** renderers de bosses e o `_finish` da cutscene de transição de
mundo — leem estado privado de domínio acoplado ao FSM da cena; extrair vira
callbacks demais (§1 alerta contra). Da cutscene, se um dia, tirar SÓ o animador
(kinematics + partículas), deixando o `_finish` na cena.

Próximo candidato limpo: AtmosphereProgression.
