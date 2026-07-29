"""Ritmo das fusões City Drone → FusedDrone.

O `FusedDrone` não nasce de spawner: ele emerge em runtime quando uma
`ChannelingGroup` de 4 City Drones completa o ritual. Como o gatilho é
emergente (proximidade + sorteio), nada impedia que dois ou três rituais
maturassem quase juntos — a fase saltava de um enxame comum para vários
mini-chefes num intervalo curto demais para o jogador reagir a cada um.

Este governador impõe três regras de ritmo, sem tocar na ameaça individual:

* **Teto de `MAX_ACTIVE` mini-chefes vivos ao mesmo tempo.**
* **Uma fusão por vez.** Com um ritual em andamento, nenhum outro começa —
  é o que faz "duas fusões ao mesmo tempo" virar "a primeira acontece, a
  outra nem começa". Sem isso o teto sozinho não bastaria: dois rituais
  abertos no mesmo instante maturariam juntos e entregariam os dois
  mini-chefes de uma vez, que é exatamente o pico que se quer evitar.
* **`MIN_INTERVAL` segundos entre uma fusão e a seguinte**, mesmo com vaga
  livre.

O intervalo é medido **entre fusões**, não entre rituais: `allows_new_ritual`
recebe o `lead_time` (a duração da canalização) e libera o começo quando o que
resta de relógio cabe dentro dele. Assim a fusão seguinte sai em exatamente
`MIN_INTERVAL` no melhor caso, e o jogador vê a canalização se formando como
telegrafia — em vez de 15s de silêncio seguidos de 4,5s de aviso.

Matar um mini-chefe **não** devolve tempo: o relógio só anda com o tempo de
jogo (`tick`), então derrubar o primeiro rápido não antecipa o segundo.

Estado de partida (§4): a instância viva é do `EntityManager`, entregue às
entidades pelo `EnemyUpdateContext` — sem variável de módulo mutável.
"""

from __future__ import annotations

from typing import Any, Iterable


class FusionGovernor:
    MAX_ACTIVE = 2  # mini-chefes vivos simultâneos
    MIN_INTERVAL = 15.0  # segundos entre uma fusão consumada e a próxima

    def __init__(self) -> None:
        self.cooldown = 0.0

    def reset(self) -> None:
        """Zera o relógio. Arena limpa (fim de fase, restart) é encontro novo."""
        self.cooldown = 0.0

    def tick(self, dt: float) -> None:
        """Anda o relógio com o tempo de jogo dos inimigos (congela em time stop)."""
        if self.cooldown > 0.0:
            self.cooldown = max(0.0, self.cooldown - dt)

    def commit_fusion(self) -> None:
        """Registra uma fusão consumada e reinicia o intervalo mínimo."""
        self.cooldown = self.MIN_INTERVAL

    def allows_new_ritual(self, enemies: Iterable[Any], lead_time: float = 0.0) -> bool:
        """O ritual pode começar agora?

        `lead_time` é quanto ele ainda vai demorar para virar mini-chefe
        (`ChannelingGroup.DURATION`): o que importa é o instante da FUSÃO cair
        depois do intervalo mínimo, não o instante em que a canalização começa.
        """
        if self.cooldown > lead_time:
            return False
        active, pending = self.count_state(enemies)
        if pending:
            return False  # uma fusão por vez
        return active < self.MAX_ACTIVE

    @staticmethod
    def count_state(enemies: Iterable[Any]) -> tuple[int, int]:
        """`(mini-chefes vivos, rituais em andamento)`.

        Derivado da lista viva de inimigos, não de contadores incrementados no
        começo e decrementados no fim: um ritual abandonado sem quebrar (fase que
        termina, arena limpa) vazaria a reserva para sempre.

        Varre a lista inteira, então é chamado só no caminho raro que já passou
        pelo scan de proximidade e pelo sorteio — nunca por frame (§7).
        """
        active = 0
        pending = 0
        for e in enemies:
            if getattr(e, "dead", False):
                continue
            if getattr(e, "is_fused_drone", False):
                active += 1
                continue
            grp = getattr(e, "channel_group", None)
            if grp is None or grp.broken or grp.spawned:
                continue
            # O ritual conta UMA vez, não quatro: responde por ele o líder — o
            # mesmo representante que a `ChannelingGroup` usa p/ somar progresso.
            if grp.members and grp.members[0] is e:
                pending += 1
        return active, pending
