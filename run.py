import traceback
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

if __name__ == "__main__":
    try:
        from game.app import GameApp

        GameApp().run()
    except Exception:
        from game.core.paths import get_error_log_path

        error_log = get_error_log_path()
        with open(error_log, "w") as f:
            f.write(traceback.format_exc())
        traceback.print_exc()
        print(f"\nErro salvo em: {error_log}")
