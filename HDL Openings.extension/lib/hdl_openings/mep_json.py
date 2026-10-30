# -*- coding: utf-8 -*-
"""ASCII JSON serialization without IronPython's implicit string encoding."""
import json
from hdl_openings.mep_labels import text_type
try:
    STRING_TYPES = (basestring,)
    INTEGER_TYPES = (int, long)
except NameError:
    STRING_TYPES = (str,)
    INTEGER_TYPES = (int,)


def quote(value):
    value = text_type(value)
    parts = ['"']
    for character in value:
        code = ord(character)
        if code == 34:
            parts.append('\\"')
        elif code == 92:
            parts.append('\\\\')
        elif code < 32 or code > 126:
            if code > 65535:
                code -= 65536
                parts.append('\\u%04x\\u%04x' % (55296+(code>>10), 56320+(code&1023)))
            else:
                parts.append('\\u%04x' % code)
        else:
            parts.append(chr(code))
    parts.append('"')
    return ''.join(parts)


def dumps_ascii(value):
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, STRING_TYPES):
        return quote(value)
    if isinstance(value, INTEGER_TYPES + (float,)):
        return json.dumps(value, allow_nan=False)
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(dumps_ascii(item) for item in value) + ']'
    if isinstance(value, dict):
        items = sorted((text_type(key), item) for key, item in value.items())
        return '{' + ','.join(quote(key)+':'+dumps_ascii(item) for key,item in items) + '}'
    # A CLR System.String may not pass the native Python string type test.
    if hasattr(value, 'GetType') and text_type(value.GetType().FullName) == 'System.String':
        return quote(value)
    raise TypeError('Unsupported identification JSON value: ' + type(value).__name__)
