"""Script para analisar balanceamento dos níveis procedurais."""

from typing import List

from game.core.levels import DifficultyPreset, LevelAnalyzer, get_level_config


def analyze_difficulty_preset(preset: DifficultyPreset, levels_to_check: range):
    """Analisa uma dificuldade específica."""
    print(f"\n{'=' * 100}")
    print(f"ANÁLISE: {preset.value.upper()}")
    print(f"{'=' * 100}\n")

    print(
        f"{'Status':^6} │ {'Nível':^5} │ {'Tema':^22} │ {'Inimigos':^8} │ "
        f"{'Spawn/s':^8} │ {'~Tela':^6} │ {'Tempo':^8} │ {'Features':^8}"
    )
    print("─" * 100)

    total_warnings = 0
    problematic_levels: List[int] = []

    for level_num in levels_to_check:
        config = get_level_config(level_num, preset)
        stats = LevelAnalyzer.analyze_level(config)
        duration = LevelAnalyzer.estimate_duration(config)
        spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
        max_enemies = LevelAnalyzer.estimate_max_enemies_on_screen(config)
        warnings = config.validate_sanity()

        # Emoji visual para features
        features = ""
        if stats["has_boss"]:
            features += "👹"
        if stats["mines"]:
            features += "💣"
        if stats["formations"]:
            features += "🌀"

        theme_name = config.theme_name or "N/A"

        # Indicador de problemas
        status = "⚠️" if warnings else "✓"
        if warnings:
            total_warnings += 1
            problematic_levels.append(level_num)

        print(
            f"{status:^6} │ {level_num:^5} │ {theme_name:^22} │ "
            f"👾{stats['enemies_to_clear']:>3} │ "
            f"📈{spawn_rate:>5.1f}/s │ "
            f"🎯~{max_enemies:>2} │ "
            f"🕐{duration/60:>5.1f}m │ "
            f"{features:^8}"
        )

        # Mostrar avisos se houver
        if warnings:
            for warning in warnings:
                print(f"       └─ ⚠️  {warning}")

    print("─" * 100)
    print(f"\nResumo: {total_warnings} níveis com avisos")
    if problematic_levels:
        print(f"Níveis problemáticos: {problematic_levels}")
    print()


def main():
    """Função principal."""
    print("\n" + "=" * 100)
    print(" " * 30 + "ANÁLISE DE BALANCEAMENTO DE NÍVEIS")
    print("=" * 100)

    # Analisar primeiros 20 níveis em diferentes dificuldades
    print("\n📊 Analisando progressão inicial (níveis 1-20)...")

    for preset in [
        DifficultyPreset.CASUAL,
        DifficultyPreset.NORMAL,
        DifficultyPreset.HARDCORE,
    ]:
        analyze_difficulty_preset(preset, range(1, 21))

    # Análise de níveis avançados
    print("\n📊 Analisando níveis avançados (30, 40, 50, 75, 100)...")
    for preset in [DifficultyPreset.NORMAL, DifficultyPreset.HARDCORE]:
        print(f"\n{'=' * 100}")
        print(f"NÍVEIS AVANÇADOS: {preset.value.upper()}")
        print(f"{'=' * 100}\n")

        for level in [30, 40, 50, 75, 100]:
            config = get_level_config(level, preset)
            spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
            max_enemies = LevelAnalyzer.estimate_max_enemies_on_screen(config)
            duration = LevelAnalyzer.estimate_duration(config)
            warnings = config.validate_sanity()

            status = "⚠️" if warnings else "✓"
            print(
                f"{status} Nível {level:3d}: {config.theme_name:20s} │ "
                f"👾 {config.enemies_to_clear:3d} │ "
                f"📈 {spawn_rate:.1f}/s │ "
                f"🎯 ~{max_enemies:2d} tela │ "
                f"🕐 {duration/60:.1f}min"
            )

            if warnings:
                for warning in warnings:
                    print(f"           └─ {warning}")

    print("\n" + "=" * 100)
    print("✅ Análise concluída!")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    main()
