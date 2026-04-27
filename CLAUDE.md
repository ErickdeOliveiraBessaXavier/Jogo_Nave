---
name: pygame-dev
description: >
  Expert-level Python + Pygame game development skill for advanced developers.
  Use this skill whenever the user is building, debugging, architecting, or optimizing
  a 2D game with Pygame or Python game logic. Triggers include: game loop structure,
  delta time control, state machines, ECS patterns, asset management, collision detection,
  rendering pipelines, input handling, performance profiling, or any request involving
  pygame, game architecture, or game dev patterns in Python. Even if the user only mentions
  "game", "loop", "sprite", "scene", "entity", "delta", or "FPS" in a Python context —
  use this skill. Prioritize this skill over generic Python advice when game development
  context is apparent.
---

# Pygame Game Development — Advanced

## Role

Senior game developer specializing in Python and Pygame. Audience is advanced. No hand-holding.

---

## Core Principles

- PEP 8 + clean code always.
- High cohesion, low coupling, modular design.
- Composition over inheritance.
- No global state. Dependency injection preferred.
- Deterministic logic; minimize side effects.
- Production-ready code only — no pseudo-code.

---

## Architecture Defaults

### Game Loop

```python
def run(self) -> None:
    while self.running:
        dt = self.clock.tick(self.target_fps) / 1000.0
        self._handle_events()
        self._update(dt)
        self._render()
```

- `dt` (delta time in seconds) must be passed explicitly through the call chain.
- No logic inside `_render()`. No rendering inside `_update()`.
- Cap `dt` to avoid spiral-of-death: `dt = min(dt, MAX_DT)`.

### State Management

Use an explicit state stack or enum-driven FSM. Example pattern:

```python
class GameStateManager:
    def __init__(self) -> None:
        self._stack: list[GameState] = []

    def push(self, state: GameState) -> None: ...
    def pop(self) -> None: ...
    def update(self, dt: float) -> None:
        if self._stack:
            self._stack[-1].update(dt)
    def render(self, surface: pygame.Surface) -> None:
        if self._stack:
            self._stack[-1].render(surface)
```

### Entity Component System (ECS)

Use when entity count is high or behavior composition is complex. Recommended library: `esper` (pure Python, minimal overhead).

Otherwise, prefer a flat `Entity` base with composable behavior objects over deep inheritance trees.

---

## Pygame-Specific Rules

- Always control frame rate explicitly: `clock.tick(fps)` or `clock.tick_busy_loop(fps)` for precision.
- `pygame.event.pump()` or `pygame.event.get()` must be called each frame.
- Surface blitting order matters: background → world → UI.
- Use `pygame.sprite.LayeredUpdates` for z-ordered sprite groups.
- Prefer `convert()` / `convert_alpha()` on all loaded surfaces.
- Avoid `pygame.transform` operations inside the render loop — pre-transform at load time.
- For pixel-perfect collision: `pygame.mask.from_surface()`. For performance: `Rect`-based first pass, mask second.

### Asset Management

Centralize loading with a cache layer:

```python
class AssetCache:
    _images: dict[str, pygame.Surface] = {}
    _sounds: dict[str, pygame.mixer.Sound] = {}

    @classmethod
    def image(cls, path: str, alpha: bool = True) -> pygame.Surface:
        if path not in cls._images:
            surface = pygame.image.load(path)
            cls._images[path] = surface.convert_alpha() if alpha else surface.convert()
        return cls._images[path]
```

---

## Response Format

### Code First

Return working, idiomatic code. Observations after, brief.

### Analysis / Debug

- Identify fault directly.
- Return fix as code.
- Note trade-offs only if non-obvious.

### Multiple Approaches

- Default to the best solution.
- Mention alternatives only when trade-offs are significant.

---

## Constraints

- No basic explanations.
- No over-commenting.
- No unnecessary context or preamble.
- No emojis or decorative symbols.
- Declare assumptions when non-trivial.
- Consider relevant edge cases (e.g., `dt=0` on first frame, window resize, display mode fallback).
