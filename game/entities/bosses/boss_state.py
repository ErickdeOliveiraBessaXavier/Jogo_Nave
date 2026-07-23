from enum import Enum, auto


class BossState(Enum):
    ENTERING = auto()
    ACTIVE = auto()
    AIMING = auto()
    CHARGING = auto()
    CONVERGING = auto()
    PREPARING_TO_FIRE = auto()
    FIRING = auto()
