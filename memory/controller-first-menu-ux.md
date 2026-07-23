---
name: controller-first-menu-ux
description: Usuário prioriza a experiência do jogador de controle nos menus
metadata:
  type: feedback
---

Ao melhorar menus, o usuário pede para **focar no jogador de controle**. No
controle, os menus usam: cursor virtual movido pelo RS, navegação discreta por
D-pad via `scene.get_focusable_rects()` (snap-focus em `app.py`, que esconde o
ponteiro do mouse), `A` confirma o que está sob o cursor, `B` volta, `LB/RB`
paginam/ciclam. No jogo, upgrades são ativados via seletor (D-pad p/ baixo abre,
LB/RB escolhe, A ativa) — não há "tecla 1-8" no controle (isso é teclado).

Implicações de design já aplicadas:
- Implementar `get_focusable_rects()` para o D-pad navegar (feito em
  `upgrades_selection.py`).
- Realce forte do item em foco (anel/glow), porque o ponteiro some no modo
  focus — sem ele o jogador não sabe o que está selecionado.

**Why:** o usuário joga de controle e reclamou que selecionar itens estava
"muito ruim".

**How to apply:** ao mexer em UI de menu, garantir navegação por D-pad +
realce de foco visível; legendas de controle no rodapé NÃO são desejadas (o
usuário pediu para remover da tela de loadout).

Relacionado: [[menu-ui-scale-convention]].
