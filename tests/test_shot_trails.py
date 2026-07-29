"""Animação dos rastros do Cryo Shot e do Corrosive Ammo.

Os dois rastros existem para o jogador **reconhecer o upgrade ativo antes de o
tiro acertar qualquer coisa**. Antes eram carimbos estáticos: três blocos e três
pingos nas mesmas posições relativas, frame após frame.

O que estes testes guardam:

1. **os rastros ANIMAM** — quadro a quadro o desenho muda. É o teste que quebra
   se alguém voltar a derivar as posições só do `rect` da bala;
2. **a animação é do UPDATE, não do relógio da máquina** (§3) — o `draw` é puro
   e o rastro para junto com o jogo na pausa. Um `pygame.time.get_ticks()` aqui
   passaria despercebido até alguém pausar o jogo e ver o gelo continuar
   escorrendo;
3. **o gelo ESCOA em ciclo** — bloco novo sob o projétil, cada um encolhendo até
   sumir na última casa, sem buraco e sem salto na virada do ciclo;
4. **o ácido SERPENTEIA** — a onda percorre a cauda (os pingos não balançam
   juntos) e a amplitude cresce para trás;
5. **a trajetória não muda** — é o requisito explícito: desenhar o rastro não
   pode mover a bala nem tocar na velocidade dela.
"""

import math

import pygame
import pytest

from game.entities.projectiles.bullet import Bullet
from game.entities.projectiles.bullet_fx.corrosive import (
    _CORROSIVE_TRAIL_SEGMENTS,
    corrosive_trail_segments,
)
from game.entities.projectiles.bullet_fx.cryo import (
    _CRYO_TRAIL,
    _CRYO_TRAIL_STEP_TIME,
    cryo_trail_blocks,
)
from game.entities.projectiles.bullet_pool import BulletPool

SLOTS = len(_CRYO_TRAIL)


def _bala(*, cryo=False, corrosive=False) -> Bullet:
    b = Bullet(150.0, 150.0, cryo=cryo, corrosive=corrosive)
    b.w, b.h = 10, 14
    b.vx, b.vy = 0.0, -420.0
    return b


def _pintado(bala, anim_time: float) -> frozenset:
    """Pixels pintados por um frame de desenho, para um dado tempo de animação."""
    bala.anim_time = anim_time
    canvas = pygame.Surface((300, 300))
    canvas.fill((0, 0, 0))
    bala.draw(canvas)
    return frozenset(
        (x, y)
        for x in range(300)
        for y in range(300)
        if canvas.get_at((x, y))[:3] != (0, 0, 0)
    )


# ---------------------------------------------------------------------------
# O relógio — comum aos dois
# ---------------------------------------------------------------------------


class TestRelogioDaAnimacao:
    def test_o_update_alimenta_o_acumulador(self):
        b = _bala(cryo=True)
        assert b.anim_time == 0.0
        b.update(0.25)
        assert b.anim_time == pytest.approx(0.25)

    def test_o_draw_NAO_mexe_no_acumulador(self):
        """§3: `draw()` desenha. Qualquer mutação pertence ao update."""
        b = _bala(corrosive=True)
        b.anim_time = 1.234
        canvas = pygame.Surface((300, 300))
        b.draw(canvas)
        assert b.anim_time == pytest.approx(1.234)

    def test_o_rastro_congela_com_o_jogo_parado(self):
        """Sem update não há avanço: é o que faz o rastro parar na pausa e
        desacelerar na câmera lenta, em vez de correr por fora do jogo."""
        for kwargs in ({"cryo": True}, {"corrosive": True}):
            b = _bala(**kwargs)
            antes = _pintado(b, b.anim_time)
            for _ in range(30):  # 30 frames desenhados, nenhum update
                b.draw(pygame.Surface((300, 300)))
            assert _pintado(b, b.anim_time) == antes, kwargs

    def test_o_pool_zera_o_acumulador(self):
        """Bala reciclada com o relógio herdado entraria no meio do ciclo, com
        um salto visível — o mesmo risco de resíduo dos outros campos."""
        pool = BulletPool(initial_size=1)
        primeira = pool.get(0.0, 0.0, cryo=True)
        primeira.update(3.7)
        assert primeira.anim_time > 0.0

        pool.release(primeira)
        segunda = pool.get(0.0, 0.0, cryo=True)
        assert segunda is primeira, "o teste não reusou a bala; pool mudou"
        assert segunda.anim_time == 0.0


# ---------------------------------------------------------------------------
# Gelo: o escoamento
# ---------------------------------------------------------------------------


class TestRastroDeGelo:
    def test_o_rastro_muda_de_um_frame_para_o_outro(self):
        b = _bala(cryo=True)
        a = _pintado(b, 0.0)
        c = _pintado(b, _CRYO_TRAIL_STEP_TIME * 0.5)
        assert a != c, "o rastro de gelo continua estático"

    def test_mantem_tres_blocos(self):
        """O conceito de três blocos é do pedido; o que muda é a animação."""
        for i in range(40):
            blocos = cryo_trail_blocks(i * _CRYO_TRAIL_STEP_TIME / 13.0)
            assert len(blocos) == SLOTS, f"{len(blocos)} blocos em t={i}"

    def test_os_blocos_encolhem_conforme_descem(self):
        for t in (0.0, 0.03, 0.07, 0.1):
            blocos = cryo_trail_blocks(t)
            casas = [slot for slot, _ in blocos]
            tamanhos = [escala for _, escala in blocos]
            assert casas == sorted(casas)
            assert tamanhos == sorted(tamanhos, reverse=True), t

    def test_um_bloco_novo_surge_na_FRENTE_do_rastro(self):
        """Sempre na casa 0 e no tamanho cheio, nunca no meio da fila: é o que
        dá a leitura de gelo escorrendo em vez de blocos piscando."""
        recem = cryo_trail_blocks(0.0)[0]
        assert recem[0] == pytest.approx(0.0)
        assert recem[1] == pytest.approx(1.0)

    def test_os_tres_blocos_ficam_visiveis_atras_do_cristal(self):
        """A casa 0 é desenhada um passo ATRÁS do projétil. Desenhada sobre ele,
        o bloco recém-nascido some sob o sprite e o rastro exibe dois blocos."""
        b = _bala(cryo=True)
        b.anim_time = 0.0
        canvas = pygame.Surface((60, 60))
        canvas.fill((0, 0, 0))
        b.x, b.y = 30 - b.w / 2, 8
        b.draw(canvas)

        cauda = b.rect.bottom + 1  # abaixo do sprite: só rastro
        linhas_com_bloco = {
            y
            for y in range(cauda, 60)
            for x in range(60)
            if canvas.get_at((x, y))[:3] in _CRYO_TRAIL
        }
        # Três blocos separados por espaços → pelo menos três faixas distintas.
        faixas = 0
        anterior = -5
        for y in sorted(linhas_com_bloco):
            if y - anterior > 1:
                faixas += 1
            anterior = y
        assert faixas >= 3, f"só {faixas} bloco(s) visível(is) atrás do cristal"

    def test_o_ultimo_bloco_some_ao_chegar_na_ponta(self):
        quase_fim = cryo_trail_blocks(_CRYO_TRAIL_STEP_TIME * 0.99)[-1]
        assert quase_fim[0] > SLOTS - 1
        assert quase_fim[1] < 0.02, "o último bloco não chegou a desaparecer"

    def test_cada_bloco_assume_a_casa_do_anterior_no_ciclo(self):
        """O ciclo pedido: o 2º assume o tamanho do 1º, o 3º o do 2º. Depois de
        um passo inteiro, as casas ocupadas são as mesmas — só que uma adiante."""
        inicio = [slot for slot, _ in cryo_trail_blocks(0.0)]
        depois = [slot for slot, _ in cryo_trail_blocks(_CRYO_TRAIL_STEP_TIME)]
        assert inicio == pytest.approx(depois), "o ciclo não fecha"

    def test_a_virada_do_ciclo_e_continua(self):
        """Sem salto: na virada nasce um bloco e some outro, então comparar por
        índice compara blocos diferentes. O que tem de valer é que todo bloco de
        depois — menos o recém-nascido — continua de onde algum estava."""
        eps = _CRYO_TRAIL_STEP_TIME / 60.0
        antes = [slot for slot, _ in cryo_trail_blocks(_CRYO_TRAIL_STEP_TIME - eps)]
        depois = [slot for slot, _ in cryo_trail_blocks(_CRYO_TRAIL_STEP_TIME + eps)]
        assert len(antes) == len(depois) == SLOTS

        nascido, herdados = depois[0], depois[1:]
        assert nascido < 0.05, f"o bloco novo nasceu longe do projétil: {nascido}"
        for d in herdados:
            assert any(abs(d - a) < 0.1 for a in antes), (
                f"salto na virada: {antes} → {depois}"
            )

    def test_nenhum_bloco_sai_do_rastro(self):
        for i in range(120):
            for slot, escala in cryo_trail_blocks(i * 0.0037):
                assert 0.0 <= slot < SLOTS
                assert 0.0 < escala <= 1.0


# ---------------------------------------------------------------------------
# Ácido: o serpenteio
# ---------------------------------------------------------------------------


class TestRastroCorrosivo:
    def test_o_rastro_muda_de_um_frame_para_o_outro(self):
        b = _bala(corrosive=True)
        a = _pintado(b, 0.0)
        c = _pintado(b, 0.08)
        assert a != c, "o rastro de ácido continua estático"

    def test_a_cauda_ondula_para_os_DOIS_lados(self):
        """Ondulação de verdade cruza o eixo; um desvio só para um lado seria
        uma curva, não uma serpente."""
        desvios = [
            sway
            for t in (i * 0.01 for i in range(60))
            for _slot, sway, _escala in corrosive_trail_segments(t)
        ]
        assert max(desvios) > 0.2 and min(desvios) < -0.2

    def test_a_onda_PERCORRE_a_cauda_e_nao_balanca_junto(self):
        """A defasagem entre pingos vizinhos é o que dá a leitura de serpente.
        Sem ela, a cauda inteira oscila em bloco — que lê como tremor."""
        segs = corrosive_trail_segments(0.0)
        # Normaliza pelo perfil de amplitude para comparar só a FASE.
        fases = [sway for _slot, sway, _e in segs]
        assert len({round(f, 3) for f in fases}) > 1, "todos os pingos em fase"

        # E a fase tem de girar: dois pingos separados por meia defasagem não
        # podem estar sempre do mesmo lado do eixo.
        opostos = any(
            fases[i] * fases[j] < 0 for i in range(len(fases)) for j in range(i + 1, len(fases))
        )
        assert opostos, "a onda não chega a inverter ao longo da cauda"

    def test_a_amplitude_cresce_para_a_ponta_da_cauda(self):
        """Perto do projétil o líquido ainda está preso a ele; longe, chicoteia
        solto. É o perfil de um rabo de serpente."""
        picos = [0.0] * _CORROSIVE_TRAIL_SEGMENTS
        for i in range(400):
            for k, (_slot, sway, _e) in enumerate(corrosive_trail_segments(i * 0.005)):
                picos[k] = max(picos[k], abs(sway))
        assert picos[-1] > picos[0] * 1.5, f"amplitude achatada: {picos}"

    def test_os_pingos_borbulham_de_tamanho(self):
        tamanhos = {
            round(escala, 4)
            for t in (i * 0.01 for i in range(60))
            for _slot, _sway, escala in corrosive_trail_segments(t)
        }
        assert len(tamanhos) > 20, "o tamanho dos pingos não varia"

    def test_o_borbulhar_e_independente_do_serpenteio(self):
        """Sincronizados, os dois leriam como uma animação em loop; separados,
        leem como líquido instável."""
        from game.entities.projectiles.bullet_fx.corrosive import (
            _CORROSIVE_BUBBLE_PERIOD,
            _CORROSIVE_WAVE_PERIOD,
        )

        assert _CORROSIVE_BUBBLE_PERIOD != _CORROSIVE_WAVE_PERIOD
        razao = _CORROSIVE_WAVE_PERIOD / _CORROSIVE_BUBBLE_PERIOD
        assert abs(razao - round(razao)) > 0.05, "os dois ritmos batem em fase"

    def test_a_cauda_afina_para_tras(self):
        # Média no tempo: o borbulhar não pode esconder o afinamento.
        somas = [0.0] * _CORROSIVE_TRAIL_SEGMENTS
        for i in range(400):
            for k, (_slot, _sway, escala) in enumerate(corrosive_trail_segments(i * 0.005)):
                somas[k] += escala
        assert somas == sorted(somas, reverse=True), f"cauda sem afinamento: {somas}"

    def test_os_pingos_ficam_em_casas_crescentes(self):
        casas = [slot for slot, _s, _e in corrosive_trail_segments(0.3)]
        assert casas == sorted(casas)
        assert all(c > 0 for c in casas), "pingo dentro do projétil"

    def test_o_tamanho_nunca_zera_nem_estoura(self):
        for i in range(400):
            for _slot, sway, escala in corrosive_trail_segments(i * 0.005):
                assert 0.0 < escala < 2.0
                assert math.isfinite(sway)


# ---------------------------------------------------------------------------
# O requisito explícito: só o rastro muda
# ---------------------------------------------------------------------------


class TestTrajetoriaIntacta:
    def test_desenhar_o_rastro_nao_move_a_bala(self):
        for kwargs in ({"cryo": True}, {"corrosive": True}):
            b = _bala(**kwargs)
            b.anim_time = 0.7
            antes = (b.x, b.y, b.vx, b.vy)
            for _ in range(10):
                b.draw(pygame.Surface((300, 300)))
            assert (b.x, b.y, b.vx, b.vy) == antes, kwargs

    def test_a_animacao_nao_altera_o_deslocamento_por_frame(self):
        """Duas balas iguais, uma com o relógio adiantado: têm de andar o mesmo
        tanto. O rastro é enfeite, não física."""
        for kwargs in ({"cryo": True}, {"corrosive": True}):
            a, b = _bala(**kwargs), _bala(**kwargs)
            b.anim_time = 5.0
            for _ in range(20):
                a.update(1 / 60)
                b.update(1 / 60)
            assert (a.x, a.y) == pytest.approx((b.x, b.y)), kwargs

    def test_bala_parada_nao_desenha_rastro(self):
        """O rastro sai da direção do voo; sem velocidade não há eixo — e o
        `anim_time` correndo não pode inventar um."""
        for kwargs in ({"cryo": True}, {"corrosive": True}):
            b = _bala(**kwargs)
            b.vx = b.vy = 0.0
            parada = _pintado(b, 0.0)
            assert _pintado(b, 2.3) == parada, kwargs
