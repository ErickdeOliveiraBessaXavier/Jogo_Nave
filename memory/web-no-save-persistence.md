---
name: web-no-save-persistence
description: Web port não persiste save; saves gateados no emscripten (MEMFS volátil). Persistência real é feature pendente.
metadata: 
  node_type: memory
  type: project
  originSessionId: 51fc0253-f4f3-4431-ab3c-8ad4d79e299b
---

No web (pygbag/emscripten) o jogo NÃO persiste progresso entre reloads: `paths.get_user_data_dir()` cai em `Path.cwd()` (não é `frozen`), que aponta pro MEMFS — filesystem virtual em memória, zerado a cada reload da aba. Não há nenhuma lógica de IDBFS/`syncfs`/`localStorage`.

Por isso, `PlayerProfile.save/save_async/auto_save` e `Preferences.save` têm early-return `if sys.platform == "emscripten"` — escrever só custaria stutter de I/O bloqueante no loop (a dica: "any I/O é lento no web") sem persistir nada. `save_async` também usa threads, terreno minado no pygbag (ver [[music-transitions-main-thread]]).

**Pendente:** persistência real no web (IDBFS + mount/syncfs, ou localStorage via `platform.window`) num branch emscripten do `paths.py`/`save()`. É feature à parte, não é sobre performance.

Build web: `web/staging/` é regenerado por `build_web.ps1` a partir de `game/` — editar sempre o fonte em `game/`, nunca o staging. Rodar `.\build_web.ps1` pra o bundle pegar mudanças. Relacionado: gating de animações de UI via `visual_quality.ui_animations` (default OFF no web).
