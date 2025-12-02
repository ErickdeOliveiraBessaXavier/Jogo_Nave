# Sistema de Aprimoramentos (Ativos)

Objetivo: Criar uma nova camada de progressão/estratégia onde o jogador equipa 2 slots de habilidades ativas no menu e as ativa durante a partida, com cooldown/duração/cargas, sem substituir o sistema de power-ups atuais.

## Escopo MVP
- Slots: `2` (expansível no futuro).
- Teclas: `1` e `2` para ativar slot 1/2 (atalhos alternativos opcionais: `Q`/`E`).
- Upgrades iniciais:
  1) Shield Burst: dá escudo temporário (5–8s), recarga ~45s.
  2) Heal: +1 vida (respeita limite), 1–2 cargas por fase, recarga ~60s.
  3) EMP: onda que desacelera/estuna inimigos por ~2s, recarga ~50s.

## Fluxo de UX
- Menu Principal: novo botão “Aprimoramentos”.
- Cena de Seleção: grid com upgrades, descrição, status (bloqueado/desbloqueado), e 2 slots para equipar.
- HUD in-game: ícones dos slots (1/2), overlay de cooldown radial, contador de cargas.
- Feedback: SFX na ativação/erro, VFX rápido (flash/onda) ao ativar.

## Modelo de Dados e API
- Enum `UpgradeType` (SHIELD_BURST, HEAL, EMP, ...).
- Classe base `ActiveUpgrade`:
  - Propriedades: `cooldown`, `duration`, `charges`, `icon_id`, `name`, `desc`.
  - Métodos: `can_activate(ctx) -> bool`, `activate(ctx)`, `update(dt, ctx)`, `on_expire(ctx)`.
  - Estado interno: `cooldown_left`, `duration_left`, `charges_left`.
- Registro de upgrades: `UPGRADES_REGISTRY[UpgradeType] -> factory/config`.
- `ctx` (contexto de jogo): acesso a `ship`, `entity_manager`, `difficulty_settings`, `sound_manager`, `renderer`/efeitos, e tempo.

## Regras de Ativação
- Verifica: não em cooldown, tem cargas, e regras especiais de dificuldade.
- Empilhamento:
  - Shield Burst: renova/estende (define: renova duração; não acumula camadas).
  - Heal: negado se em vida máxima (toc de erro).
  - EMP: se ativado enquanto ativo, reinicia duração (sem stack de intensidade).
- Interações com power-ups: independentes; efeitos podem coexistir.

## Persistência (PlayerProfile)
- Campos novos:
  - `unlocked_upgrades: set[UpgradeType]` (MVP: {ShieldBurst, Heal, EMP}).
  - `loadout: list[UpgradeType]` (tamanho = slots, default vazio).
- Migração: se não existir no JSON, inicializar com defaults seguros.
- Auto-save ao confirmar loadout.

## Balanceamento (valores iniciais)
- Shield Burst: duração 7.0s, cooldown 45s.
- Heal: +1 vida; cargas por fase 2; cooldown 60s; não acima do cap.
- EMP: duração 2.0s; slowdown 60% (meteoros/inimigos); cooldown 50s; chefes: efeito visual leve e no máximo redução de precisão/velocidade de projéteis por 0.5s (ou nenhum efeito em chefe clássico).
- Dificuldade: se `special_rules` contém `no_powerups`, em MVP aplicaremos +50% no cooldown em vez de bloquear (configurável).

## HUD
- Posição: canto inferior direito (alinhado com estilo atual) ou superior direito, conforme legibilidade.
- Ícones circulares 40–48px, label pequeno “1”/“2”.
- Overlay de cooldown: círculo radial cinza escuro com alpha; badge de cargas no canto.

## Sons e Efeitos
- SFX: `upgrade_activate`, `upgrade_denied` (reutilizar hover/click ou adicionar novos).
- VFX:
  - Shield: borda/halo azul na nave.
  - Heal: flash verde curto na nave; número de vidas atualiza.
  - EMP: anel de onda partindo da nave; leve tremor nos inimigos.

## Integração com Gameplay
- Input em `PlayingScene`: mapear `K_1`, `K_2` (e opcionalmente `K_q`, `K_e`).
- Loop `update`: chamar `update(dt)` de cada instância equipada para decair cooldown/duração.
- Aplicar efeitos usando APIs existentes (escudo/invuln, controle de velocidades em `entity_manager`, etc.).

## Estrutura de Código (MVP)
- `game/core/upgrades.py`: tipos, base, registro e implementações (ShieldBurst, Heal, EMP).
- `game/scenes/upgrades_selection.py`: UI de seleção/equipar.
- `game/scenes/main_menu.py`: adiciona botão e navegação.
- `game/scenes/playing.py`: input, atualização de cooldowns, ativação, HUD simples.
- (Opcional) `game/core/upgrades_config.py`: constantes/balance, se preferirmos não tocar em `Config` no início.

## Passos de Implementação
1) Modelo e registry dos upgrades (arquivo novo, testes rápidos).  
2) Persistência no `PlayerProfile` (com migração).  
3) Cena de seleção e botão no menu.  
4) Integração no `PlayingScene` (input/ativação/update/HUD).  
5) SFX/VFX e ajustes de balance.  
6) QA básico e testes unitários de cooldown/persistência.

## Casos Limite
- Tentar ativar sem cargas/sem cooldown pronto → negar com SFX/tooltip breve.
- Vida cheia para Heal → negar (sem consumir cooldown/carga).
- Transições de fase/boss: impedir ativação durante fade-in/out se necessário.
- Game over/paused: upgrades não ativam.

## Decisões (MVP)
- Teclas padrão: `1` e `2`.
- Slots: 2.
- Desbloqueios: os 3 upgrades MVP vêm desbloqueados.
- Sem sistema de “energia” no MVP (apenas cooldown/cargas).
- Em dificuldades com `no_powerups`: +50% cooldown (configurável posteriormente).
