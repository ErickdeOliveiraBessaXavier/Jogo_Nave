"""InterceptorSquad — coordenação leve da dupla de Police Interceptors.

Materializa o **pincer sincronizado** ("Squad Pairs"): quando o holofote de
*qualquer* membro pega o jogador, o esquadrão **arma** um bote conjunto — todos
os membros vivos que ainda patrulham entram em `lock` no mesmo instante e
disparam o dash juntos, de lados opostos. Se um membro morre, o sobrevivente
fica em **modo solo** (mais agressivo).

Segue o espírito do `ChannelingGroup` do City Drone (§1): é um coordenador leve
que **não conhece a cena** nem o EntityManager — só medeia o gatilho entre os
membros por uma API pública. Os membros lêem/escrevem o esquadrão; o esquadrão
lê apenas atributos públicos dos membros (`dead`), nunca privados de outro
objeto irmão.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .police_interceptor import PoliceInterceptor

# Janela em que o bote fica "armado" — tempo para os dois membros reagirem e
# entrarem em lock no mesmo frame/instante (sincronia do pincer).
ARM_WINDOW: float = 0.16
# Descanso compartilhado após um bote conjunto (entre investidas coordenadas).
STRIKE_COOLDOWN: float = 1.9


class InterceptorSquad:
    def __init__(self, members: List["PoliceInterceptor"]) -> None:
        self.members: List["PoliceInterceptor"] = list(members)
        for m in self.members:
            m.squad = self
        self.armed: bool = False
        self.window: float = 0.0
        self.cooldown: float = STRIKE_COOLDOWN * 0.5  # carência inicial

    @property
    def solo(self) -> bool:
        return len(self.members) <= 1

    def can_arm(self) -> bool:
        return not self.armed and self.cooldown <= 0.0

    def arm(self) -> None:
        """Um membro pegou o jogador no holofote: arma o bote conjunto."""
        if self.can_arm():
            self.armed = True
            self.window = ARM_WINDOW

    def poll(self) -> bool:
        """Um membro pergunta se deve aderir ao bote (enquanto a janela está aberta)."""
        return self.armed

    def tick(self, member: "PoliceInterceptor", dt: float) -> None:
        """Avança os timers compartilhados. Idempotente por frame: só o líder
        (primeiro membro vivo) avança, então os dois podem chamar sem dobrar."""
        alive = [m for m in self.members if not m.dead]
        self.members = alive
        if not alive or member is not alive[0]:
            return

        if self.cooldown > 0.0:
            self.cooldown = max(0.0, self.cooldown - dt)
        if self.armed:
            self.window -= dt
            if self.window <= 0.0:
                # Fecha a janela e entra em descanso conjunto (o bote já disparou).
                self.armed = False
                self.cooldown = STRIKE_COOLDOWN
