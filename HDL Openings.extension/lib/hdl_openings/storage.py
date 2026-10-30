# -*- coding: utf-8 -*-
import json
from hdl_openings.synchronization import validate_payload
from System import Guid, String
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, Entity, AccessLevel

LEGACY_SCHEMA_ID = Guid('5d7ba5df-a941-4232-9bac-d40e9c783460')
SCHEMA_ID = Guid('6f68c121-bf2f-4174-baf2-a2514c05e5d1')


def _pairs(items):
    data = {}
    for key,value in items:
        if key in data:
            raise ValueError('Duplicate stored field: '+key)
        data[key] = value
    return data


def _nonfinite(value):
    raise ValueError('Nonfinite stored value: '+value)


def schema():
    found = Schema.Lookup(SCHEMA_ID)
    if found:
        return found
    builder = SchemaBuilder(SCHEMA_ID)
    builder.SetSchemaName('HDLOpeningsSynchronizationV2')
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.AddSimpleField('Payload', String)
    builder.AddSimpleField('OpeningGuid', Guid)
    return builder.Finish()


def read(element):
    for schema_id in (SCHEMA_ID, LEGACY_SCHEMA_ID):
        s = Schema.Lookup(schema_id)
        if s is None:
            continue
        entity = element.GetEntity(s)
        if not entity.IsValid():
            continue
        raw = entity.Get[String](s.GetField('Payload'))
        if len(raw) > 1048576:
            raise ValueError('Stored payload exceeds 1 MiB')
        payload = validate_payload(json.loads(raw,object_pairs_hook=_pairs,parse_constant=_nonfinite))
        if schema_id == SCHEMA_ID:
            guid = str(entity.Get[Guid](s.GetField('OpeningGuid'))).lower()
            if guid != payload.get('opening_guid','').lower():
                raise ValueError('OpeningGuid field does not match payload')
        return payload
    return None


def write(element, payload):
    s = schema()
    entity = Entity(s)
    entity.Set[String](s.GetField('Payload'), json.dumps(validate_payload(payload), sort_keys=True, allow_nan=False))
    entity.Set[Guid](s.GetField('OpeningGuid'), Guid(payload['opening_guid']))
    element.SetEntity(entity)
    legacy = Schema.Lookup(LEGACY_SCHEMA_ID)
    if legacy is not None and element.GetEntity(legacy).IsValid():
        element.DeleteEntity(legacy)
