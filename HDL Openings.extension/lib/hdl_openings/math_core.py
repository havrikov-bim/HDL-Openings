# -*- coding: utf-8 -*-
"""Pure functions. Lengths supplied by caller, no Revit dependency."""
import math


def merge_intervals(records, gap):
    """Records: (start, end, payload). Preserve transitive groups and payloads."""
    if gap < 0:
        raise ValueError('gap must be nonnegative')
    result = []
    for start, end, payload in sorted(records, key=lambda r: (r[0], r[1])):
        if end < start:
            raise ValueError('reversed interval')
        if result and start <= result[-1][1] + gap:
            result[-1][1] = max(result[-1][1], end)
            result[-1][2].append(payload)
        else:
            result.append([start, end, [payload]])
    return result


def trig_range(center, cosine, sine, start, end):
    """Exact extrema of center + cosine*cos(t) + sine*sin(t) on [start,end]."""
    if end < start:
        raise ValueError('reversed parameter interval')
    values = [center + cosine * math.cos(start) + sine * math.sin(start),
              center + cosine * math.cos(end) + sine * math.sin(end)]
    phase = math.atan2(sine, cosine)
    k0 = int(math.ceil((start - phase) / math.pi))
    k1 = int(math.floor((end - phase) / math.pi))
    for k in range(k0, k1 + 1):
        t = phase + k * math.pi
        values.append(center + cosine * math.cos(t) + sine * math.sin(t))
    return min(values), max(values)


def rect_size(x_range, y_range, clearance):
    if clearance < 0:
        raise ValueError('negative clearance')
    return (x_range[1] - x_range[0] + 2 * clearance,
            y_range[1] - y_range[0] + 2 * clearance)


def insertion_coordinates(x_range, y_range, depth_range, wall):
    """Return insertion in (width, section-height, positive-normal) frame.

    Wall: centered width, bottom height, start of +Y depth.
    Floor: centered section, top of depth, geometry extends along -Z.
    """
    for lo, hi in (x_range, y_range, depth_range):
        if hi <= lo:
            raise ValueError('Opening ranges must have positive extent')
    return ((x_range[0] + x_range[1]) / 2.,
            y_range[0] if wall else (y_range[0] + y_range[1]) / 2.,
            depth_range[0] if wall else depth_range[1])


def interval_gap(a, b):
    """Nonnegative distance between two closed ranges in the same coordinates."""
    return max(0., a[0]-b[1], b[0]-a[1])


def may_extend_group(group_interval, candidate_interval, gap, belongs_to_other_group):
    # Previously separated groups must never be rejoined by depth expansion.
    return (not belongs_to_other_group and
            interval_gap(group_interval, candidate_interval) <= gap)
