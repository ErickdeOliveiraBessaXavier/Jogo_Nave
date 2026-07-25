"""Distinção mudança-de-nível × mudança-de-tema (continuidade vs limpeza).

A limpeza total da fase (projéteis, coletáveis, referências de IA) e o
"encerramento" (magnetizar/fade/esperar) só devem ocorrer em MUDANÇA DE TEMA
(fronteira de mundo). Dentro do mesmo mundo (1-1→1-2) a sequência é contínua e
os elementos persistentes seguem funcionando.

`PlayingScene._next_transition_is_theme_change()` decide isso com a MESMA lógica
que `LevelProgressionController.start_next_level` usa para o `theme_changed`
(`get_world_for_level(n+1).theme != get_world_for_level(n).theme`). Este teste
trava os boundaries: se alguém mudar o layout dos mundos sem perceber que afeta a
regra continuidade-vs-limpeza, quebra aqui.
"""

from game.core.world_config import get_world_for_level


def _is_theme_change(current_level: int) -> bool:
    """Espelha exatamente o cálculo do jogo (peek da próxima transição)."""
    return (
        get_world_for_level(current_level + 1).theme
        != get_world_for_level(current_level).theme
    )


# Fronteiras de mundo conhecidas (onde a limpeza DEVE disparar).
_THEME_BOUNDARIES = [10, 25, 40, 50, 60]

# Transições dentro do mesmo mundo (devem ser contínuas — SEM limpeza).
_WITHIN_WORLD = [1, 5, 9, 12, 20, 24, 30, 39, 45, 49, 55, 59]


class TestThemeTransitionBoundaries:
    def test_fronteiras_de_mundo_mudam_tema(self):
        for cur in _THEME_BOUNDARIES:
            assert _is_theme_change(cur), (
                f"L{cur}->L{cur + 1} deveria ser mudança de tema (limpeza total)"
            )

    def test_dentro_do_mundo_e_continuo(self):
        for cur in _WITHIN_WORLD:
            assert not _is_theme_change(cur), (
                f"L{cur}->L{cur + 1} é dentro do mesmo mundo — deve ser contínuo, "
                "sem limpeza nem encerramento"
            )

    def test_boundaries_e_within_nao_se_sobrepoem(self):
        # Sanidade: nenhum nível marcado como 'dentro do mundo' é fronteira.
        assert not (set(_THEME_BOUNDARIES) & set(_WITHIN_WORLD))
