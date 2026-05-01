# Sistema de Som

Este arquivo documenta a configuração central do sistema de áudio e o caminho
de migração adotado no projeto.

## Estrutura atual

- `sound_config.py`: fonte única de verdade para volumes, canais, paths e
  comportamento.
- `sound.py`: contém a fachada pública `sound_manager`, hoje implementada como
  `AudioController` sobre um `SoundManager` existente.
- `sfx_manager.py`: extrai o carregamento de SFX e grupos de sons.

## Configuração principal

### `VOLUME_CONFIG`

- `master`: volume global.
- `sfx`: volume base dos efeitos.
- `music`: volume base da música.
- `boss_music`: multiplicador aplicado em faixas de boss.
- `shots`: volume base dos tiros.

### `CHANNEL_CONFIG`

- `shots`: canal dedicado aos disparos.
- `warning`: canal para avisos.
- `boss_laser`: canal para carga do laser.
- `boss_laser_fire`: canal para disparo do laser.
- `max_channels`: número total de canais reservados no mixer.

### `SOUND_PATHS`

Contém os caminhos relativos de música e SFX. Para adicionar um som novo:

1. Adicione o arquivo em `game/assets/sounds/...`.
2. Registre o caminho em `sound_config.py`.
3. Se for um som de uso frequente, adicione um método explícito em `sound.py`.

## Migração incremental

### Fase 1

- Manter a API pública usada pelo restante do jogo.
- Delegar o carregamento de SFX para `sfx_manager.load_sfx()`.
- Garantir `sound_manager.shutdown()` em `GameApp.run()`.

### Fase 2

- Extrair a reprodução de SFX para um `SfxManager` completo.
- Extrair a lógica de música para um `MusicManager` com transição controlada.
- Manter `sound_manager` como fachada para compatibilidade.
- Para bosses novos, defina em cada classe `MUSIC_STATE` e, na cena, use
  `getattr(type(boss), "MUSIC_STATE", MusicState.BOSS)` para tocar a trilha
  correta sem espalhar `if/elif` por tipo de boss.

### Fase 3

- Adicionar testes de assets e de comportamento.
- Remover caminhos duplicados ou métodos obsoletos depois da migração.

## Boas práticas usadas aqui

- Carregamento centralizado.
- Caminhos configuráveis em um único módulo.
- Encerramento explícito do mixer.
- Logging em vez de `print()` para eventos de áudio.
