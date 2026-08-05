"""Tiro especial CARREGADO do Caçador (`HomingBullet`): arte, sobrecarga e mira.

O modo de falha destes sprites é silencioso: renomear um arquivo ou a pasta
(que tem cedilha no nome, então viaja mal entre sistemas de arquivos) faz o
`_get_frames` devolver lista vazia e o projétil volta ao círculo ciano de
fallback — em jogo isso parece "a arte não ficou pronta ainda", não um bug.
Nada aqui abre janela: são testes de disco e de surface pequena.

O que guardam:

1. **os três frames existem com o nome que o módulo procura** — o fallback nunca
   deve ser o caminho normal;
2. **os frames são surfaces próprias**, nunca a compartilhada do `get_image`;
3. **P2 recebe a cor dele** — dois Caçadores em coop precisam ser distinguíveis;
4. **a animação e o giro andam pelo `age`/`dt`**, não por relógio de parede, que
   ignoraria pausa e câmera lenta (§3);
5. **a sobrecarga acontece inteira** — o projétil que esgota o tempo de vida sem
   acertar nada para, treme, acelera o giro, incha, embranquece e só então
   estoura em área. Cada etapa tem teste porque o valor dela é ser VISTA: uma
   que silenciosamente pare de acontecer não quebra nada, só volta a fazer o
   tiro especial sumir no ar como se fosse bug de render;
6. **a mira só considera quem está na tela** — perseguir um inimigo que está
   saindo de cena transforma o projétil em escolta dele: os dois somem pela
   borda e o tiro morre sem acertar nada, enquanto hostis visíveis ficavam ali.
"""

import math

import pygame

from game.core.assets import get_image
from game.core.config import config as Config
from game.entities.projectiles import homing_bullet as hb
from game.systems.entity_manager import EntityManager
from game.systems.targeting import is_huntable, is_targetable


class _NaveFalsa:
    def __init__(self, player_index: int) -> None:
        self.player_index = player_index


def test_os_tres_frames_existem_no_disco():
    faltando = [n for n in hb._SPRITE_FILES if not (hb._SPRITE_DIR / n).exists()]
    assert not faltando, f"sprites ausentes em {hb._SPRITE_DIR}: {faltando}"


def test_carrega_os_tres_frames_para_os_dois_jogadores():
    for player_index in (0, 1):
        frames = hb._get_frames(player_index)
        assert len(frames) == len(hb._SPRITE_FILES)
        assert all(f.get_width() > 1 and f.get_height() > 1 for f in frames)


def test_frames_sao_copias_privadas_e_nao_a_surface_do_cache():
    # A surface do `get_image` é compartilhada com qualquer outro consumidor do
    # mesmo arquivo; transformá-la in-place é a armadilha do buffer de fade
    # (CLAUDE.md §17). Hoje `_prepare` escala (o que já aloca nova), mas o
    # `.copy()` do caminho sem escala é o que mantém a garantia se o fator
    # voltar a 1.
    compartilhada = get_image(hb._SPRITE_DIR / hb._SPRITE_FILES[0])
    assert hb._get_frames(0)[0] is not compartilhada


def test_frames_saem_escalados_pelo_fator_declarado():
    origem = get_image(hb._SPRITE_DIR / hb._SPRITE_FILES[0])
    ow, oh = origem.get_size()
    fw, fh = hb._get_frames(0)[0].get_size()
    assert (fw, fh) == (ow * hb._SPRITE_SCALE, oh * hb._SPRITE_SCALE)


def test_p2_desenha_em_cor_diferente_da_do_p1():
    p1 = pygame.image.tostring(hb._get_frames(0)[0], "RGBA")
    p2 = pygame.image.tostring(hb._get_frames(1)[0], "RGBA")
    assert p1 != p2


def _dominancia_azul(frame: pygame.Surface) -> float:
    """Média de (B - R) nos pixels opacos. Positivo = núcleo na família azul."""
    total = 0.0
    opacos = 0
    for x in range(frame.get_width()):
        for y in range(frame.get_height()):
            r, _g, b, a = frame.get_at((x, y))
            if a == 0:
                continue
            total += b - r
            opacos += 1
    return total / max(1, opacos)


def test_p2_usa_o_giro_de_TIRO_e_nao_o_de_nave():
    """O tiro do P2 continua azul; a meia-volta das naves o levaria ao vermelho.

    Regressão real desta arte: carregá-la por `player_sprite` (feito para o
    CASCO, giro de 0.5) virava o núcleo azul do Caçador em vermelho — que é
    justamente a cor do casco do P1, o contrário do que distinguir jogadores
    deveria comunicar. O giro certo é o curto, `P2_SHOT_HUE_SHIFT`.
    """
    assert _dominancia_azul(hb._get_frames(0)[0]) > 0, "sprite base não é azul"
    assert _dominancia_azul(hb._get_frames(1)[0]) > 0, (
        "o tiro do P2 saiu da família azul — giro de nave aplicado a um tiro?"
    )


def test_animacao_avanca_pelo_dt_acumulado_e_cicla():
    bala = hb.HomingBullet(50.0, 50.0, damage=10, source_ship=_NaveFalsa(0))
    total = len(hb._get_frames(0))
    vistos = set()
    # Um ciclo inteiro da animação, em passos de frame.
    passos = int((total / hb._ANIM_FPS) / (1 / 60.0)) + 2
    for _ in range(passos):
        bala.update(1 / 60.0, [])
        vistos.add(int(bala.age * hb._ANIM_FPS) % total)
    assert vistos == set(range(total))


def test_bala_congela_o_jogador_no_spawn():
    nave = _NaveFalsa(1)
    bala = hb.HomingBullet(0.0, 0.0, damage=10, source_ship=nave)
    assert bala.player_index == 1
    # Sem nave (projétil órfão) cai no P1 em vez de estourar.
    assert hb.HomingBullet(0.0, 0.0, damage=10).player_index == 0


def test_draw_desenha_sem_mexer_no_estado_da_bala():
    bala = hb.HomingBullet(60.0, 60.0, damage=10, source_ship=_NaveFalsa(0))
    bala.update(1 / 60.0, [])
    antes = (bala.x, bala.y, bala.age, bala.life, bala.dead, bala.rotation_angle)

    surface = pygame.Surface((160, 160), pygame.SRCALPHA)
    bala.draw(surface)

    assert (
        bala.x,
        bala.y,
        bala.age,
        bala.life,
        bala.dead,
        bala.rotation_angle,
    ) == antes
    assert surface.get_bounding_rect().width > 0, "nada foi desenhado"


# ---------------------------------------------------------------------------
# Giro em voo
# ---------------------------------------------------------------------------


def test_gira_no_proprio_eixo_a_velocidade_constante():
    bala = hb.HomingBullet(200.0, 200.0, damage=10, source_ship=_NaveFalsa(0))
    dt = 1 / 60.0
    anterior = bala.rotation_angle
    passos = []
    for _ in range(20):
        bala.update(dt, [])  # sem inimigos: voa reto, só o giro muda
        passos.append((bala.rotation_angle - anterior) % 360.0)
        anterior = bala.rotation_angle

    esperado = hb._ROT_SPEED * dt
    assert all(abs(p - esperado) < 1e-6 for p in passos), (
        f"giro deveria ser constante ({esperado}°/frame), veio {set(passos)}"
    )


def test_o_desenho_nao_depende_mais_da_vida_restante():
    """O fade por vida foi removido: gastar vida não apaga mais o projétil.

    Duas balas no mesmo instante da animação e do giro têm de sair pixel a pixel
    idênticas, mesmo com vidas muito diferentes.
    """
    cheia = hb.HomingBullet(40.0, 40.0, damage=10, source_ship=_NaveFalsa(0))
    gasta = hb.HomingBullet(40.0, 40.0, damage=10, source_ship=_NaveFalsa(0))
    gasta.consume_life(gasta.max_life * 0.9)
    cheia.rotation_angle = gasta.rotation_angle = 0.0
    assert gasta.life < cheia.life and not gasta.dead

    def pinta(bala):
        s = pygame.Surface((120, 120), pygame.SRCALPHA)
        bala.draw(s)
        return pygame.image.tostring(s, "RGBA")

    assert pinta(cheia) == pinta(gasta)


# ---------------------------------------------------------------------------
# Sobrecarga (fim do tempo de vida sem acertar nada)
# ---------------------------------------------------------------------------


def _bala_em_sobrecarga(player_index: int = 0, damage: int = 25):
    """Bala levada até o primeiro frame de sobrecarga."""
    bala = hb.HomingBullet(
        300.0, 200.0, damage=damage, lifetime=0.001, source_ship=_NaveFalsa(player_index)
    )
    bala.update(1 / 60.0, [])
    assert bala.overloading and not bala.dead
    return bala


def test_fim_do_tempo_de_vida_entra_em_sobrecarga_em_vez_de_morrer():
    bala = hb.HomingBullet(
        300.0, 200.0, damage=10, lifetime=0.05, source_ship=_NaveFalsa(0)
    )
    for _ in range(10):
        bala.update(1 / 60.0, [])
        if bala.overloading:
            break
    assert bala.overloading, "o projétil expirou sem entrar em sobrecarga"
    assert not bala.dead, "não pode morrer no instante em que a sobrecarga começa"


def test_sobrecarga_para_de_se_mover():
    bala = _bala_em_sobrecarga()
    pos = (bala.x, bala.y)
    for _ in range(10):
        bala.update(1 / 60.0, [])
    assert (bala.x, bala.y) == pos, "o projétil andou durante a sobrecarga"
    assert (bala.vx, bala.vy) == (0.0, 0.0)


def test_sobrecarga_acelera_o_giro_e_intensifica_o_tremor():
    """Giro e tremor sobem juntos — é a sincronia que comunica a sobrecarga."""
    bala = _bala_em_sobrecarga()
    dt = 1 / 60.0
    giros: list[float] = []
    tremores: list[float] = []
    anterior = bala.rotation_angle
    while not bala.dead:
        bala.update(dt, [])
        giros.append((bala.rotation_angle - anterior) % 360.0)
        tremores.append(max(abs(bala.shake_x), abs(bala.shake_y)))
        anterior = bala.rotation_angle

    # Compara o início com o fim: o tremor é sorteado por frame, então frames
    # vizinhos não são monotônicos — a TENDÊNCIA é o que o teste trava.
    inicio, fim = len(giros) // 5, len(giros) - len(giros) // 5
    assert max(giros[fim:]) > max(giros[:inicio]) * 2, "o giro não acelerou"
    assert max(tremores[fim:]) > max(tremores[:inicio]), "o tremor não intensificou"
    assert max(tremores) <= hb._OVERLOAD_SHAKE_MAX


def _pixels_pintados(bala) -> int:
    """Área realmente pintada. Medida invariante ao giro e ao estiramento.

    A bbox não serve: o ângulo inicial é sorteado e o estica-e-comprime encolhe
    UM dos eixos por vez, então largura sozinha oscila. Contagem de pixels
    opacos só responde ao inchaço.
    """
    s = pygame.Surface((400, 400), pygame.SRCALPHA)
    bala.draw(s)
    rect = s.get_bounding_rect()
    return sum(
        1
        for x in range(rect.left, rect.right)
        for y in range(rect.top, rect.bottom)
        if s.get_at((x, y))[3] > 0
    )


def test_sobrecarga_incha_o_sprite_ate_o_estouro():
    bala = _bala_em_sobrecarga()
    inicial = _pixels_pintados(bala)

    final = inicial
    while not bala.dead:
        bala.update(1 / 60.0, [])
        if not bala.dead:
            final = _pixels_pintados(bala)

    assert final > inicial, f"o sprite não cresceu ({inicial} → {final} px)"


def test_sobrecarga_embranquece_o_sprite():
    bala = _bala_em_sobrecarga()

    def brilho_medio() -> float:
        s = pygame.Surface((400, 400), pygame.SRCALPHA)
        bala.draw(s)
        total = 0.0
        opacos = 0
        rect = s.get_bounding_rect()
        for x in range(rect.left, rect.right):
            for y in range(rect.top, rect.bottom):
                r, g, b, a = s.get_at((x, y))
                if a == 0:
                    continue
                total += (r + g + b) / 3.0
                opacos += 1
        return total / max(1, opacos)

    inicial = brilho_medio()
    ultimo = inicial
    while not bala.dead:
        bala.update(1 / 60.0, [])
        if not bala.dead:
            ultimo = brilho_medio()

    assert ultimo > inicial * 1.5, (
        f"o sprite não clareou rumo ao branco ({inicial:.0f} → {ultimo:.0f})"
    )


def test_sobrecarga_termina_em_estouro_de_area_e_so_entao_morre():
    bala = _bala_em_sobrecarga(damage=37)
    blast = None
    while not bala.dead:
        bala.update(1 / 60.0, [])
        blast = bala.take_pending_blast() or blast

    assert bala.dead
    assert blast is not None, "morreu sem deixar explosão"
    # Kwargs prontos para `EntityManager.spawn_explosive_effect`.
    assert blast["radius"] == hb._OVERLOAD_BLAST_RADIUS
    assert blast["damage"] == 37, "o estouro usa o dano do próprio projétil"
    assert (blast["x"], blast["y"]) == (bala.x + bala.w / 2, bala.y + bala.h / 2)


def test_estouro_e_consumido_uma_unica_vez():
    bala = _bala_em_sobrecarga()
    while not bala.dead:
        bala.update(1 / 60.0, [])
    assert bala.take_pending_blast() is not None
    assert bala.take_pending_blast() is None, "a mesma explosão spawnaria duas vezes"


def test_entity_manager_materializa_o_estouro_da_sobrecarga():
    """A fiação ponta a ponta: o projétil pede, o manager spawna.

    O projétil não alcança o `EntityManager` (§1), então ninguém percebe se a
    ponta do manager sumir — a sobrecarga continuaria bonita e simplesmente não
    causaria dano nenhum. Só um teste que roda os dois lados pega isso.
    """
    em = EntityManager()
    bala = em.spawn_homing_bullet(
        300.0, 200.0, damage=25, direction=(0.0, -1.0), source_ship=_NaveFalsa(0)
    )
    bala.lifetime = 0.02

    for _ in range(int((0.02 + hb._OVERLOAD_TIME) * 60) + 5):
        em.update(1 / 60.0, player_x=400.0, player_y=300.0)

    assert bala.dead
    assert em.explosive_effects, "a sobrecarga não virou dano em área"
    efeito = em.explosive_effects[0]
    assert efeito.max_radius == hb._OVERLOAD_BLAST_RADIUS
    assert efeito.damage == 25


def test_sair_da_tela_mata_sem_sobrecarga():
    """Sequência inteira fora do campo visível é efeito que ninguém vê — e o
    estouro mataria um inimigo entrando pela borda sem explicação na tela."""
    bala = hb.HomingBullet(50.0, 50.0, damage=10, source_ship=_NaveFalsa(0))
    bala.y = -500.0
    bala.update(1 / 60.0, [])
    assert bala.dead
    assert not bala.overloading
    assert bala.take_pending_blast() is None


# ---------------------------------------------------------------------------
# Mira: só persegue quem está na tela
# ---------------------------------------------------------------------------

_SW = float(Config.SCREEN_WIDTH)
_SH = float(Config.SCREEN_HEIGHT)


class _InimigoFalso:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.w = 40
        self.h = 40
        self.dead = False


def test_is_huntable_exige_vivo_E_visivel():
    dentro = _InimigoFalso(_SW * 0.5, _SH * 0.5)
    assert is_huntable(dentro, _SW, _SH)

    saindo = _InimigoFalso(_SW * 0.5, -300.0)  # já passou do topo
    assert is_targetable(saindo), "ainda é alvejável — o que muda é a visibilidade"
    assert not is_huntable(saindo, _SW, _SH)

    dentro.dead = True
    assert not is_huntable(dentro, _SW, _SH)


def test_solta_o_alvo_travado_que_sai_da_tela():
    """O caso relatado em jogo: o teleguiado virava escolta de quem ia embora."""
    fugindo = _InimigoFalso(_SW * 0.5, _SH * 0.5)
    ficando = _InimigoFalso(_SW * 0.6, _SH * 0.6)
    bala = hb.HomingBullet(
        _SW * 0.5, _SH * 0.9, damage=10, source_ship=_NaveFalsa(0),
        locked_target=fugindo,
    )

    bala.update(1 / 60.0, [fugindo, ficando])
    assert bala.locked_target is fugindo, "deveria manter o alvo enquanto visível"

    fugindo.y = -300.0  # saiu pelo topo, ainda vivo
    bala.update(1 / 60.0, [fugindo, ficando])
    assert bala.locked_target is None, "não soltou o alvo que saiu de cena"


def test_reaponta_para_um_hostil_visivel_depois_de_soltar():
    fugindo = _InimigoFalso(_SW * 0.5, _SH * 0.4)
    ficando = _InimigoFalso(_SW * 0.5, _SH * 0.6)
    bala = hb.HomingBullet(
        _SW * 0.5, _SH * 0.9, damage=10, source_ship=_NaveFalsa(0),
        locked_target=fugindo,
    )
    fugindo.y = -300.0

    antes = math.hypot(ficando.x - bala.x, ficando.y - bala.y)
    for _ in range(30):
        bala.update(1 / 60.0, [fugindo, ficando])
    depois = math.hypot(ficando.x - bala.x, ficando.y - bala.y)

    assert depois < antes, "não passou a caçar o hostil que continuou visível"


def test_nao_escolhe_alvo_fora_da_tela_nem_quando_e_o_mais_proximo():
    """Proximidade não vence visibilidade: o mais perto pode ser o que já saiu."""
    perto_fora = _InimigoFalso(_SW * 0.5, -50.0)  # colado na borda, porém fora
    longe_dentro = _InimigoFalso(_SW * 0.1, _SH * 0.8)
    bala = hb.HomingBullet(_SW * 0.5, 20.0, damage=10, source_ship=_NaveFalsa(0))

    escolhido = bala._find_best_target([perto_fora, longe_dentro], _SW, _SH)
    assert escolhido is longe_dentro
