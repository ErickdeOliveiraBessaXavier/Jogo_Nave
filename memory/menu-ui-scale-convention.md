---
name: menu-ui-scale-convention
description: Telas de menu devem escalar a UI por ui_scale = SCREEN_WIDTH/1280 para resoluções diferentes
metadata:
  type: project
---

As telas de menu são desenhadas em pixels num design base de **1280×720** e o
jogo roda com `pygame.SCALED` na resolução escolhida (de 576p a 5K, sempre
16:9; `set_screen_resolution` atualiza `config.SCREEN_WIDTH/HEIGHT` para casar
com a surface lógica). Sem escala, cards/fontes/botões fixos ficam
desproporcionais fora de 720p ("estranho").

Convenção adotada: cada view calcula `self.ui_scale = Config.SCREEN_WIDTH / 1280.0`
(um fator só serve para os dois eixos por ser 16:9) e multiplica por ele os
tamanhos/posições fixos: dimensões de card, espaçamento, fontes (`get_font(max(8, int(base*ui_scale)))`),
offsets de texto, border_radius, hitboxes de seta/botão e posição do título.
Em 720p o resultado é idêntico ao design original (sem regressão).

Já aplicado em `world_selection.py` e `difficulty_selection.py`. O usuário vem
auditando tela a tela — aplicar o mesmo padrão em qualquer menu novo/antigo.

**Why:** o usuário relatou layout quebrado em resoluções não-720p e pede
consistência entre telas.

**How to apply:** computar `ui_scale` no `__init__`/`setup_ui` antes de criar
fontes; escalar todas as constantes de pixel; validar headless renderizando em
576p/720p/1080p/4K e conferindo que tudo cabe na tela e que 720p não muda.

Relacionado: preferência geral de UX [[controller-first-menu-ux]].
