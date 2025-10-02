class Timer:
    def __init__(self, duration: float = 0.0):
        self.duration = duration
        self.time = 0.0
        self.active = False

    def start(self, duration: float | None = None):
        if duration is not None:
            self.duration = duration
        self.time = self.duration
        self.active = True

    def update(self, dt: float):
        if self.active:
            self.time -= dt
            if self.time <= 0:
                self.active = False

    def done(self) -> bool:
        return not self.active

    def get_progress(self) -> float:
        if self.duration == 0 or not self.active:
            return 0.0
        return max(0.0, min(1.0, (self.duration - self.time) / self.duration))
