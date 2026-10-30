# -*- coding: utf-8 -*-
"""Oriented Scope Box clipping by analytical volume support, not its world AABB."""
import math

EPS = 1e-7


class ScopeBoxError(ValueError):
    pass


def xyz(value):
    return (value.X,value.Y,value.Z)


def dot(a,b):
    return sum(a[i]*b[i] for i in range(3))


def add(a,b):
    return tuple(a[i]+b[i] for i in range(3))


def scale(a,value):
    return tuple(v*value for v in a)


class Region(object):
    def __init__(self,name,uid,segments):
        self.name,self.uid = name,uid
        axes,points = [],[]
        for a,b in segments:
            direction = tuple(b[i]-a[i] for i in range(3))
            length = math.sqrt(dot(direction,direction))
            if length <= EPS:
                continue
            direction = scale(direction,1./length)
            if not any(abs(abs(dot(direction,axis))-1.) <= 1e-6 for axis in axes):
                if any(abs(dot(direction,axis)) > 1e-6 for axis in axes):
                    raise ScopeBoxError('Scope Box edges are not orthogonal')
                axes.append(direction)
            points.extend((a,b))
        if len(axes)!=3 or not points:
            raise ScopeBoxError('Cannot read three Scope Box axes from its geometry')
        self.axes = tuple(axes)
        self.ranges = tuple((min(dot(p,axis) for p in points),max(dot(p,axis) for p in points))
                            for axis in axes)
        if any(high-low <= EPS for low,high in self.ranges):
            raise ScopeBoxError('Scope Box must have positive width, length and height')

    def overlaps_bounds(self,bounds):
        """Conservative broad phase; long MEP may start/end outside the box."""
        if bounds is None:
            return True
        center = tuple(sum(r)/2. for r in bounds)
        half = tuple((r[1]-r[0])/2. for r in bounds)
        for axis,(low,high) in zip(self.axes,self.ranges):
            c = dot(center,axis)
            h = sum(abs(axis[i])*half[i] for i in range(3))
            if c+h < low-EPS or c-h > high+EPS:
                return False
        return True

    def contains_volume(self,center,x,y,normal,width,height,depth,shape):
        if min(width,height,depth) <= 0:
            raise ScopeBoxError('Invalid opening volume')
        for axis,(low,high) in zip(self.axes,self.ranges):
            c = dot(center,axis)
            if shape == 'round':
                h = width/2.*math.sqrt(dot(x,axis)**2+dot(y,axis)**2)
            elif shape == 'rect':
                h = abs(dot(x,axis))*width/2.+abs(dot(y,axis))*height/2.
            else:
                raise ScopeBoxError('Unknown opening shape')
            h += abs(dot(normal,axis))*depth/2.
            if c-h < low-EPS or c+h > high+EPS:
                return False
        return True

    def contains_plan(self,plan):
        width,height = ((plan['diameter'],plan['diameter']) if plan['shape']=='round'
                        else (plan['width'],plan['height']))
        return self.contains_volume(xyz(plan['center']),xyz(plan['x']),xyz(plan['y']),
                                    xyz(plan['normal']),width,height,plan['depth'],plan['shape'])

    def contains_state(self,state,wall):
        if not isinstance(state,dict):
            raise ScopeBoxError('Actual opening geometry unavailable')
        width,height = ((state['diameter'],state['diameter']) if state['shape']=='round'
                        else (state['width'],state['height']))
        center = add(state['insertion'],scale(state['normal'],state['depth']/2. if wall else -state['depth']/2.))
        if wall and state['shape']=='rect':
            center = add(center,scale(state['y'],height/2.))
        return self.contains_volume(center,state['x'],state['y'],state['normal'],
                                    width,height,state['depth'],state['shape'])


def from_element(element,db):
    options = db.Options()
    options.IncludeNonVisibleObjects = True
    segments = []
    def visit(geometry):
        for item in geometry:
            if isinstance(item,db.Line):
                segments.append((xyz(item.GetEndPoint(0)),xyz(item.GetEndPoint(1))))
            elif isinstance(item,db.GeometryInstance):
                visit(item.GetInstanceGeometry())
    geometry = element.get_Geometry(options)
    if geometry is not None:
        visit(geometry)
    # Do not replace rotated geometry with an axis-aligned bounding box.
    return Region(element.Name,element.UniqueId,segments)
