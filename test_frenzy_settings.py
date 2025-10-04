#!/usr/bin/env python3
"""
Script para testar e demonstrar as configurações de timing do modo frenzy.
"""

from game.core.config import Config


def show_frenzy_comparison():
    """Mostra comparação entre modo normal e frenzy."""
    print("🎯 CONFIGURAÇÕES DE TIMING DO BOSS")
    print("=" * 50)

    print("\n📊 MODO NORMAL vs FRENZY:")
    print("-" * 30)

    # Duração do carregamento
    normal_charge = Config.BOSS_CHARGE_DURATION
    frenzy_charge = Config.BOSS_FRENZY_CHARGE_DURATION
    charge_speedup = normal_charge / frenzy_charge

    print(f"⚡ Carregamento do Laser:")
    print(f"   Normal: {normal_charge:.2f}s")
    print(f"   Frenzy: {frenzy_charge:.2f}s ({charge_speedup:.1f}x mais rápido)")

    # Delay antes do disparo
    normal_delay = Config.BOSS_LASER_DELAY
    frenzy_delay = Config.BOSS_FRENZY_LASER_DELAY
    delay_speedup = normal_delay / frenzy_delay

    print(f"\n⏱️  Delay antes do Disparo:")
    print(f"   Normal: {normal_delay:.2f}s")
    print(f"   Frenzy: {frenzy_delay:.2f}s ({delay_speedup:.1f}x mais rápido)")

    # Tempo total de warning
    normal_total = normal_charge + normal_delay
    frenzy_total = frenzy_charge + frenzy_delay
    total_speedup = normal_total / frenzy_total

    print(f"\n🚨 Tempo Total de Aviso:")
    print(f"   Normal: {normal_total:.2f}s")
    print(f"   Frenzy: {frenzy_total:.2f}s ({total_speedup:.1f}x mais rápido)")

    # Efeitos visuais
    normal_blink = Config.BOSS_AIM_BLINK_INTERVAL
    frenzy_blink = Config.BOSS_FRENZY_AIM_BLINK_INTERVAL
    blink_speedup = normal_blink / frenzy_blink

    print(f"\n👁️  Piscar da Mira:")
    print(f"   Normal: {normal_blink}ms")
    print(f"   Frenzy: {frenzy_blink}ms ({blink_speedup:.1f}x mais rápido)")

    print("\n" + "=" * 50)
    print("✨ Para ajustar os timings, edite os valores em game/core/config.py")
    print("🎮 Valores menores = mais rápido e mais difícil")
    print("🎮 Valores maiores = mais lento e mais fácil")


if __name__ == "__main__":
    show_frenzy_comparison()
