"""Descoberta da arte dos upgrades por pasta (`upgrade_icons`).

A estrutura existe antes da arte: hoje TODO upgrade cai no fallback (medalhão
de letra), e cada PNG que aparecer em `assets/images/upgrades/` passa a ser
usado sem código novo. O que estes testes travam é justamente o contrato que
torna isso possível — inclusive o cache da ausência, que é o que evita 23
acessos a disco por frame.
"""

from pathlib import Path

import pygame
import pytest

from game.core.upgrades import list_all_upgrades_meta
from game.scenes import upgrade_icons


@pytest.fixture(autouse=True)
def cache_limpo():
    upgrade_icons.clear_cache()
    yield
    upgrade_icons.clear_cache()


def test_sem_arte_o_fallback_e_sinalizado_por_none():
    """`None` é o estado NORMAL enquanto os ícones não são produzidos."""
    assert upgrade_icons.icon_surface("nao_existe_este_upgrade", 32) is None
    assert not upgrade_icons.has_icon("nao_existe_este_upgrade")


def test_todo_upgrade_do_elenco_responde_sem_estourar():
    """Nenhum `icon_id` pode levantar exceção — com ou sem arte."""
    for meta in list_all_upgrades_meta():
        upgrade_icons.icon_surface(meta.icon_id, 48)  # não deve levantar


def test_ausencia_fica_em_cache(monkeypatch):
    """Sem cache negativo seriam 23 `exists()` por frame, no laço de render."""
    chamadas = []
    original = Path.exists

    def espiao(self):
        chamadas.append(self)
        return original(self)

    monkeypatch.setattr(Path, "exists", espiao)

    for _ in range(10):
        upgrade_icons.icon_surface("qualquer", 32)

    assert len(chamadas) == 1, "só a primeira consulta pode tocar o disco"


def test_arte_presente_e_usada_e_escalada(tmp_path, monkeypatch):
    """Quando o PNG existir, ele entra no lugar do medalhão — já escalado."""
    monkeypatch.setattr(upgrade_icons, "ICON_DIR", tmp_path)
    arte = pygame.Surface((7, 7), pygame.SRCALPHA)
    arte.fill((255, 0, 0, 255))
    pygame.image.save(arte, str(tmp_path / "heal.png"))

    surf = upgrade_icons.icon_surface("heal", 40)

    assert surf is not None
    assert surf.get_size() == (40, 40)
    assert upgrade_icons.has_icon("heal")


def test_png_corrompido_cai_no_fallback(tmp_path, monkeypatch):
    """Arquivo ilegível não pode derrubar a tela inteira."""
    monkeypatch.setattr(upgrade_icons, "ICON_DIR", tmp_path)
    (tmp_path / "emp.png").write_bytes(b"isto nao e um png")

    assert upgrade_icons.icon_surface("emp", 32) is None


def test_tamanho_invalido_nao_estoura():
    assert upgrade_icons.icon_surface("heal", 0) is None
    assert upgrade_icons.icon_surface("heal", -5) is None
