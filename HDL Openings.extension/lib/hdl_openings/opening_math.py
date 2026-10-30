# -*- coding: utf-8 -*-
import math


def ceil_step(value, step):
    if value <= 0 or step <= 0:
        raise ValueError('Positive dimension and rounding step required')
    units = value/step
    nearest = round(units)
    if abs(units-nearest) <= 1e-10 and nearest*step >= value-1e-10:
        return nearest*step
    return math.ceil(units)*step


def round_requirement(diameter, cosine, depth, clearance):
    if not 0 < cosine <= 1+1e-12 or diameter <= 0 or depth < 0:
        raise ValueError('Invalid circular passage geometry')
    cosine = min(cosine,1.)
    sine = math.sqrt(max(0.,1-cosine*cosine))
    return diameter/cosine+depth*sine/cosine+2*clearance


def choose_round(diameter, cosine, depth, clearance, cores, maximum_depth):
    """Select one core by OD+2t, then test full oblique footprint. Units consistent."""
    if not 0 < cosine <= 1+1e-12 or diameter <= 0 or depth < 0:
        raise ValueError('Invalid circular passage geometry')
    cosine = min(cosine,1.)
    initial = diameter+2*clearance
    core = next((d for d in cores if d > initial+1e-10), None)
    if core is None:
        return None, 'No strictly larger core diameter'
    if depth > maximum_depth+1e-9:
        return None, 'MaxCoreDepth exceeded'
    required = round_requirement(diameter,cosine,depth,clearance)
    if required > core+1e-9:
        return None, 'Full passage does not fit selected core'
    return core, None
