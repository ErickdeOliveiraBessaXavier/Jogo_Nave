from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self):
        self._subs: dict[str, list[Callable[..., None]]] = defaultdict(list)

    def on(self, event: str, fn: Callable[..., None]):
        self._subs[event].append(fn)

    def emit(self, event: str, **kwargs: Any):
        for fn in self._subs[event]:
            fn(**kwargs)
