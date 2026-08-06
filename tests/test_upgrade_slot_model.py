"""Modelo de slots de upgrade: três slots, um upgrade cada, sem peso.

Cobre as duas regras que a mudança criou e que nada mais exercita:

- **Migração** dos perfis salvos no modelo antigo (8 slots + orçamento de peso).
  É a parte que mexe em dado durável do jogador — errar aqui apaga upgrades
  equipados ou some com estrelas pagas, e o sintoma só aparece no boot seguinte.
- **Equipar** deixou de consultar peso. O teste trava a regra nova para que uma
  reintrodução de orçamento não passe despercebida.
"""

import json

import pytest

from game.core.meta_progression import PlayerProfile
from game.core.upgrades import UPGRADES_META, UpgradeType
from game.core.upgrades_config import (
    INITIAL_UNLOCKED_SLOTS,
    SLOT_UNLOCK_COSTS,
    UPGRADE_SLOT_COUNT,
    migrate_slot_model,
)

# Custos do modelo antigo, replicados aqui de propósito: se alguém mexer na
# tabela legada em `upgrades_config`, este teste tem de falhar em vez de
# acompanhar a mudança em silêncio.
_LEGACY_TOTAL_8_SLOTS = 3 + 5 + 10 + 20 + 35 + 50  # 123
_NOVO_TOTAL_3_SLOTS = sum(SLOT_UNLOCK_COSTS)  # 40


def test_modelo_tem_tres_slots_e_um_gratis():
    assert UPGRADE_SLOT_COUNT == 3
    assert INITIAL_UNLOCKED_SLOTS == 1
    assert len(SLOT_UNLOCK_COSTS) == UPGRADE_SLOT_COUNT
    assert SLOT_UNLOCK_COSTS[0] == 0


def test_migracao_devolve_estrelas_dos_slots_que_deixaram_de_existir():
    """Quem pagou pelos 8 slots recebe de volta o que passou do custo dos 3."""
    slots, gasto = migrate_slot_model(8, _LEGACY_TOTAL_8_SLOTS)
    assert slots == 3
    assert gasto == _NOVO_TOTAL_3_SLOTS
    devolvido = _LEGACY_TOTAL_8_SLOTS - gasto
    assert devolvido == 83


def test_migracao_nao_cobra_retroativamente_slot_ja_conquistado():
    """Os dois primeiros slots eram grátis no modelo antigo; continuam pagos."""
    slots, gasto = migrate_slot_model(2, 0)
    assert (slots, gasto) == (2, 0)


def test_migracao_e_idempotente():
    """Rodar de novo sobre um perfil já migrado não devolve estrela nenhuma.

    A migração roda a cada carga (não há flag no arquivo), então repetir tem de
    ser inofensivo — senão cada boot imprimiria estrelas."""
    primeira = migrate_slot_model(8, _LEGACY_TOTAL_8_SLOTS)
    segunda = migrate_slot_model(*primeira)
    assert segunda == primeira


def test_migracao_nunca_devolve_mais_do_que_foi_gasto():
    """Perfil editado à mão (8 slots, 0 gasto) não vira fábrica de estrelas."""
    _, gasto = migrate_slot_model(8, 0)
    assert gasto == 0


@pytest.fixture
def perfil_antigo(tmp_path):
    """Escreve um perfil no formato de 8 slots e devolve o caminho."""
    caminho = tmp_path / "player_profile.json"
    caminho.write_text(
        json.dumps(
            {
                # `level_stats` é o que marca o arquivo como perfil válido (ver
                # `_parse_profile_data`); sem ele a carga cai no caminho de
                # recuperação e o teste mediria os defaults, não a migração.
                "level_stats": {},
                "unlocked_slots": 8,
                "stars_collected": 500,
                "stars_spent": _LEGACY_TOTAL_8_SLOTS,
                "upgrade_loadout": [
                    "CRYO_SHOT",
                    "CHAIN_LIGHTNING",
                    "HOMING_SHOT",
                    "IMPLOSION_SHOT",
                    None,
                    None,
                    None,
                    None,
                ],
            }
        ),
        encoding="utf-8",
    )
    return caminho


def test_perfil_antigo_carrega_no_modelo_novo(perfil_antigo):
    profile = PlayerProfile(profile_path=perfil_antigo)

    assert profile.unlocked_slots == 3
    assert len(profile.upgrade_loadout) == 3
    # Os três primeiros equipados sobrevivem, na ordem.
    assert profile.upgrade_loadout == [
        UpgradeType.CRYO_SHOT,
        UpgradeType.CHAIN_LIGHTNING,
        UpgradeType.HOMING_SHOT,
    ]
    # E as estrelas dos slots perdidos voltaram para o saldo.
    assert profile.stars_spent == _NOVO_TOTAL_3_SLOTS
    assert profile.available_stars == 500 - _NOVO_TOTAL_3_SLOTS


def test_upgrade_pesado_cabe_em_qualquer_slot_destravado(tmp_path):
    """O `slot_weight` não gateia mais nada — é só tier exibido na tela."""
    profile = PlayerProfile(profile_path=tmp_path / "p.json")
    pesados = [t for t, m in UPGRADES_META.items() if m.slot_weight >= 3]
    assert pesados, "esperava upgrades de tier 3 no elenco"

    assert profile.unlocked_slots == 1
    assert profile.can_equip_upgrade(pesados[0], 0)
    # Dois pesados juntos também: o que limita é a contagem de slots.
    profile.add_stars(sum(SLOT_UNLOCK_COSTS))
    profile.unlock_slot(1)
    assert profile.can_equip_upgrade(pesados[0], 0)
    assert profile.can_equip_upgrade(pesados[1 % len(pesados)], 1)


def test_slot_travado_recusa_equipar(tmp_path):
    profile = PlayerProfile(profile_path=tmp_path / "p.json")
    assert profile.unlocked_slots == 1
    assert not profile.can_equip_upgrade(UpgradeType.HEAL, 1)
    assert not profile.can_equip_upgrade(UpgradeType.HEAL, UPGRADE_SLOT_COUNT)
    assert not profile.can_equip_upgrade(UpgradeType.HEAL, -1)
