# -*- coding: utf-8 -*-
"""XLSX byte streams must reach IronPython's XML parser as Unicode text."""
import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'HDL Openings.extension', 'lib'))
from hdl_openings import mep_excel


class EncodingTests(unittest.TestCase):
    def parse(self,raw):
        original=mep_excel.ET.fromstring
        def text_only(value):
            if not isinstance(value,str):raise TypeError('expected str, got bytes')
            return original(value)
        with patch.object(mep_excel.ET,'fromstring',side_effect=text_only):
            return mep_excel._xml(NS(read=lambda n:raw),'test.xml')
    def test_utf8_hebrew(self):
        text='<?xml version="1.0" encoding="UTF-8"?><t>מיזוג אוויר</t>'
        self.assertEqual(self.parse(text.encode('utf-8')).text,'מיזוג אוויר')
    def test_utf8_bom(self):
        self.assertEqual(self.parse('<t>מים</t>'.encode('utf-8-sig')).text,'מים')
    def test_utf16(self):
        self.assertEqual(self.parse('<t>חשמל</t>'.encode('utf-16')).text,'חשמל')
    def test_utf16_without_bom(self):
        for encoding in ('utf-16-le','utf-16-be'):
            self.assertEqual(self.parse('<t>חשמל</t>'.encode(encoding)).text,'חשמל')
    def test_utf32_bom(self):
        self.assertEqual(self.parse('<t>מים</t>'.encode('utf-32')).text,'מים')
    def test_text_already_decoded(self):
        self.assertEqual(self.parse('<t>מים</t>').text,'מים')
    def test_dtd_rejected_after_decoding(self):
        for encoding in ('utf-8','utf-16'):
            with self.assertRaises(ValueError):
                self.parse('<!DOCTYPE t><t />'.encode(encoding))
    def test_exported_template(self):
        p=os.path.join(os.path.dirname(__file__),'..','HDL_MEP_Mapping.xlsx')
        mapping,fingerprint=mep_excel.load(p)
        self.assertEqual(mapping.resolve(category='Cable Trays'),('Electricity','Electrical'))
        self.assertEqual(len(fingerprint),64)


if __name__=='__main__':unittest.main()
