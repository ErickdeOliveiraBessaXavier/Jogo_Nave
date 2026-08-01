"""render_frame.py — DTO de leitura entre PlayingScene e GameRenderer.

Define o contrato explícito de tudo que o renderizador lê da cena. Em vez de
o renderer acessar `scene.foo_bar` direto (e quebrar silenciosamente quando a
cena renomeia atributos), `PlayingScene._build_render_frame()` monta um
`RenderFrame` por frame e o renderer consome só este DTO.

Scalars/flags são copiados; refs a sistemas estáveis (ship, entity_manager,
boss_controller) são passadas por referência — esses não são "internals" da
cena, são serviços compartilhados. Coleções mutáveis (particles, upgrade
slots) também passam por ref e são tratadas como read-only pelo renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    from ..core.difficulty import DifficultyPreset
    from ..core.upgrades import ActiveUpgrade
    from ..entities.player.revival_beacon import RevivalBeacon
    from ..entities.player.ship import Ship
    from .boss_backdrop_dim import BossBackdropDim
    from .damage_vignette import DamageVignette
    from ..scenes.playing import GameState, ThrusterParticle
    from ..systems.boss_fight_controller import BossFightController
    from ..systems.entity_manager import EntityManager


@dataclass(frozen=True)
class P2HudInfo:
    """Snapshot dos dados do Jogador 2 para o HUD secundário.

    Existe apenas quando há um segundo slot no roster (coop ativo). Quando
    `is_dead=True`, `beacon_progress` está em 0.0-1.0 mostrando o quanto da
    barra de revive já foi acumulada — usado pelo HUD para mostrar
    "REVIVENDO XX%" no lugar das vidas.
    """

    lives: int
    is_dead: bool
    ship: "Ship"
    beacon_progress: float = 0.0


@dataclass(frozen=True)
class RenderFrame:
    """Snapshot imutável do estado relevante para renderização de um frame."""

    # Tempo & FSM
    dt: float
    state: "GameState"
    preparation_time_left: float

    # Score, vidas e dificuldade
    score: int
    lives: int
    total_enemies_destroyed: int
    difficulty_preset: "DifficultyPreset"
    stage_name: str

    # Multiplicador de score
    score_multiplier_active: bool
    score_multiplier_timer: float

    # Screen shake
    shake_timer: float
    shake_intensity: int

    # Debug overlays
    show_fps: bool
    show_enemy_hitboxes: bool

    # Upgrade HUD
    upgrade_select_mode: bool
    upgrade_select_index: int
    upgrade_slots: list["ActiveUpgrade | None"]
    upgrade_keybindings: list[int]
    upgrade_denied_timers: dict[int, float]
    """Índice do slot → segundos restantes de tremor por uso negado.

    Alimenta o feedback de "tentei usar e não deu": sem isto, apertar a tecla de
    um poder em cooldown não produz resposta visual nenhuma.
    """

    # Cutscene de transição de mundo
    world_transition_cutscene_active: bool
    world_transition_cutscene_timer: float
    is_arrival_cutscene: bool
    world_transition_thruster_particles: list["ThrusterParticle"]

    # Refs a sistemas (estáveis — não são internals da cena)
    ship: "Ship"
    entity_manager: "EntityManager"
    boss_controller: "BossFightController"

    # Vinheta de dano (overlay de HUD). Renderer só chama `draw()`; estado é
    # mutado na cena (trigger/update), nunca aqui.
    damage_vignette: "DamageVignette"

    # Escurecimento de fundo em lutas de boss. Renderer só chama `draw()` (após o
    # background); estado é mutado na cena (update).
    boss_backdrop_dim: "BossBackdropDim"

    # Multiplayer: naves adicionais (P2 em diante) renderizadas após `ship`.
    # Vazio em single-player. Renderer apenas draw()-a; não inspeciona estado.
    extra_ships: tuple["Ship", ...] = ()

    # Multiplayer: beacons de revive de slots mortos. Renderer só os desenha.
    revival_beacons: tuple["RevivalBeacon", ...] = ()

    # Multiplayer: False quando o slot primário está morto esperando revive.
    # Renderer pula `frame.ship.draw()` mas mantém o resto do HUD/stats.
    primary_alive: bool = True

    # Multiplayer: dados do P2 para o HUD secundário. None em single-player.
    p2_hud: Optional[P2HudInfo] = None

    # Pop-up de início de nível (sub-fases)
    level_popup_text: str = ""
    level_popup_timer: float = 0.0
    level_popup_duration: float = 2.5

    # Fase de atmosfera (interstício)
    in_atmosphere: bool = False
    atmosphere_progress: float = 0.0
    atmosphere_route: Optional[str] = None

    # Impact flash (white frames): clarão branco curtíssimo sobre o mundo para
    # momentos importantes. Renderer compõe alpha = flash_alpha * (timer/duração).
    flash_timer: float = 0.0
    flash_duration: float = 0.0
    flash_alpha: int = 0

    # 'Pop' do número do score: 1.0 no frame em que pontuou, decaindo a 0.0.
    # A cena mantém o timer; aqui só chega a fração já normalizada.
    score_pop: float = 0.0

    # ── Parada do tempo (power-up TIME_STOP) ──────────────────────────────
    # Já normalizados pela cena a partir do `TimeStopState`; o renderer não
    # conhece durações nem constantes, só desenha as frações.
    # A moldura é descrita por DOIS números contínuos e um relógio, e nada
    # mais. Não há booleano de fase aqui de propósito: um `frozen`/`recovering`
    # convida o renderer a ramificar, e foi exatamente uma ramificação por fase
    # que fazia a saída da moldura recomeçar do zero em vez de continuar de
    # onde a permanência estava.
    time_stop_warning: float = 0.0
    """0→1 conforme o congelamento se aproxima do fim, e de volta a 0 na saída.

    Único canal do aviso de término: a intensidade da pulsação e o quanto a
    moldura 'racha' saem daqui. Sobe em rampa, em vez de ser um liga/desliga,
    para o aviso entrar suave e ir ficando mais aflito.

    Vem de `TimeStopState.hud_warning`, **não** de `warning_ratio`: o segundo
    zera de um frame para o outro no descongelamento (certo para o tremor,
    que tem de parar na hora) e isso dava um degrau visível na moldura.
    """

    time_stop_openness: float = 0.0
    """Abertura da moldura: 0 → 1 → 0. Um só valor para entrada, permanência e
    saída.

    A saída é a MESMA rampa da entrada lida ao contrário (1,01s cada), então o
    fechamento é a continuação natural do estado atual, não uma segunda
    animação que recomeça do zero.

    Cronometrado pelos SFX: sobe durante o gesto do `Efeito_Desacelerando`
    (1,01s) e desce durante o do `Efeito_Acelerando`, depois de segurar os
    0,47s de silêncio inicial daquele arquivo. É deliberado que **não** siga a
    recuperação dos inimigos, que dura o dobro do áudio.

    `0.0` significa "sem moldura" — é o único guarda de que o renderer precisa.
    """

    time_stop_phase: float = 0.0
    """Relógio da pulsação, em segundos de congelamento acumulados.

    Vem da cena porque o render não tem (nem deve ter) relógio próprio: §3.
    Um `time.time()` aqui continuaria correndo durante a pausa e faria a
    moldura reaparecer fora de fase ao despausar.
    """

    # ── Descoberta dos aprimoramentos (FTUE) ──────────────────────────────
    # Dois números do perfil que o HUD precisa para não deixar o sistema de
    # aprimoramentos invisível na primeira partida. Vêm pelo DTO como cópias
    # (§1): o renderer não conhece `PlayerProfile`.

    available_stars: int = 0
    """Saldo de estrelas (coletadas − gastas), o que o jogador pode gastar.

    A estrela é a moeda que compra capacidade de slot (`SLOT_UNLOCK_COSTS`),
    mas até aqui só era exibida na tela de Estatísticas e na própria Central
    de Loadout — nunca durante a partida, que é justamente onde ela é colhida.
    Quem nunca abriu aquelas telas juntava a moeda sem saber que era moeda.
    """

    touch_mode: bool = False
    """Modo toque (celular) ligado — ver `UserPreferences.touch_mode`.

    O HUD muda de LAYOUT, não só de estilo: a fileira de upgrades vira coluna na
    borda direita e um botão de pausa aparece. No desktop a fileira embaixo, no
    centro, é o lugar mais confortável; no celular é o pior possível, porque é
    debaixo do polegar que pilota. Ver `hud_layout`.
    """

    joystick_enabled: bool = False
    """Joystick virtual ligado — ver `UserPreferences.virtual_joystick`.

    Muda o HUD do modo toque: entra o direcional no canto inferior esquerdo
    e o botao de girar no direito, e a pausa sobe para a borda esquerda.
    """

    joystick_active: bool = False
    """O polegar esta no direcional NESTE frame (desenha aceso)."""

    joystick_offset: tuple[float, float] = (0.0, 0.0)
    """Deslocamento do knob em px, ja preso ao raio pelo `VirtualJoystick`.

    Vem pronto de proposito: a regra de saturacao mora no sistema (§3, o
    render nao decide nada), e o renderer so soma ao centro.
    """

    unlocked_upgrade_slots: int = 0
    """Quantos slots o perfil tem destravados (`PlayerProfile.unlocked_slots`).

    Usado só para desenhar os contornos vazios quando nada está equipado; o
    mesmo número é orçamento de peso na Central de Loadout, mas essa regra não
    interessa ao HUD.
    """
