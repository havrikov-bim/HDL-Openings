# -*- coding: utf-8 -*-
"""Exercise .NET XML adapter contracts without requiring a Revit process."""
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from xml.etree import ElementTree as ET
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings import mep_excel
PARSE=ET.fromstring


class Manager:
    def __init__(self,table):self.ns={}
    def AddNamespace(self,p,u):self.ns[p]=u


class Node:
    def __init__(self,element,doc):self.e,self.OwnerDocument=element,doc
    @property
    def InnerText(self):return ''.join(self.e.itertext())
    def key(self,args):return '{'+args[1]+'}'+args[0] if len(args)==2 else args[0]
    def HasAttribute(self,*args):return self.key(args) in self.e.attrib
    def GetAttribute(self,*args):return self.e.attrib.get(self.key(args),'')
    def SelectNodes(self,path,manager=None):
        return [Node(e,self.OwnerDocument) for e in self.e.findall(path,manager.ns if manager else {})]


class Document:
    NameTable=None
    def LoadXml(self,text):self.DocumentElement=Node(PARSE(text),self)


class XmlTests(unittest.TestCase):
    def setUp(self):
        self.modules={'clr':NS(AddReference=lambda name:None),
                      'System.Xml':NS(XmlDocument=Document,XmlNamespaceManager=Manager)}
        module_patch=patch.dict(sys.modules,self.modules)
        module_patch.start();self.addCleanup(module_patch.stop)
    def parse(self,text):
        # Reproduce the observed parser limitation: any ElementTree parsing is forbidden.
        with patch.dict(sys.modules,self.modules),patch.object(sys,'platform','cli'),patch.object(ET,'fromstring',side_effect=UnicodeEncodeError('ascii','א',0,1,'ordinal not in range(128)')):
            return mep_excel._xml(NS(read=lambda name:text),'test.xml')
    def test_hebrew_and_rich_runs(self):
        root=self.parse('<sst xmlns="'+mep_excel.NS['s']+'"><si><r><t>מיזוג </t></r><r><t>אוויר</t></r></si></sst>')
        value=''.join(t.text for t in root.findall('s:si',mep_excel.NS)[0].findall('.//s:t',mep_excel.NS))
        self.assertEqual(value,'מיזוג אוויר')
    def test_namespaced_attributes_and_iteration(self):
        root=self.parse('<workbook xmlns="'+mep_excel.NS['s']+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="מים" r:id="rId1"/></sheets></workbook>')
        sheet=root.find('s:sheets/s:sheet',mep_excel.NS)
        self.assertEqual(sheet.get(mep_excel.REL),'rId1');self.assertEqual(sheet.get('name'),'מים')
        self.assertEqual(sheet.get('missing','fallback'),'fallback');self.assertEqual(len(list(root)),1)
    def test_inline_cells(self):
        xml='<worksheet xmlns="'+mep_excel.NS['s']+'"><sheetData><row><c r="A1" t="inlineStr"><is><t>מים</t></is></c></row></sheetData></worksheet>'
        with patch.dict(sys.modules,self.modules),patch.object(sys,'platform','cli'),patch.object(ET,'fromstring',side_effect=AssertionError('ElementTree parser invoked')):
            self.assertEqual(mep_excel._rows(NS(read=lambda name:xml),'sheet.xml',[]),[{'A':'מים'}])
    def test_template_all_xml_without_elementtree_parser(self):
        p=os.path.join(os.path.dirname(__file__),'..','HDL_MEP_Mapping.xlsx')
        # Standard ZIP backend supplies fixture entries; XML always uses .NET adapter.
        from io import BytesIO
        import zipfile
        with patch.dict(sys.modules,self.modules),patch.object(sys,'platform','cli'),patch.object(mep_excel,'_open_zip',side_effect=lambda raw:zipfile.ZipFile(BytesIO(raw))),patch.object(ET,'fromstring',side_effect=AssertionError('ElementTree parser invoked')):
            m,_=mep_excel.load(p)
        self.assertEqual(m.resolve(category='Conduits'),('Electricity','Electrical'))


if __name__=='__main__':unittest.main()
