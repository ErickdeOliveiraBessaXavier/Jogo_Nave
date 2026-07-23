def compute_laser_width(
    timer: float,
    expand_time: float,
    hold_time: float,
    lifetime: float,
    max_w: float,
) -> float:
    """Ease-out expand → hold → ease-in shrink width animation."""
    if timer < expand_time:
        progress = timer / expand_time
        w = max_w * (1 - (1 - progress) ** 2)
    elif timer < expand_time + hold_time:
        w = max_w
    else:
        shrink_duration = lifetime - (expand_time + hold_time)
        if shrink_duration > 0:
            progress = (timer - (expand_time + hold_time)) / shrink_duration
            w = max_w * (1 - progress**2)
        else:
            w = 0.0
    return max(0.0, w)
