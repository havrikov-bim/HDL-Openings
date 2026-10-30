# -*- coding: utf-8 -*-
"""Validated immutable per-run settings, retained across persistent-engine calls."""
import collections
import hashlib
import json
import math
import os
import threading
try:
    import builtins
except ImportError:
    import __builtin__ as builtins
try:
    STRING_TYPES = (basestring,)
    INTEGER_TYPES = (int, long)
except NameError:
    STRING_TYPES = (str,)
    INTEGER_TYPES = (int,)

MM = 1./304.8
MAX_BYTES = 65536
Families = collections.namedtuple('Families', 'rect_wall rect_floor round_wall round_floor')
Snapshot = collections.namedtuple('Snapshot',
    'clearance gap touch k_slope max_core_depth rect_step cores families fingerprint path sync_length sync_direction through_all')
STATE_KEY = '_hdl_openings_settings_cache_v3'
if not hasattr(builtins, STATE_KEY):
    setattr(builtins, STATE_KEY, dict(lock=threading.RLock(), entries={}))
_STATE = getattr(builtins, STATE_KEY)


class SettingsError(Exception):
    pass


def default_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'settings.json'))


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise SettingsError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise SettingsError('Nonfinite JSON value: ' + value)


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, INTEGER_TYPES + (float,)):
        raise SettingsError(name + ': expected a number')
    try:
        v = float(value)
    except (OverflowError, ValueError):
        raise SettingsError(name + ': invalid number')
    if math.isnan(v) or math.isinf(v) or not low <= v <= high:
        raise SettingsError('{}: expected finite value in [{}, {}]'.format(name, low, high))
    return v


def validate(data, fingerprint='', path=''):
    if not isinstance(data, dict):
        raise SettingsError('Settings root must be an object')
    keys = set(('schema_version', 'clearance_mm', 'gap_mm', 'touch_mm', 'k_slope',
                'max_core_depth_mm', 'rect_size_step_mm', 'core_diameters_inch', 'families'))
    optional = set(('sync_length_tolerance_mm','sync_angle_tolerance_deg','ThroughAll'))
    if not keys <= set(data) or set(data) - keys - optional:
        raise SettingsError('Missing/unknown settings keys: ' + ', '.join(sorted(set(data)^keys)))
    if isinstance(data['schema_version'], bool) or not isinstance(data['schema_version'], INTEGER_TYPES) or data['schema_version'] != 1:
        raise SettingsError('Unsupported schema_version; expected integer 1')
    clearance = _number(data['clearance_mm'], 'clearance_mm', 0, 1000)*MM
    gap = _number(data['gap_mm'], 'gap_mm', 0, 10000)*MM
    touch = _number(data['touch_mm'], 'touch_mm', 0, 1000)*MM
    slope = _number(data['k_slope'], 'k_slope', 1, 100)
    depth = _number(data['max_core_depth_mm'], 'max_core_depth_mm', .1, 10000)*MM
    step = _number(data['rect_size_step_mm'], 'rect_size_step_mm', .1, 1000)*MM
    values = data['core_diameters_inch']
    if not isinstance(values, list) or not 1 <= len(values) <= 256:
        raise SettingsError('core_diameters_inch: expected 1..256 diameters')
    inches = [_number(v, 'core_diameters_inch', .01, 120) for v in values]
    if len(set(inches)) != len(inches):
        raise SettingsError('core_diameters_inch: duplicate diameters')
    fam = data['families']
    if not isinstance(fam, dict) or set(fam) != set(Families._fields):
        raise SettingsError('families: expected exactly four family keys')
    names = []
    for name in Families._fields:
        value = fam[name]
        if not isinstance(value, STRING_TYPES) or not value.strip() or len(value) > 200 or any(ord(c)<32 for c in value):
            raise SettingsError('families.' + name + ': invalid family name')
        names.append(value.strip())
    if len(set(names)) != 4:
        raise SettingsError('families: names must be distinct')
    through_all = data.get('ThroughAll',1)
    if isinstance(through_all,bool) or not isinstance(through_all,INTEGER_TYPES) or through_all not in (0,1):
        raise SettingsError('ThroughAll: expected integer 0 or 1')
    sync_length = _number(data.get('sync_length_tolerance_mm', .1), 'sync_length_tolerance_mm', .0001, 10)*MM
    angle = _number(data.get('sync_angle_tolerance_deg', .01), 'sync_angle_tolerance_deg', .000001, 1)
    sync_direction = 2*math.sin(math.radians(angle)/2.)
    return Snapshot(clearance, gap, touch, slope, depth, step,
                    tuple(v/12. for v in sorted(inches)), Families(*names), fingerprint, path, sync_length, sync_direction, bool(through_all))


def _stamp(path):
    st = os.stat(path)
    return (getattr(st,'st_mtime_ns',st.st_mtime), st.st_size,
            getattr(st,'st_ctime_ns',st.st_ctime), getattr(st,'st_ino',0))


def _check_depth(text):
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == chr(92):
                escaped = True
            elif char == chr(34):
                in_string = False
        elif char == chr(34):
            in_string = True
        elif char in '[{':
            depth += 1
            if depth > 16:
                raise SettingsError('JSON nesting exceeds 16 levels')
        elif char in ']}':
            depth -= 1


def _read_stable(path, before):
    if not 0 < before[1] <= MAX_BYTES:
        raise SettingsError('Settings file must contain 1..65536 bytes')
    with open(path,'rb') as stream:
        raw = stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise SettingsError('Settings file is too large')
    after = _stamp(path)
    if before != after or len(raw) != before[1]:
        raise SettingsError('Settings file changed during reading; retry next command')
    try:
        text = raw.decode('utf-8-sig')
        _check_depth(text)
        data = json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    except SettingsError:
        raise
    except (ValueError, UnicodeError, RuntimeError) as error:
        raise SettingsError('Invalid JSON/UTF-8: ' + str(error)[:200])
    return validate(data, hashlib.sha256(raw).hexdigest(), path)


def load(path=None):
    """Return (immutable snapshot, warning or None, was_reloaded).

    Metadata is checked once per command. No successful-cache fallback is hidden.
    """
    path = os.path.normcase(os.path.abspath(path or default_path()))
    with _STATE['lock']:
        previous = _STATE['entries'].get(path)
        try:
            stamp = _stamp(path)
            if previous and stamp == previous['stamp']:
                return previous['snapshot'], None, False
            if previous and stamp == previous.get('bad_stamp'):
                return previous['snapshot'], previous['warning'], False
            snapshot = _read_stable(path, stamp)
            _STATE['entries'][path] = dict(stamp=stamp, snapshot=snapshot)
            return snapshot, None, True
        except Exception as error:
            # Boundary guard: file/parser errors cannot escape into the model transaction.
            warning = 'Settings not applied: ' + str(error)[:300]
            if previous:
                previous['bad_stamp'] = locals().get('stamp')
                previous['warning'] = warning + '; using last valid settings.'
                return previous['snapshot'], warning + '; using last valid settings.', False
            raise SettingsError(warning + '; no valid cached settings. No model changes.')
