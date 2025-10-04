import traceback

if __name__ == "__main__":
    try:
        from game.app import GameApp

        GameApp().run()
    except Exception as e:
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
        traceback.print_exc()
