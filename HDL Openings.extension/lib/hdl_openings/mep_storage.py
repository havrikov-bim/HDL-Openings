# -*- coding: utf-8 -*-
from hdl_openings.mep_json import dumps_ascii
from System import Guid, String
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, Entity, AccessLevel
SCHEMA_ID = Guid('e803865b-9aec-4e1f-9fad-2e3789b23e76')


def schema():
    result = Schema.Lookup(SCHEMA_ID)
    if result is None:
        builder = SchemaBuilder(SCHEMA_ID)
        builder.SetSchemaName('HDLOpeningsMEPIdentificationV1')
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField('Payload', String)
        result = builder.Finish()
    return result


def serialized(payload):
    raw = dumps_ascii(payload)
    if len(raw) > 4*1024*1024:
        raise ValueError('MEP identification payload exceeds 4 MiB')
    return raw


def matches(element, raw):
    s = Schema.Lookup(SCHEMA_ID)
    if s is None:
        return False
    entity = element.GetEntity(s)
    return entity.IsValid() and entity.Get[String](s.GetField('Payload')) == raw


def write(element, raw):
    s = schema()
    entity = Entity(s)
    entity.Set[String](s.GetField('Payload'), raw)
    element.SetEntity(entity)
