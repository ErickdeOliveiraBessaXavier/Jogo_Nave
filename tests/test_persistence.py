"""Persistência atômica do §15 — save/load do perfil do jogador.

Cobre a cadeia de recuperação (principal → backup → defaults) e a invariante
central: uma falha no meio da escrita nunca deixa o perfil num estado
intermediário ilegível.
"""

import json

import pytest

from game.core.meta_progression import PlayerProfile

# Uma chave numérica estável do perfil, usada como sonda nos testes.
PROBE = "stars_collected"


@pytest.fixture
def profile_path(tmp_path):
    return tmp_path / "perfil.json"


def _profile(path):
    return PlayerProfile(profile_path=path)


def test_save_cria_arquivo_sem_tmp_residual(profile_path):
    p = _profile(profile_path)
    setattr(p, PROBE, 1234)
    p.save()
    assert profile_path.exists()
    assert not profile_path.with_suffix(".tmp").exists()


def test_round_trip(profile_path):
    p = _profile(profile_path)
    setattr(p, PROBE, 4321)
    p.save()
    q = _profile(profile_path)
    q.load()
    assert getattr(q, PROBE) == 4321


def test_backup_guarda_estado_anterior(profile_path):
    p = _profile(profile_path)
    setattr(p, PROBE, 111)
    p.save()
    setattr(p, PROBE, 222)
    p.save()
    backup = profile_path.with_suffix(".bak.json")
    assert json.loads(backup.read_text(encoding="utf-8"))[PROBE] == 111
    assert json.loads(profile_path.read_text(encoding="utf-8"))[PROBE] == 222


def test_corrompido_restaura_do_backup(profile_path):
    p = _profile(profile_path)
    setattr(p, PROBE, 111)
    p.save()
    setattr(p, PROBE, 222)
    p.save()
    profile_path.write_text("{lixo truncado", encoding="utf-8")
    q = _profile(profile_path)
    q.load()
    assert getattr(q, PROBE) == 111
    # O arquivo problemático é preservado, não descartado.
    assert profile_path.with_suffix(".corrupt.json").exists()


def test_principal_e_backup_ilegiveis_caem_em_defaults(profile_path):
    p = _profile(profile_path)
    setattr(p, PROBE, 999)
    p.save()
    p.save()  # cria o backup
    profile_path.write_text("lixo", encoding="utf-8")
    profile_path.with_suffix(".bak.json").write_text("lixo", encoding="utf-8")
    q = _profile(profile_path)
    q.load()  # não deve levantar
    assert getattr(q, PROBE) == 0  # default


def test_crash_no_meio_da_escrita_preserva_perfil_antigo(profile_path, monkeypatch):
    p = _profile(profile_path)
    setattr(p, PROBE, 777)
    p.save()
    intacto = profile_path.read_text(encoding="utf-8")

    real_dump = json.dump

    def dump_que_explode(*args, **kwargs):
        real_dump(*args, **kwargs)
        raise OSError("disco cheio no meio da escrita")

    monkeypatch.setattr(json, "dump", dump_que_explode)
    with pytest.raises(OSError):
        setattr(p, PROBE, 888)
        p.save()
    monkeypatch.undo()

    # O arquivo real nunca viu o estado intermediário: continua o 777 íntegro.
    assert profile_path.read_text(encoding="utf-8") == intacto
    q = _profile(profile_path)
    q.load()
    assert getattr(q, PROBE) == 777
