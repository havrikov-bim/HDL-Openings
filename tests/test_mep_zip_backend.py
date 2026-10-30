# -*- coding: utf-8 -*-
import io
import os
import sys
import unittest
import zipfile
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings import mep_excel


class DotNetBackendTests(unittest.TestCase):
    def setUp(self):
        self.disposed=[]
        outer=self
        class Stream(io.BytesIO):
            def Dispose(self):outer.disposed.append('stream');self.close()
        class ArrayFactory:
            def __getitem__(self,t):return lambda values:bytes(values)
        class Entry:
            def __init__(self,archive,name):self.archive,self.FullName=archive,name;self.Length=archive.getinfo(name).file_size
            def Open(self):return Stream(self.archive.read(self.FullName))
        class Archive:
            def __init__(self,stream,mode,leave_open):
                self.z=zipfile.ZipFile(stream);self.Entries=[Entry(self.z,n) for n in self.z.namelist()]
            def GetEntry(self,name):return next((e for e in self.Entries if e.FullName==name),None)
            def Dispose(self):outer.disposed.append('archive');self.z.close()
        class Reader:
            def __init__(self,stream,encoding,detect):self.stream=stream
            def ReadToEnd(self):
                b=self.stream.read()
                return b.decode('utf-16' if b.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
            def Dispose(self):outer.disposed.append('reader');self.stream.Dispose()
        self.mods={'clr':NS(AddReference=lambda name:None),
                   'System':NS(Array=ArrayFactory(),Byte=int),
                   'System.IO':NS(MemoryStream=Stream,StreamReader=Reader),
                   'System.IO.Compression':NS(ZipArchive=Archive,ZipArchiveMode=NS(Read=0)),
                   'System.Text':NS(UTF8Encoding=lambda *args:object())}
    def test_ironpython_routes_away_from_stdlib(self):
        with patch.object(sys,'platform','cli'),patch.object(mep_excel,'_DotNetZip',return_value='dotnet') as ctor,patch.object(mep_excel.zipfile,'ZipFile',side_effect=AssertionError('stdlib must not run')):
            self.assertEqual(mep_excel._open_zip(b'PK'),'dotnet');ctor.assert_called_once_with(b'PK')
    def test_full_template_through_dotnet_adapter(self):
        p=os.path.join(os.path.dirname(__file__),'..','HDL_MEP_Mapping.xlsx')
        with patch.dict(sys.modules,self.mods),patch.object(sys,'platform','cli'),patch.object(mep_excel,'_parse_dotnet_xml',side_effect=mep_excel.ET.fromstring):
            m,h=mep_excel.load(p)
        self.assertEqual(m.resolve(category='Conduits'),('Electricity','Electrical'))
        self.assertIn('archive',self.disposed);self.assertIn('reader',self.disposed)
    def test_hebrew_shared_strings_and_disposal(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('text.xml','<t>חשמל</t>'.encode('utf-8'))
        with patch.dict(sys.modules,self.mods):
            with mep_excel._DotNetZip(b.getvalue()) as z:
                self.assertEqual(mep_excel._xml(z,'text.xml').text,'חשמל')
        self.assertIn('archive',self.disposed)
    def test_missing_entry_still_disposes(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w'):pass
        with patch.dict(sys.modules,self.mods):
            with self.assertRaises(ValueError):
                with mep_excel._DotNetZip(b.getvalue()) as z:z.read('missing')
        self.assertIn('archive',self.disposed)


if __name__=='__main__':unittest.main()
