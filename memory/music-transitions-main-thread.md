---
name: music-transitions-main-thread
description: Transições/crossfade de música DEVEM rodar na thread principal; pygame não é thread-safe. Worker thread causava access violation.
metadata: 
  node_type: memory
  type: project
  originSessionId: 829ac96a-9105-4034-85fd-f070fa60a2fc
---

Crossfade de música é **cooperativo na thread principal**, nunca em worker
thread. `MusicManager._transition_to_music` dispara o `fadeout` assíncrono do
SDL e agenda a nova faixa em `_pending_transition`; `MusicManager.update(dt)`
(chamado 1×/frame por `SoundManager.update_music` no loop de `app.run`) carrega
e toca a faixa com `music.play(loop, 0.0, fade_ms)` (fade-in nativo do SDL)
quando o fade-out termina. Sem `time.sleep`, sem stepping manual de volume.

**Why:** pygame/SDL **não é thread-safe**. A versão antiga rodava
`_smooth_transition` numa `threading.Thread` daemon fazendo
`mixer.music.load/play/fadeout/set_volume` enquanto o loop principal
renderizava → *access violation* (crash nativo silencioso, sem exceção Python
nem `error.log`). O `crash.log` do `faulthandler` mostrou duas threads no core
do pygame ao mesmo tempo: main em `renderer.smoothscale` × worker em
`music_manager._smooth_transition`. Reproduzia ao entrar na arena CITY (troca de
tema + música de boss coincidindo com o render da tela de preparação).

**How to apply:** nunca chamar API de `pygame.mixer.music` (nem qualquer
pygame) fora da thread principal. Novas mecânicas de áudio com tempo usam o
tick cooperativo de `update(dt)`, não `threading`. `faulthandler` fica ligado
em `run.py` (`_enable_faulthandler` → `crash.log`) para capturar crashes
nativos futuros. `transition_thread`/`transition_lock` no `SoundManager` são
vestigiais (sem uso após a correção).
