# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""Read a stable XLSX snapshot without Office, COM or third-party packages."""
import hashlib
import os
import posixpath
import re
import sys
import zipfile
from xml.etree import ElementTree as ET
from hdl_openings.mep_labels import Mapping, text_type

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


class _DotNetZip(object):
    """Avoid IronPython stdlib zipfile's bytes/str failure entirely."""
    def __init__(self, raw):
        import clr
        clr.AddReference('System.IO.Compression')
        from System import Array, Byte
        from System.IO import MemoryStream
        from System.IO.Compression import ZipArchive, ZipArchiveMode
        self.stream = MemoryStream(Array[Byte](list(bytearray(raw))))
        try:
            self.archive = ZipArchive(self.stream, ZipArchiveMode.Read, True)
        except Exception:
            self.stream.Dispose()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            self.archive.Dispose()
        finally:
            self.stream.Dispose()

    def expanded_size(self):
        return sum(entry.Length for entry in self.archive.Entries)

    def namelist(self):
        return [text_type(entry.FullName) for entry in self.archive.Entries]

    def read(self, name):
        from System.IO import StreamReader
        from System.Text import UTF8Encoding
        entry = self.archive.GetEntry(name)
        if entry is None:
            raise ValueError('Missing XLSX entry: ' + name)
        stream = entry.Open()
        reader = None
        try:
            reader = StreamReader(stream, UTF8Encoding(False, True), True)
            return text_type(reader.ReadToEnd())
        finally:
            if reader is not None:
                reader.Dispose()
            else:
                stream.Dispose()


def _is_ironpython():
    return (sys.platform == 'cli' or
            getattr(getattr(sys, 'implementation', None), 'name', '') == 'ironpython')


def _open_zip(raw):
    if _is_ironpython():
        return _DotNetZip(raw)
    from io import BytesIO
    return zipfile.ZipFile(BytesIO(raw))


class _DotNetXmlNode(object):
    """Small ElementTree-compatible view over Unicode-safe System.Xml nodes."""
    def __init__(self, node):
        self.node = node

    @property
    def text(self):
        return text_type(self.node.InnerText)

    def get(self, name, default=None):
        if name.startswith('{'):
            uri, local = name[1:].split('}', 1)
            args = (local, uri)
        else:
            args = (name,)
        if not self.node.HasAttribute(*args):
            return default
        return text_type(self.node.GetAttribute(*args))

    def findall(self, path, namespaces=None):
        from System.Xml import XmlNamespaceManager
        manager = XmlNamespaceManager(self.node.OwnerDocument.NameTable)
        for prefix, uri in (namespaces or {}).items():
            manager.AddNamespace(prefix, uri)
        return [_DotNetXmlNode(node) for node in self.node.SelectNodes(path, manager)]

    def find(self, path, namespaces=None):
        found = self.findall(path, namespaces)
        return found[0] if found else None

    def __iter__(self):
        return iter([_DotNetXmlNode(node) for node in self.node.SelectNodes('*')])


def _parse_dotnet_xml(text):
    import clr
    clr.AddReference('System.Xml')
    from System.Xml import XmlDocument
    doc = XmlDocument()
    doc.XmlResolver = None
    doc.PreserveWhitespace = True
    doc.LoadXml(text)
    return _DotNetXmlNode(doc.DocumentElement)


def _xml(z, name):
    raw = z.read(name)
    # IronPython's XML parser may require str/unicode rather than the bytes
    # returned by ZipFile.read. Decode explicitly, preserving Hebrew text.
    if isinstance(raw, text_type):
        text = raw
    elif raw.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
        text = raw.decode('utf-32')
    elif raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16')
    elif raw.startswith(b'<\x00'):
        text = raw.decode('utf-16-le')
    elif raw.startswith(b'\x00<'):
        text = raw.decode('utf-16-be')
    else:
        text = raw.decode('utf-8-sig')
    if u'<!DOCTYPE' in text or u'<!ENTITY' in text:
        raise ValueError('Unsupported XML declaration')
    if _is_ironpython():
        # IronPython ElementTree.feed can implicitly encode Unicode as ASCII.
        # Keep both parsing and XML traversal in .NET; never invoke expat/feed.
        return _parse_dotnet_xml(text)
    return ET.fromstring(text)


def _rows(z, path, shared):
    root = _xml(z, path)
    rows = []
    for row in root.findall('s:sheetData/s:row', NS):
        cells = {}
        for cell in row.findall('s:c', NS):
            if cell.find('s:f', NS) is not None:
                raise ValueError('Use literal text, not formulas: ' + cell.get('r', ''))
            ref = cell.get('r', '')
            col = re.sub('[0-9]', '', ref)
            value = cell.find('s:v', NS)
            raw = value.text if value is not None and value.text else ''
            typ = cell.get('t')
            if typ == 's':
                raw = shared[int(raw)]
            elif typ == 'inlineStr':
                raw = u''.join(t.text or '' for t in cell.findall('s:is//s:t', NS))
            elif raw and typ not in ('str',):
                raise ValueError('Mapping cells must be text: ' + ref)
            cells[col] = raw
        if any(cells.values()):
            rows.append(cells)
    return rows


def load(path):
    before = os.stat(path)
    if before.st_size > 10*1024*1024:
        raise ValueError('XLSX exceeds 10 MiB')
    with open(path, 'rb') as stream:
        raw = stream.read(10*1024*1024+1)
    after = os.stat(path)
    if (before.st_mtime != after.st_mtime or before.st_size != after.st_size or
            len(raw) != before.st_size):
        raise ValueError('Excel changed while reading; retry')
    with _open_zip(raw) as z:
        expanded = (z.expanded_size() if isinstance(z, _DotNetZip) else
                    sum(i.file_size for i in z.infolist()))
        if expanded > 40*1024*1024:
            raise ValueError('Expanded XLSX exceeds 40 MiB')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [u''.join(t.text or '' for t in si.findall('.//s:t', NS))
                      for si in _xml(z, 'xl/sharedStrings.xml').findall('s:si', NS)]
        rels = dict((r.get('Id'), r.get('Target')) for r in
                    _xml(z, 'xl/_rels/workbook.xml.rels'))
        sheets = {}
        for s in _xml(z, 'xl/workbook.xml').findall('s:sheets/s:sheet', NS):
            target = rels[s.get(REL)]
            name = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            sheets[s.get('name')] = name
        output = []
        for name, key in (('Systems', 'System Type'), ('Categories', 'Category')):
            if name not in sheets:
                raise ValueError('Missing worksheet: ' + name)
            rows = _rows(z, sheets[name], shared)
            expected = {'A': key, 'B': 'SP_OP_System_Label', 'C': 'Discipline'}
            if not rows or any(rows[0].get(k) != v for k, v in expected.items()):
                raise ValueError(name + ': expected columns ' + ', '.join(expected[k] for k in ('A','B','C')))
            output.append([(r.get('A',''), r.get('B',''), r.get('C','')) for r in rows[1:]])
    return Mapping(*output), hashlib.sha256(raw).hexdigest()
