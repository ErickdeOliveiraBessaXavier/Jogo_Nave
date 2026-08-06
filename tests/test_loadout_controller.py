"""Regras de equipar upgrade e escolher nave (`LoadoutController`).

São as regras que o jogador sente a cada clique na tela de Aprimoramentos.
Antes da extração elas moravam entre um `sound_manager.play_*` e um
`floating_messages.append`, e só dava para exercitá-las abrindo o jogo — este
arquivo existe porque a fronteira nova permite testá-las sem pygame de vídeo,
sem cena e sem app.
"""

import pytest

from game.core.meta_progression import PlayerProfile
from game.core.ship_types import all_ship_profiles, get_ship_profile
from game.core.upgrades import UpgradeRole, UpgradeType, list_all_upgrades_meta
from game.core.upgrades_config import SLOT_UNLOCK_COSTS, UPGRADE_SLOT_COUNT
from game.systems.loadout_controller import LoadoutAction, LoadoutController

UPGRADES = sorted(list_all_upgrades_meta(), key=lambda u: u.name)


@pytest.fixture
def controller(tmp_path):
    profile = PlayerProfile(profile_path=tmp_path / "p.json")
    return LoadoutController(profile, UPGRADES)


def meta(tipo: UpgradeType):
    return next(u for u in UPGRADES if u.type is tipo)


def destrava_todos_os_slots(controller: LoadoutController) -> None:
    controller.profile.add_stars(sum(SLOT_UNLOCK_COSTS))
    for i in range(1, UPGRADE_SLOT_COUNT):
        assert controller.profile.unlock_slot(i)


# ── equipar / desequipar ────────────────────────────────────────────────────


def test_equipa_no_primeiro_slot_livre(controller):
    destrava_todos_os_slots(controller)
    controller.profile.equip_upgrade(UpgradeType.HEAL, 0)

    r = controller.toggle_upgrade(meta(UpgradeType.EMP))

    assert r.action is LoadoutAction.EQUIPPED
    assert r.slot_index == 1, "deveria pular o slot 0, que está ocupado"
    assert controller.profile.upgrade_loadout[1] is UpgradeType.EMP


def test_clicar_no_upgrade_ja_equipado_desequipa(controller):
    destrava_todos_os_slots(controller)
    alvo = meta(UpgradeType.EMP)
    controller.toggle_upgrade(alvo)

    r = controller.toggle_upgrade(alvo)

    assert r.action is LoadoutAction.UNEQUIPPED
    assert r.slot_index == 0
    assert controller.profile.upgrade_loadout[0] is None


def test_sem_slot_livre_recusa_e_aponta_o_ultimo_slot(controller):
    """A recusa ancora no último slot destravado — o que precisa ser esvaziado."""
    destrava_todos_os_slots(controller)
    for i, tipo in enumerate(
        (UpgradeType.HEAL, UpgradeType.EMP, UpgradeType.SHIELD_BURST)
    ):
        controller.profile.equip_upgrade(tipo, i)

    r = controller.toggle_upgrade(meta(UpgradeType.GIANT_SHOT))

    assert r.action is LoadoutAction.DENIED_NO_FREE_SLOT
    assert r.denied
    assert r.slot_index == UPGRADE_SLOT_COUNT - 1


def test_slot_travado_nao_conta_como_livre(controller):
    """Com 1 slot destravado, o segundo upgrade não tem para onde ir."""
    assert controller.profile.unlocked_slots == 1
    controller.toggle_upgrade(meta(UpgradeType.HEAL))

    r = controller.toggle_upgrade(meta(UpgradeType.EMP))

    assert r.action is LoadoutAction.DENIED_NO_FREE_SLOT


def test_upgrade_bloqueado_recusa_sem_mexer_no_loadout(controller):
    alvo = meta(UpgradeType.EMP)
    controller.profile.unlocked_upgrades.discard(UpgradeType.EMP)

    r = controller.toggle_upgrade(alvo)

    assert r.action is LoadoutAction.DENIED_UPGRADE_LOCKED
    assert all(u is None for u in controller.profile.upgrade_loadout)


# ── slots ───────────────────────────────────────────────────────────────────


def test_clicar_no_slot_equipado_devolve_o_upgrade(controller):
    controller.profile.equip_upgrade(UpgradeType.HEAL, 0)

    r = controller.press_slot(0)

    assert r.action is LoadoutAction.UNEQUIPPED
    assert r.meta is not None and r.meta.type is UpgradeType.HEAL
    assert controller.profile.upgrade_loadout[0] is None


def test_clicar_no_slot_vazio_nao_faz_nada(controller):
    r = controller.press_slot(0)
    assert r.action is LoadoutAction.NOTHING


def test_slot_travado_destrava_com_estrelas(controller):
    controller.profile.add_stars(SLOT_UNLOCK_COSTS[1])

    r = controller.press_slot(1)

    assert r.action is LoadoutAction.SLOT_UNLOCKED
    assert controller.profile.unlocked_slots == 2
    assert controller.profile.available_stars == 0


def test_slot_travado_sem_estrelas_recusa(controller):
    r = controller.press_slot(1)

    assert r.action is LoadoutAction.DENIED_SLOT_COST
    assert r.denied
    assert controller.profile.unlocked_slots == 1


# ── naves ───────────────────────────────────────────────────────────────────


def test_selecionar_nave_desbloqueada(controller):
    outra = next(
        s for s in all_ship_profiles() if s.id != controller.profile.selected_ship
    )
    controller.profile.unlocked_ships.add(outra.id)

    r = controller.press_ship(outra)

    assert r.action is LoadoutAction.SHIP_SELECTED
    assert controller.profile.selected_ship == outra.id


def test_clicar_na_nave_em_uso_nao_e_evento(controller):
    atual = get_ship_profile(controller.profile.selected_ship)
    assert controller.press_ship(atual).action is LoadoutAction.NOTHING


def test_comprar_nave_ja_deixa_ela_selecionada(controller):
    """Comprar e não equipar seria um segundo passo depois de gastar as estrelas."""
    alvo = next(s for s in all_ship_profiles() if s.unlock_cost > 0)
    controller.profile.add_stars(alvo.unlock_cost)

    r = controller.press_ship(alvo)

    assert r.action is LoadoutAction.SHIP_PURCHASED
    assert controller.profile.is_ship_unlocked(alvo.id)
    assert controller.profile.selected_ship == alvo.id


def test_nave_cara_demais_recusa(controller):
    alvo = max(all_ship_profiles(), key=lambda s: s.unlock_cost)

    r = controller.press_ship(alvo)

    assert r.action is LoadoutAction.DENIED_SHIP_COST
    assert not controller.profile.is_ship_unlocked(alvo.id)


# ── filtro das abas ─────────────────────────────────────────────────────────


def test_aba_todos_traz_o_elenco_inteiro(controller):
    assert len(controller.upgrades_for_role(None)) == len(UPGRADES)


@pytest.mark.parametrize("papel", list(UpgradeRole))
def test_toda_aba_tem_conteudo(controller, papel):
    """Aba vazia lê como bug — foi por isso que os papéis viraram quatro."""
    assert controller.upgrades_for_role(papel), f"aba {papel.name} está vazia"


def test_filtro_por_papel_nao_mistura(controller):
    for u in controller.upgrades_for_role(UpgradeRole.DEFENSE):
        assert u.role is UpgradeRole.DEFENSE


def test_soma_das_abas_cobre_todos_os_upgrades(controller):
    total = sum(len(controller.upgrades_for_role(p)) for p in UpgradeRole)
    assert total == len(UPGRADES), "algum upgrade ficou sem aba ou aparece em duas"


# ── ajuste do loadout salvo ─────────────────────────────────────────────────


def test_loadout_curto_e_completado_no_construtor(tmp_path):
    profile = PlayerProfile(profile_path=tmp_path / "p.json")
    profile.upgrade_loadout = [UpgradeType.HEAL]

    LoadoutController(profile, UPGRADES)

    assert len(profile.upgrade_loadout) == UPGRADE_SLOT_COUNT
    assert profile.upgrade_loadout[0] is UpgradeType.HEAL


def test_loadout_longo_e_truncado_no_construtor(tmp_path):
    profile = PlayerProfile(profile_path=tmp_path / "p.json")
    profile.upgrade_loadout = [UpgradeType.HEAL] * (UPGRADE_SLOT_COUNT + 4)

    LoadoutController(profile, UPGRADES)

    assert len(profile.upgrade_loadout) == UPGRADE_SLOT_COUNT
