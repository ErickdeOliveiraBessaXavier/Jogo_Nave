from game.core.levels import ProceduralLevelGenerator, DifficultyConfig

def test_reproducibility():
    """Testa se os níveis são determinísticos."""
    gen1 = ProceduralLevelGenerator(seed=42)
    gen2 = ProceduralLevelGenerator(seed=42)
    
    for level in range(1, 20):
        config1 = gen1.generate_level(level)
        config2 = gen2.generate_level(level)
        
        assert config1.enemies_to_clear == config2.enemies_to_clear
        assert config1.theme_name == config2.theme_name
        assert config1.enemy_spawn_config == config2.enemy_spawn_config
    
    print("✓ Reprodutibilidade OK!")

def test_spawn_times():
    """Verifica se spawn times nunca ficam muito baixos."""
    gen = ProceduralLevelGenerator()
    
    for level in range(1, 100):
        config = gen.generate_level(level)
        
        for enemy_type, spawn_time in config.enemy_spawn_config.items():
            assert spawn_time >= DifficultyConfig.MIN_SPAWN_TIME, \
                f"Level {level}: {enemy_type.__name__} spawn time = {spawn_time}"
    
    print("✓ Spawn times dentro dos limites!")

def test_theme_distribution():
    """Analisa distribuição de temas."""
    gen = ProceduralLevelGenerator(seed=12345)
    themes: dict[str, int] = {}
    
    for level in range(1, 51):
        config = gen.generate_level(level)
        theme_name = config.theme_name or "N/A"
        themes[theme_name] = themes.get(theme_name, 0) + 1
    
    print("\nDistribuição de Temas (níveis 1-50):")
    for theme, count in sorted(themes.items(), key=lambda x: -x[1]):
        print(f"  {theme:25s}: {count:2d} ({count*100/50:.0f}%)")