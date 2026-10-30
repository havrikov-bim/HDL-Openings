# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest
from types import SimpleNamespace as NS
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings.mep_json import dumps_ascii,quote


class JsonTests(unittest.TestCase):
    def test_hebrew_lrm_payload_roundtrip(self):
        data=dict(source_title='Bldg\u200e מלון',system_type='מים קרים',label='מים\u200e',discipline='אינסטלציה',
                  path='C:\\משתמש\\mapping.xlsx',entry_mm=25.1,elements=['א','ב'],empty=None,yes=True,no=False)
        raw=dumps_ascii(data)
        self.assertEqual(json.loads(raw),data)
        self.assertTrue(raw.isascii())
        self.assertIn('\\u200e',raw)
    def test_every_string_escape(self):
        s='"\\\n\t\r\b\f\x00\x1f\x7fא\u200e\U0001f600'
        self.assertEqual(json.loads(quote(s)),s)
        self.assertTrue(quote(s).isascii())
    def test_stable_key_order_and_nested_values(self):
        self.assertEqual(dumps_ascii({'ב':[1,0.5,False],'א':{}}),dumps_ascii({'א':{},'ב':[1,0.5,False]}))
    def test_invalid_numbers_rejected(self):
        for x in [float('nan'),float('inf')]:
            with self.assertRaises(ValueError):dumps_ascii({'x':x})
    def test_clr_string_without_ascii_conversion(self):
        class String:
            def GetType(self):return NS(FullName='System.String')
            def __str__(self):return 'מלון\u200e'
        self.assertEqual(json.loads(dumps_ascii(String())),'מלון\u200e')
    def test_unknown_object_rejected(self):
        with self.assertRaises(TypeError):dumps_ascii(object())


if __name__=='__main__':unittest.main()
