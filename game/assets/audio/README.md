# Música orientada por pastas (data-driven)

A **presença** de um arquivo de áudio dentro destas pastas é o único registro
necessário. Não há lista de arquivos no código nem caminhos fixos: o jogo
descobre tudo sozinho em tempo de execução (`game/core/music_library.py`).

## Como adicionar música

- **Tema (música ambiente):** solte arquivos em `themes/<tema>/`.
  O `<tema>` é o valor de `WorldTheme` (`mountains`, `starfield`, `city`,
  `volcanic`). Mundos `procedural` são expandidos para um destes.
- **Boss (música exclusiva):** solte arquivos em `bosses/<BOSS_TYPE_NAME>/`.
  O `<BOSS_TYPE_NAME>` é o atributo de classe do boss
  (ex.: `metropolis_overlord`, `mountain_serpent`, `stone_golem`).
- **Menu:** solte arquivos direto em `menu/` (pasta plana, sem subpasta — é um
  contexto único).

Formatos aceitos: `.mp3`, `.ogg`, `.wav`.

## Comportamento

- **Várias faixas numa pasta** → rotação automática (aleatória, sem repetir a
  mesma faixa em seguida), com transição suave (fade) entre faixas.
- **Uma faixa só** → ela repete continuamente (loop gapless).
- **Pasta de boss vazia** → usa a música de boss **genérica** (`bosses/normal/`).
- **Pasta de tema/menu vazia** → mantém a faixa que já estava tocando (sem corte).

## Criar um tema ou boss novo no futuro

1. Crie a pasta (`themes/<novo>` ou `bosses/<novo_BOSS_TYPE_NAME>`).
2. Adicione os arquivos de áudio.
3. Pronto — sem editar código de configuração.
