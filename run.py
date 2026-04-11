import logging
import os
import sys
import traceback

# Ensure the project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

def main():
    """Main entry point for the game."""
    # Configure basic logging to console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    try:
        from game.app import GameApp
        app = GameApp()
        app.run()
    except Exception:
        # Try to save the error to a file
        try:
            from game.core.paths import get_error_log_path
            error_log = get_error_log_path()
            with open(error_log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            print(f"\nErro salvo em: {error_log}")
        except Exception as e:
            print(f"\nNão foi possível salvar o log de erro: {e}")
        
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
