from typing import Any, TypeVar, Generic, Protocol, cast


class HasRect(Protocol):
    """Protocol for objects that have a pygame Rect."""

    rect: Any  # pygame.Rect


class HasPosition(Protocol):
    """Protocol for objects that have x, y, w, h attributes."""

    x: float
    y: float
    w: float
    h: float


T_co = TypeVar("T_co", covariant=True)


class SpatialGrid(Generic[T_co]):
    """
    A simple spatial hash grid for efficient collision detection.
    Divides space into cells and stores objects in them based on their position.
    """

    def __init__(self, cell_size: int = 200):
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = cell_size
        self.grid: dict[tuple[int, int], list[T_co]] = {}

    def _get_cell_coords(self, x: float, y: float) -> tuple[int, int]:
        """Get the cell coordinates for a given position."""
        return (int(x // self.cell_size), int(y // self.cell_size))

    def _get_cells_for_rect(
        self, x: float, y: float, w: float, h: float
    ) -> set[tuple[int, int]]:
        """Get all cell coordinates that a rectangle occupies."""
        left = int(x // self.cell_size)
        right = int((x + w) // self.cell_size)
        top = int(y // self.cell_size)
        bottom = int((y + h) // self.cell_size)

        return {
            (cx, cy) for cx in range(left, right + 1) for cy in range(top, bottom + 1)
        }

    def insert(self, obj: Any, x: float, y: float, w: float = 0, h: float = 0):
        """Insert an object into the grid based on its bounding box."""
        cells = self._get_cells_for_rect(x, y, w, h)
        for cell in cells:
            if cell not in self.grid:
                self.grid[cell] = []
            self.grid[cell].append(obj)  # type: ignore[arg-type]

    def insert_from_rect(self, obj: Any):
        """Insert object that has a pygame rect attribute."""
        if hasattr(obj, "rect"):
            r = cast(HasRect, obj).rect
            self.insert(obj, r.x, r.y, r.width, r.height)
        elif (
            hasattr(obj, "x")
            and hasattr(obj, "y")
            and hasattr(obj, "w")
            and hasattr(obj, "h")
        ):
            pos_obj = cast(HasPosition, obj)
            self.insert(obj, pos_obj.x, pos_obj.y, pos_obj.w, pos_obj.h)
        else:
            raise ValueError("Object must have rect or x/y/w/h attributes")

    def insert_batch(self, objects: list[tuple[Any, float, float, float, float]]):
        """Insert multiple objects at once. More efficient than individual inserts."""
        for obj, x, y, w, h in objects:
            cells = self._get_cells_for_rect(x, y, w, h)
            for cell in cells:
                if cell not in self.grid:
                    self.grid[cell] = []
                self.grid[cell].append(obj)  # type: ignore[arg-type]

    def query(self, x: float, y: float, w: float, h: float) -> list[T_co]:
        """Query objects in the cells that overlap with the given rectangle."""
        cells = self._get_cells_for_rect(x, y, w, h)
        result: list[T_co] = []
        seen: set[int] = set()  # Store IDs instead of objects for faster hashing
        grid = self.grid  # Cache grid reference to avoid repeated attribute lookups
        for cell in cells:
            if cell in grid:
                for obj in grid[cell]:
                    obj_id = id(obj)  # Much faster than hashing arbitrary objects
                    if obj_id not in seen:
                        seen.add(obj_id)
                        result.append(obj)
        return result

    def query_from_rect(self, rect: Any) -> list[T_co]:
        """Query using a pygame Rect object."""
        return self.query(rect.x, rect.y, rect.width, rect.height)

    def clear(self):
        """Clear all objects from the grid."""
        self.grid.clear()

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the grid for debugging/optimization."""
        if not self.grid:
            return {
                "num_cells": 0,
                "total_objects": 0,
                "avg_objects_per_cell": 0,
                "max_objects_in_cell": 0,
            }

        num_cells = len(self.grid)
        total_objects = sum(len(objs) for objs in self.grid.values())
        avg_per_cell = total_objects / num_cells if num_cells > 0 else 0
        max_in_cell = max(len(objs) for objs in self.grid.values()) if self.grid else 0

        return {
            "num_cells": num_cells,
            "total_objects": total_objects,
            "avg_objects_per_cell": avg_per_cell,
            "max_objects_in_cell": max_in_cell,
        }