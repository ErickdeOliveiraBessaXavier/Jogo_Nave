"""Efeito de dano crítico: fogo e fumaça de quem está prestes a cair.

O sistema é GENÉRICO por contrato — recebe uma razão de vida (0..1) e um
`pygame.Rect` de emissão, e não conhece entidade nenhuma. Estes testes exercitam
o efeito sozinho, sem instanciar boss algum: é essa a prova de que ele serve para
o próximo boss sem alteração.
"""

import pygame
import pytest

from game.entities.effects.critical_damage import CriticalDamageFX

AREA = pygame.Rect(100, 100, 180, 140)
DT = 1 / 60


def rodar(fx: CriticalDamageFX, ratio: float, segundos: float) -> None:
    for _ in range(int(segundos / DT)):
        fx.update(DT, ratio, AREA)


def total(fx: CriticalDamageFX) -> int:
    return len(fx._bursts) + len(fx._smoke)


class TestLimiar:
    def test_vida_cheia_nao_emite_nada(self):
        fx = CriticalDamageFX()
        rodar(fx, 1.0, 3.0)
        assert not fx.emitting
        assert not fx.has_particles

    def test_logo_acima_do_limiar_ainda_nao_emite(self):
        fx = CriticalDamageFX()
        rodar(fx, fx.threshold + 0.01, 3.0)
        assert total(fx) == 0

    def test_abaixo_do_limiar_emite(self):
        fx = CriticalDamageFX()
        rodar(fx, fx.threshold - 0.01, 3.0)
        assert fx.emitting
        assert total(fx) > 0

    def test_o_limiar_e_configuravel(self):
        """Um boss de vida curta pode querer fumegar mais cedo."""
        fx = CriticalDamageFX(threshold=0.8)
        rodar(fx, 0.5, 2.0)
        assert total(fx) > 0


class TestRampaDeIntensidade:
    def test_zero_no_limiar_e_um_com_vida_zerada(self):
        fx = CriticalDamageFX()
        fx.update(DT, fx.threshold, AREA)
        assert fx.intensity == 0.0
        fx.update(DT, 0.0, AREA)
        assert fx.intensity == pytest.approx(1.0)

    def test_a_intensidade_cresce_conforme_a_vida_cai(self):
        fx = CriticalDamageFX()
        leituras = []
        for ratio in (0.29, 0.20, 0.10, 0.0):
            fx.update(DT, ratio, AREA)
            leituras.append(fx.intensity)
        assert leituras == sorted(leituras)
        assert leituras[0] < leituras[-1]

    def test_razao_fora_da_faixa_nao_quebra(self):
        """Vida negativa (overkill) ou acima de 1 (cura) não devem estourar."""
        fx = CriticalDamageFX()
        fx.update(DT, -0.5, AREA)
        assert fx.intensity == pytest.approx(1.0)
        fx.update(DT, 2.0, AREA)
        assert fx.intensity == 0.0

    def test_perto_da_morte_emite_mais_que_perto_do_limiar(self):
        """É a rampa que faz o efeito dizer 'quanto falta' sem número na tela."""
        fraco = CriticalDamageFX()
        rodar(fraco, 0.29, 2.0)
        forte = CriticalDamageFX()
        rodar(forte, 0.0, 2.0)
        assert total(forte) > total(fraco)


class TestCicloDeVida:
    def test_as_particulas_expiram_sozinhas(self):
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 2.0)
        assert fx.has_particles
        rodar(fx, 1.0, 4.0)  # voltou à vida cheia: para de emitir
        assert not fx.has_particles

    def test_as_particulas_vivas_terminam_a_animacao(self):
        """Parar de emitir não pode cortar o fogo num frame seco."""
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 2.0)
        vivas = total(fx)
        fx.update(DT, 1.0, AREA)  # deixou de emitir AGORA
        assert total(fx) > 0 and total(fx) <= vivas

    def test_clear_apaga_tudo(self):
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 2.0)
        fx.clear()
        assert not fx.has_particles
        assert fx.intensity == 0.0

    def test_area_ausente_nao_quebra(self):
        """Entidade sem caixa válida num frame (ex.: entrando em cena)."""
        fx = CriticalDamageFX()
        for _ in range(60):
            fx.update(DT, 0.0, None)
        assert total(fx) == 0

    def test_respeita_o_teto_de_particulas(self):
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 20.0)
        assert len(fx._bursts) <= fx.MAX_BURSTS
        assert len(fx._smoke) <= fx.MAX_SMOKE


class TestCadencia:
    def test_nao_reatribui_o_intervalo_cheio(self):
        """§14: o período real tem que bater com o configurado, não virar um
        número inteiro de frames. Com `timer = INTERVALO` o efeito renderia
        MENOS estouros que o pedido, e o erro é pequeno e sistemático.

        Conta as EMISSÕES, não o tamanho da lista: as partículas também expiram,
        então um spawn no mesmo frame de uma expiração deixa o tamanho igual e
        passa despercebido — o que tornava esta medição flaky.
        """
        fx = CriticalDamageFX()
        emitidos = {"n": 0}
        original = fx._spawn_burst

        def contar(area):
            emitidos["n"] += 1
            original(area)

        fx._spawn_burst = contar  # type: ignore[method-assign]

        segundos = 12.0
        for _ in range(int(segundos / DT)):
            fx.update(DT, 0.0, AREA)

        esperado = segundos / fx.BURST_INTERVAL_NEAR
        assert emitidos["n"] == pytest.approx(esperado, rel=0.05)

    def test_pausar_a_emissao_nao_acumula_divida(self):
        """Quem volta a fumegar recomeça a cadência, sem rajada represada."""
        fx = CriticalDamageFX()
        rodar(fx, 1.0, 5.0)  # 5s sem emitir
        fx.update(DT, 0.0, AREA)
        assert total(fx) <= 2


class TestRenderSemEfeitoColateral:
    def test_draw_nao_muta_estado(self):
        """§3: `draw` desenha e mais nada."""
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 2.0)
        surface = pygame.Surface((640, 480), pygame.SRCALPHA)
        antes = (len(fx._bursts), len(fx._smoke), fx.intensity)
        posicoes = [(b.x, b.y, b.radius) for b in fx._bursts]
        fx.draw(surface, 3.0, -2.0)
        assert (len(fx._bursts), len(fx._smoke), fx.intensity) == antes
        assert [(b.x, b.y, b.radius) for b in fx._bursts] == posicoes

    def test_desenha_de_fato_na_surface(self):
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 2.0)
        surface = pygame.Surface((640, 480), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))
        fx.draw(surface)
        assert pygame.transform.average_color(surface)[3] > 0

    def test_o_buffer_compartilhado_nao_vaza_alpha(self):
        """§17: o scratch é reusado entre partículas; um `set_alpha` residual
        pintaria a próxima com o alpha da anterior. Aqui o alpha vai na COR."""
        fx = CriticalDamageFX()
        rodar(fx, 0.0, 2.0)
        surface = pygame.Surface((640, 480), pygame.SRCALPHA)
        fx.draw(surface)
        from game.entities.effects import critical_damage as mod

        assert mod._alpha_scratch is not None
        assert mod._alpha_scratch.get_alpha() in (None, 255)


class TestReuso:
    """O ponto do pedido: servir a QUALQUER boss, não só ao primeiro."""

    def test_cada_instancia_tem_estado_proprio(self):
        a, b = CriticalDamageFX(), CriticalDamageFX()
        rodar(a, 0.0, 2.0)
        assert total(a) > 0
        assert total(b) == 0

    def test_a_escala_engorda_o_efeito(self):
        """Boss maior pede fogo maior."""
        pequeno = CriticalDamageFX(scale=1.0)
        grande = CriticalDamageFX(scale=3.0)
        rodar(pequeno, 0.0, 3.0)
        rodar(grande, 0.0, 3.0)
        assert max(b.max_radius for b in grande._bursts) > max(
            b.max_radius for b in pequeno._bursts
        )

    def test_as_cores_sao_configuraveis(self):
        verde = (0, 255, 0)
        fx = CriticalDamageFX(burst_colors=(verde,), smoke_colors=((10, 10, 10),))
        rodar(fx, 0.0, 2.0)
        assert {b.color for b in fx._bursts} == {verde}

    def test_emite_dentro_da_area_recebida(self):
        """A área é contrato: um boss irregular passa um rect menor e o fogo
        tem que respeitar."""
        fx = CriticalDamageFX()
        area = pygame.Rect(500, 300, 40, 30)
        for _ in range(240):
            fx.update(DT, 0.0, area)
        for b in fx._bursts:
            assert area.left <= b.x <= area.right
            assert area.top <= b.y <= area.bottom
