# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""Language-independent mapping and reduction. No Revit or Excel dependency."""
import unicodedata
try:
    text_type = unicode
except NameError:
    text_type = str


def clean(value):
    return unicodedata.normalize('NFC', text_type(value or '').strip())


class Mapping(object):
    def __init__(self, systems, categories):
        self.systems = {}
        self.categories = {}
        self.order = []
        for rows, target in ((systems, self.systems), (categories, self.categories)):
            for row in rows:
                key, label, discipline = [clean(v) for v in row]
                if not any((key, label, discipline)):
                    continue
                if not all((key, label, discipline)):
                    raise ValueError('Incomplete mapping row: ' + key)
                if key in target:
                    raise ValueError('Duplicate mapping key: ' + key)
                target[key] = (label, discipline)
                if discipline not in self.order:
                    self.order.append(discipline)
        if set(self.categories) != set(('Conduits', 'Cable Trays')):
            raise ValueError('Categories must contain exactly Conduits and Cable Trays')

    def resolve(self, system_type=None, category=None):
        key = clean(category if category else system_type)
        table = self.categories if category else self.systems
        if key not in table:
            raise ValueError('No Excel mapping: ' + (key or '<unassigned system>'))
        return table[key]

    def reduce(self, labels):
        labels = set(labels)
        if not labels:
            return ''
        disciplines = set(d for _, d in labels)
        if len(disciplines) > 1:
            return u', '.join(d for d in self.order if d in disciplines)
        if len(labels) == 1:
            return next(iter(labels))[0]
        return next(iter(disciplines))


def qualifies(entry, depth, full_segment, threshold, tolerance):
    # Full passage and a wholly contained segment are independent exceptions.
    return (full_segment or entry >= depth-tolerance or
            entry > threshold + 1e-9)
