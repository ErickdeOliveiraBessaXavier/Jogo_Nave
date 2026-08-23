"""A morte de uma Voz da Tríade sai na cor DELA, não na da nave que atirou.

Regressão de um bug que o olho não denuncia: `HitResult.killed` significa "a
ENTIDADE morreu", e a Tríade sobrevive à queda de uma cabeça. Com `killed`
False, o `CollisionPhysics` classificava a queda como hit comum e deixava o
`ImpactStyle` da nave pintar por cima — a Voz explodia em verde com o Estilete,
azul com o Magneto, e só saía laranja quando ninguém passava estilo (dano em
área, testes). O `explosion_type` pedido pelo boss era descartado em silêncio.
"""

from __future__ import annotations

from game.entities._shared.impact_styles import SHIP_IMPACT_STYLES
from game.entities.bosses.city import triad_pixel_map as pmap
from game.systems.collision_physics import CollisionPhysics
from game.systems.hit_result import HitResult


class _ExplosionSpy:
    """Só o que o roteador de dano precisa — nada de EntityManager de verdade."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def spawn_explosion(self, x, y, size=30, explosion_type=None, pattern="burst"):
        self.calls.append({"palette": explosion_type, "pattern": pattern, "size": size})

    def absorb_fragments(self, fragments):  # pragma: no cover - não usado aqui
        pass

    def add_powerups(self, powerups):  # pragma: no cover - não usado aqui
        pass


class _VozCaindo:
    """Devolve o mesmo HitResult que `TriadBoss._damage_head` na queda."""

    shield_hp = 0.0

    def on_hit(self, damage, hit_x, hit_y):
        return HitResult(
            explosion_size=60,
            explosion_type=pmap.VOICE_DEATH_PALETTE,
            part_death=True,
        )


class _VozLevandoTiro:
    """Hit que NÃO derruba — este deve continuar sendo pintado pela nave."""

    shield_hp = 0.0

    def on_hit(self, damage, hit_x, hit_y):
        return HitResult(explosion_size=12)


def _explode(alvo, impact):
    spy = _ExplosionSpy()
    CollisionPhysics().apply_hit(alvo, 10, 100.0, 100.0, spy, impact=impact)
    assert len(spy.calls) == 1
    return spy.calls[0]


def test_queda_da_voz_ignora_o_estilo_da_nave():
    """Com QUALQUER nave atirando, a queda sai na paleta do boss."""
    for nome, estilo in SHIP_IMPACT_STYLES.items():
        call = _explode(_VozCaindo(), estilo)
        assert call["palette"] == pmap.VOICE_DEATH_PALETTE, (
            f"a Voz derrubada pela nave '{nome}' saiu na paleta da nave "
            f"({call['palette']}) em vez da do boss"
        )


def test_paleta_da_voz_e_ancorada_no_laranja_do_telegrafo():
    """A cor dominante é a MESMA do frame `Atacando` — é o círculo que fecha.

    E ela fica no MEIO: a paleta é interpolada por `life_ratio`, então o miolo é
    o que mais aparece na tela.
    """
    pal = pmap.VOICE_DEATH_PALETTE
    assert len(pal) >= 3
    assert pmap.ORANGE in pal[1:-1], "o laranja do telégrafo saiu do miolo da paleta"


def test_a_explosao_da_voz_tem_dois_tons_de_verdade():
    """Matiz precisa VIAJAR, não só clarear.

    A primeira versão empilhava três luminosidades do mesmo laranja (6,2° de
    amplitude) e lia como mancha chapada — fogo tem viagem de matiz, e a
    explosão padrão do jogo percorre 60° (amarelo → vermelho). O piso aqui é
    frouxo de propósito: trava o "voltou a ser um tom só", não o valor exato.
    """
    import colorsys

    matizes = [
        colorsys.rgb_to_hls(*[v / 255 for v in cor])[0] * 360
        for cor in pmap.VOICE_DEATH_PALETTE
    ]
    amplitude = max(matizes) - min(matizes)
    assert amplitude >= 15.0, (
        f"a paleta voltou a ser um matiz só ({amplitude:.1f}° de amplitude)"
    )
    # ...e sem sair do laranja: nem amarelo (>50°) nem vermelho puro (<5°), ou a
    # queda deixa de ser reconhecivelmente a cor do sprite `Atacando`.
    assert 5.0 <= min(matizes) and max(matizes) <= 50.0, (
        f"a paleta escapou da família do laranja: {[round(m, 1) for m in matizes]}"
    )


def test_hit_que_nao_derruba_continua_com_a_cor_da_nave():
    """O `part_death` não pode vazar para o hit comum: ali a nave é quem pinta."""
    estilo = SHIP_IMPACT_STYLES["estilete"]
    call = _explode(_VozLevandoTiro(), estilo)
    assert call["palette"] == estilo.palette
    assert call["pattern"] == estilo.pattern
