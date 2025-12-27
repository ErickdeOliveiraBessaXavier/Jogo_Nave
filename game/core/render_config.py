# game/core/render_config.py


class RenderConfig:
    # Celestial Manager configurations
    CELESTIAL_NUM_BODIES = 2
    CELESTIAL_SCALE_MIN = 0.05
    CELESTIAL_SCALE_MAX = 0.3
    CELESTIAL_ALPHA_MIN = 50
    CELESTIAL_ALPHA_MAX = 200
    CELESTIAL_SPEED_BASE_MIN = 25
    CELESTIAL_SPEED_BASE_MAX = 150
    CELESTIAL_SPEED_OFFSET = 20
    CELESTIAL_RESET_Y_MIN_MULTIPLIER = -1.5
    CELESTIAL_RESET_Y_MAX_MULTIPLIER = -0.5
    CELESTIAL_MIN_GAP = 150  # Minimum horizontal gap between celestial bodies

    # Spawn timing for more organic appearance
    CELESTIAL_SPAWN_MIN_INTERVAL = 8.0  # Minimum seconds between spawns
    CELESTIAL_SPAWN_MAX_INTERVAL = 15.0  # Maximum seconds between spawns

    # Starfield configurations
    STARFIELD_NUM_STARS = 30
    STARFIELD_SPEED_MIN = 20
    STARFIELD_SPEED_MAX = 150
    STARFIELD_BRIGHTNESS_MIN = 100
    STARFIELD_BRIGHTNESS_MAX = 255
