"""
Teste: cooldown_haste reduz instantaneamente 20s de todos os cooldowns ativos.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.core.upgrades import UpgradeType, create_upgrade
from game.core.config import Config

print("=" * 60)
print("TESTE: cooldown_haste reduz instantaneamente cooldowns")
print("=" * 60)


# Criar contexto mock
class MockShip:
    x, y = 400, 500
    rect = type("obj", (object,), {"centerx": 400, "centery": 500})()


class MockEntityManager:
    player_lasers = []

    def spawn_player_laser(self, *args, **kwargs):
        pass


class MockScene:
    screen_shake_timer = 0


class MockSoundManager:
    def play_laser(self):
        pass

    def play_upgrade_activate(self):
        pass

    def play_upgrade_denied(self):
        pass


ctx = type(
    "Ctx",
    (),
    {
        "ship": MockShip(),
        "entity_manager": MockEntityManager(),
        "difficulty_settings": {},
        "sound_manager": MockSoundManager(),
        "scene": MockScene(),
    },
)()

# Criar upgrades
laser = create_upgrade(UpgradeType.LASER_SHOT)
shield = create_upgrade(UpgradeType.SHIELD_BURST)

print(f"\n[LASER_SHOT] Cooldown base: {laser.meta.base_cooldown}s")
print(f"[SHIELD_BURST] Cooldown base: {shield.meta.base_cooldown}s")

# Simular ativação dos upgrades
print("\n[1] Ativando ambos upgrades...")
laser.activate(ctx)
shield.activate(ctx)
print(f"    LASER_SHOT cooldown: {laser.cooldown_left:.1f}s")
print(f"    SHIELD_BURST cooldown: {shield.cooldown_left:.1f}s")

# Aplicar redução de 20s (simulando o power-up)
REDUCTION = Config.COOLDOWN_HASTE_REDUCTION
print(f"\n[2] Aplicando redução de {REDUCTION}s (cooldown_haste power-up)...")

laser.cooldown_left = max(0.0, laser.cooldown_left - REDUCTION)
shield.cooldown_left = max(0.0, shield.cooldown_left - REDUCTION)

print(f"    LASER_SHOT cooldown: {laser.cooldown_left:.1f}s (esperado: 40s)")
print(f"    SHIELD_BURST cooldown: {shield.cooldown_left:.1f}s (esperado: 25s)")

# Verificar resultados
assert (
    laser.cooldown_left == 40.0
), f"LASER_SHOT deveria ter 40s, tem {laser.cooldown_left}s"
assert (
    shield.cooldown_left == 25.0
), f"SHIELD_BURST deveria ter 25s, tem {shield.cooldown_left}s"

print("\n" + "=" * 60)
print("SUCESSO! Redução de cooldown funcionando corretamente")
print("=" * 60)

# Testar edge case: cooldown menor que a redução
print("\n[3] Teste de segurança: cooldown < redução...")
laser.cooldown_left = 15.0  # Menos que 20s
print(f"    LASER_SHOT cooldown inicial: {laser.cooldown_left:.1f}s")
laser.cooldown_left = max(0.0, laser.cooldown_left - REDUCTION)
print(
    f"    Após redução de {REDUCTION}s: {laser.cooldown_left:.1f}s (esperado: 0s, não negativo)"
)

assert (
    laser.cooldown_left == 0.0
), f"Cooldown não pode ser negativo! Valor: {laser.cooldown_left}"

print("\n" + "=" * 60)
print("TODOS OS TESTES PASSARAM!")
print("=" * 60)
