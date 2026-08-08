"""Todo boss liga o `CriticalDamageFX` — e liga onde o efeito realmente roda.

O sistema em si é testado sozinho em `test_critical_damage_fx.py`. Aqui o alvo é a
FIAÇÃO de cada boss, que falha em silêncio de dois jeitos:

  1. `update` do efeito colocado DEPOIS de um `return` cedo da FSM do boss. Foi
     o que aconteceu com o `MountainSerpentBoss`: ele tem um `return [], []` na
     intro da cabeça, e o fogo simplesmente nunca aparecia. Nada quebra, nada
     avisa — só não acende.
  2. Área de emissão montada de uma fonte errada (`self.rect` de um boss que
     devolve rect fora da tela quando invulnerável, ou caixa cheia de um corpo
     que fica quase todo fora da vista).

O fogo é DANO ACUMULADO, não estado de fase: tem que acender em qualquer ponto
da FSM em que o boss esteja, desde que a vida esteja baixa.
"""

from typing import Any, Callable

import pygame
import pytest

from game.entities.bosses.boss import Boss
from game.entities.bosses.cloud_archmage_boss import CloudArchmageBoss
from game.entities.bosses.giant_meteor_boss import GiantMeteorBoss
from game.entities.bosses.mountain_serpent_boss import MountainSerpentBoss
from game.entities.bosses.slime_boss import SlimeBoss
from game.entities.bosses.spike_boss import SpikeBoss
from game.entities.bosses.stone_golem_boss import StoneGolemBoss
from game.systems.entity_manager import EntityManager

DT = 1 / 60


def _boss(nome: str) -> tuple[Any, Callable[[Any], None]]:
    """Instancia o boss e devolve (boss, tick). Assinaturas de `update` divergem."""
    em = EntityManager()
    if nome == "Boss":
        b = Boss(550.0, 120.0)
        b.y = b.target_y
        return b, lambda x: x.update(DT, 640.0, 600.0)
    if nome == "SpikeBoss":
        b = SpikeBoss(500.0, 120.0)
        b.y = b.target_y
        b.state = "active"
        return b, lambda x: x.update(DT, 640.0, 600.0, [])
    if nome == "SlimeBoss":
        b = SlimeBoss(0.0, 0.0)
        b.y = b.target_y
        return b, lambda x: x.update(DT, 640.0, 600.0, em)
    if nome == "GiantMeteorBoss":
        b = GiantMeteorBoss(0.0, 0.0)
        b.y = b.target_y
        b.state = "active"
        return b, lambda x: x.update(DT, em)
    if nome == "StoneGolemBoss":
        b = StoneGolemBoss(600.0, 120.0)
        return b, lambda x: x.update(DT, 640.0, 600.0, em)
    if nome == "CloudArchmageBoss":
        b = CloudArchmageBoss()
        b.y = 80.0
        return b, lambda x: x.update(DT, (640.0, 600.0))
    if nome == "MountainSerpentBoss":
        return MountainSerpentBoss(), lambda x: x.update(DT, 640.0, 600.0)
    raise AssertionError(nome)


BOSSES = [
    "Boss",
    "SpikeBoss",
    "SlimeBoss",
    "GiantMeteorBoss",
    "StoneGolemBoss",
    "CloudArchmageBoss",
    "MountainSerpentBoss",
]


@pytest.mark.parametrize("nome", BOSSES)
class TestFiacao:
    def test_tem_o_efeito(self, nome):
        boss, _ = _boss(nome)
        assert hasattr(boss, "critical_fx")

    def test_com_vida_cheia_nao_pega_fogo(self, nome):
        boss, tick = _boss(nome)
        for _ in range(30):
            tick(boss)
        assert not boss.critical_fx.emitting
        assert not boss.critical_fx.has_particles

    def test_com_vida_baixa_pega_fogo(self, nome):
        """O teste que a serpente reprovava: o `update` do efeito tem que rodar
        em qualquer fase da FSM, não só nas que chegam ao fim do método."""
        boss, tick = _boss(nome)
        boss.health = max(1, int(boss.max_health * 0.05))
        for _ in range(120):
            tick(boss)
        assert boss.critical_fx.intensity > 0.5
        assert boss.critical_fx.has_particles

    def test_desenhar_com_fogo_nao_quebra(self, nome):
        boss, tick = _boss(nome)
        boss.health = max(1, int(boss.max_health * 0.05))
        surface = pygame.Surface((1280, 720), pygame.SRCALPHA)
        for _ in range(120):
            tick(boss)
            boss.draw(surface)

    def test_emite_na_regiao_do_corpo(self, nome):
        """A área tem que sair da posição REAL do corpo. Se alguém trocar por
        `self.rect` num boss que devolve rect fora da tela enquanto invulnerável,
        o fogo vai para (-1000, -1000) e este teste pega."""
        boss, tick = _boss(nome)
        boss.health = max(1, int(boss.max_health * 0.05))
        for _ in range(120):
            tick(boss)
        longe = [
            p
            for p in list(boss.critical_fx._bursts) + list(boss.critical_fx._smoke)
            if p.x < -600 or p.y < -600
        ]
        assert longe == []
