# -*- coding: utf-8 -*-
"""Analytical supports and oblique sweep of a straight constant section."""
import math


def dot(a, b):
    return sum(x*y for x,y in zip(a,b))


def section_support(direction, u, v, half_width, half_height, round_section):
    if round_section == 'oval':
        du, dv = dot(direction,u), dot(direction,v)
        radius = min(half_width,half_height)
        return (max(half_width-half_height,0.)*abs(du)+
                max(half_height-half_width,0.)*abs(dv)+
                radius*math.sqrt(du*du+dv*dv))
    a = half_width * dot(direction,u)
    b = half_height * dot(direction,v)
    return math.sqrt(a*a+b*b) if round_section else abs(a)+abs(b)


def passage_interval(origin, axis, length, u, v, hw, hh, circular, normal, low, high):
    an=dot(axis,normal)
    if abs(an)<1e-8:
        raise ValueError('MEP axis is parallel to base layer')
    radius=section_support(normal,u,v,hw,hh,circular)
    cn=dot(origin,normal)
    ends=sorted(((low-cn-radius)/an,(high-cn+radius)/an))
    # For negative an the min/max support must be reversed before sorting.
    if an<0:
        ends=sorted(((low-cn-radius)/an,(high-cn+radius)/an))
    return max(0.,ends[0]),min(length,ends[1])


def swept_range(origin, axis, u, v, hw, hh, circular, normal, low, high, direction):
    """Exact projection of the full section sweep between two parallel planes.

    The MEP is continued across the construction, independently of its end cap.
    """
    an=dot(axis,normal)
    if abs(an)<1e-8:
        raise ValueError('MEP axis is parallel to base layer')
    ratio=dot(axis,direction)/an
    effective=tuple(direction[i]-ratio*normal[i] for i in range(3))
    radius=section_support(effective,u,v,hw,hh,circular)
    center=dot(origin,direction)-ratio*dot(origin,normal)
    ends=[center+ratio*low,center+ratio*high]
    return min(ends)-radius,max(ends)+radius


def axis_trace_length(origin, axis, length, normal, low, high):
    """Length of the finite centreline segment inside the layer's parallel planes.

    Section size and rotation deliberately do not participate in this criterion.
    Inputs axis/normal are unit vectors; lengths use consistent units.
    """
    an = dot(axis, normal)
    if abs(an) < 1e-8:
        raise ValueError('MEP axis is parallel to base layer')
    cn = dot(origin, normal)
    a, b = sorted(((low-cn)/an, (high-cn)/an))
    return max(0., min(length, b) - max(0., a))


def axis_interval(origin, axis, length, normal, low, high):
    """Finite centreline interval, with no section footprint inflation."""
    an = dot(axis, normal)
    if abs(an) < 1e-8:
        raise ValueError('MEP axis is parallel to base layer')
    cn = dot(origin, normal)
    a, b = sorted(((low-cn)/an, (high-cn)/an))
    return max(0.,a), min(length,b)


def layer_normal_interval(origin, axis, layer_normal, low, high, base_normal):
    """Project layer boundary intersections onto the common base normal.

    No MEP end-cap clipping or profile size participates in layer spacing.
    Parallel normals of either sign describe the same layer direction.
    """
    if abs(abs(dot(layer_normal, base_normal))-1.) > 1e-6:
        raise ValueError('Layer normals are not parallel')
    denominator = dot(axis, layer_normal)
    if abs(denominator) < 1e-8:
        raise ValueError('MEP axis is parallel to layer')
    cn = dot(origin, layer_normal)
    base_origin = dot(origin, base_normal)
    scale = dot(axis, base_normal)/denominator
    return tuple(sorted((base_origin+(low-cn)*scale,
                         base_origin+(high-cn)*scale)))
