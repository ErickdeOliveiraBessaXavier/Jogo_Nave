"""Um power-up por vez em tela — a regra e os dois produtores que a respeitam.

O jogo cria power-up por dois caminhos: o relógio do `PowerUpSpawner` e os drops
de morte que passam pelo `EntityManager`. Antes desta regra, os dois somavam sem
se enxergar — e um ataque que solta prêmio por peça destruída (as esferas
premiadas da Tríade) enfileirava vários de uma vez sobre o que o relógio já tinha
posto na arena.

Lógica pura (§16): nada aqui instancia cena nem abre janela.
"""

from __future__ import annotations

from game.core.config import PowerUpType
from game.entities.pickups.powerup import PowerUp, screen_has_powerup
from game.entities.bosses.city.triad_orb import OrbBehavior, TriadOrb
from game.systems.entity_manager import EntityManager
from game.systems.spawner import PowerUpSpawner

DT = 1.0 / 60.0


def _novo(kind: PowerUpType = PowerUpType.SHIELD) -> PowerUp:
    return PowerUp(kind)


def _orbe() -> TriadOrb:
    """Esfera comum, viva e coletável — a matéria-prima do sorteio de prêmio."""
    return TriadOrb(100.0, 100.0, OrbBehavior.RING, birth=0.0)


# ── A regra ──────────────────────────────────────────────────────────────────
class TestScreenHasPowerup:
    def test_tela_vazia_nao_trava(self):
        assert not screen_has_powerup([])

    def test_um_coletavel_trava(self):
        assert screen_has_powerup([_novo()])

    def test_quem_dissolve_nao_trava(self):
        """Já não dá para coletar — segurá-lo como bloqueio só adiaria o próximo
        sem nada em tela justificando a espera."""
        pu = _novo()
        pu.begin_fade_out()
        assert not screen_has_powerup([pu])

    def test_morto_nao_trava(self):
        pu = _novo()
        pu.dead = True
        assert not screen_has_powerup([pu])


# ── Produtor 1: o relógio ────────────────────────────────────────────────────
class TestSpawnerRespeitaOGate:
    def test_com_a_tela_vazia_o_relogio_entrega(self):
        spawner = PowerUpSpawner()
        powerups: list = []
        for _ in range(6000):
            spawner.update(DT, powerups)
            if powerups:
                break
        assert powerups, "o relógio nunca entregou um power-up"

    def test_com_um_em_tela_o_relogio_nao_empilha(self):
        spawner = PowerUpSpawner()
        powerups: list = [_novo()]
        # O pickup fica parado no topo: sem `update` ele não desce nem sai da
        # tela, então continua bloqueando por toda a janela medida.
        for _ in range(12000):
            spawner.update(DT, powerups)
        assert len(powerups) == 1, f"empilhou {len(powerups)} power-ups em tela"

    def test_o_relogio_reinicia_em_vez_de_guardar_credito(self):
        """§14: crédito acumulado com o gate fechado dispararia tudo no instante
        em que ele abre — e a tela nunca ficaria vazia."""
        spawner = PowerUpSpawner()
        bloqueio = _novo()
        powerups: list = [bloqueio]
        for _ in range(12000):
            spawner.update(DT, powerups)
        powerups.clear()
        # Com a tela limpa, o próximo não pode nascer no frame seguinte.
        spawner.update(DT, powerups)
        assert not powerups, "o power-up seguinte nasceu no frame em que a tela limpou"


# ── Produtor 2: os drops de morte ────────────────────────────────────────────
class TestDropsRespeitamOGate:
    def test_drop_entra_com_a_tela_vazia(self):
        em = EntityManager()
        em.add_powerups((_novo(),))
        assert len(em.powerups) == 1

    def test_drop_e_descartado_com_um_em_tela(self):
        """Rede de segurança. O caminho normal é o prêmio nem ser prometido —
        ver `TestPremioNaoNasceBloqueado`."""
        em = EntityManager()
        em.powerups.append(_novo())
        em.add_powerups((_novo(PowerUpType.SPREAD_SHOT),))
        assert len(em.powerups) == 1, "o drop empilhou sobre o que já estava em tela"

    def test_salva_de_drops_entrega_no_maximo_um(self):
        """O caso da Tríade: várias esferas premiadas caindo no mesmo frame."""
        em = EntityManager()
        em.add_powerups(tuple(_novo(PowerUpType.SPREAD_SHOT) for _ in range(5)))
        assert len(em.powerups) == 1, f"a salva entregou {len(em.powerups)} de uma vez"

    def test_tupla_vazia_e_no_op(self):
        em = EntityManager()
        em.add_powerups(())
        assert em.powerups == []


# ── A promessa não é feita se não puder ser paga ─────────────────────────────
class TestPremioNaoNasceBloqueado:
    """A esfera premiada da Tríade é de COR DIFERENTE: ela promete prêmio antes
    de o jogador gastar tiro nela. Prometer com um power-up já caindo (quando o
    drop seria descartado na entrega) ensina "o prêmio é aleatório" — o oposto
    do que a cor existe para ensinar. Por isso o gate é no nascimento."""

    def _boss(self):
        from game.entities.bosses.city.triad_boss import TriadBoss

        return TriadBoss()

    def test_sorteia_com_a_arena_limpa(self):
        boss = self._boss()
        boss.arena_has_powerup = False
        orbes = [_orbe() for _ in range(40)]
        for _ in range(200):
            boss._sortear_premio(orbes)
            if any(o.prize for o in orbes):
                return
        raise AssertionError("nenhum prêmio saiu em 200 sorteios com a arena limpa")

    def test_nao_sorteia_com_power_up_em_tela(self):
        boss = self._boss()
        boss.arena_has_powerup = True
        for _ in range(500):
            orbes = [_orbe() for _ in range(8)]
            boss._sortear_premio(orbes)
            assert not any(o.prize for o in orbes), "prometeu prêmio que não pagaria"

    def test_has_prize_pending_reflete_a_esfera_viva(self):
        boss = self._boss()
        assert not boss.has_prize_pending
        orbe = _orbe()
        boss._orbs.append(orbe)
        assert not boss.has_prize_pending, "esfera comum não é promessa"
        orbe.prize = True
        assert boss.has_prize_pending
        orbe.dead = True
        assert not boss.has_prize_pending, "esfera morta ainda contava como promessa"


class TestRewardPendingUneAsDuasFontes:
    def test_arena_vazia(self):
        assert not EntityManager().reward_pending()

    def test_power_up_em_tela_conta(self):
        em = EntityManager()
        em.powerups.append(_novo())
        assert em.reward_pending()

    def test_boss_sem_premio_nao_conta(self):
        em = EntityManager()
        em.boss = object()  # boss que nem declara o atributo (§5: getattr)
        assert not em.reward_pending()

    def test_esfera_premiada_viva_conta(self):
        from game.entities.bosses.city.triad_boss import TriadBoss

        em = EntityManager()
        boss = TriadBoss()
        orbe = _orbe()
        orbe.prize = True
        boss._orbs.append(orbe)
        em.boss = boss
        assert em.reward_pending(), "a esfera premiada não segurou o relógio"

    def test_o_relogio_segura_enquanto_a_promessa_existe(self):
        spawner = PowerUpSpawner()
        powerups: list = []
        for _ in range(12000):
            spawner.update(DT, powerups, reward_pending=True)
        assert not powerups, "o relógio soltou item com prêmio já prometido"
