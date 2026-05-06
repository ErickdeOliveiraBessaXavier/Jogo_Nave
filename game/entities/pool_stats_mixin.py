class PoolStatsMixin:
    active: list
    pool: list
    peak_active: int
    max_size: int
    total_created: int
    reused_count: int

    def get_active_count(self) -> int:
        return len(self.active)

    def get_pool_size(self) -> int:
        return len(self.pool)

    def _update_peak(self) -> None:
        self.peak_active = max(self.peak_active, len(self.active))

    def get_stats(self) -> dict[str, int | float]:
        total = max(1, self.total_created)
        return {
            "active": len(self.active),
            "inactive": len(self.pool) - len(self.active),
            "pool_total": len(self.pool),
            "peak_active": self.peak_active,
            "max_size": self.max_size,
            "total_created": self.total_created,
            "reused": self.reused_count,
            "efficiency_percent": (self.reused_count / total) * 100,
        }
