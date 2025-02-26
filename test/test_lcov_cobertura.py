#!/usr/bin/env python

# Copyright 2011-2012 Eric Wendelin
#
# This is free software, licensed under the Apache License, Version 2.0,
# available in the accompanying LICENSE.txt file.

import shutil
import tempfile
import unittest
from xmldiff import main as xmldiff
from xmldiff import actions

from lcov_cobertura import LcovCobertura, main
from distutils.spawn import find_executable


class Test(unittest.TestCase):
    """Unit tests for lcov_cobertura."""

    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def assertXmlEquals(self, left, right):
        xml_diff = xmldiff.diff_texts(left, right)
        # ignore MoveNode, order doesn't matter
        xml_diff = [x for x in xml_diff if not isinstance(x, actions.MoveNode)]

        # ignore timestamps, only check that it's an integer
        xml_diff = [x for x in xml_diff if not (isinstance(x, actions.UpdateAttrib) and
                                                x.name == "timestamp" and
                                                x.value.isdigit())]

        self.assertEqual(len(xml_diff), 0, xml_diff)

    def test_parse(self):
        converter = LcovCobertura(
            'SF:foo/file.ext\nDA:1,1\nDA:2,0\nBRDA:1,1,1,1\nBRDA:1,1,2,0\nend_of_record\n')
        result = converter.parse()
        self.assertTrue('packages' in result)
        self.assertTrue('foo' in result['packages'])
        self.assertEqual(result['packages']['foo']['branches-covered'], 1)
        self.assertEqual(result['packages']['foo']['branches-total'], 2)
        self.assertEqual(result['packages']['foo']['branch-rate'], '0.5')
        self.assertEqual(result['packages']['foo']['line-rate'], '0.5')
        self.assertEqual(result['packages']['foo']['lines-covered'], 1)
        self.assertEqual(result['packages']['foo']['lines-total'], 2)
        self.assertEqual(result['packages']['foo']['classes']['foo/file.ext']['branches-covered'], 1)
        self.assertEqual(result['packages']['foo']['classes']['foo/file.ext']['branches-total'], 2)
        self.assertEqual(result['packages']['foo']['classes']['foo/file.ext']['methods'], {})

    def test_parse_with_functions(self):
        converter = LcovCobertura(
            'TN:\nSF:foo/file.ext\nDA:1,1\nDA:2,0\nFN:1,(anonymous_1)\nFN:2,namedFn\nFNDA:1,(anonymous_1)\nend_of_record\n')
        result = converter.parse()
        self.assertEqual(result['packages']['foo']['line-rate'], '0.5')
        self.assertEqual(result['packages']['foo']['lines-covered'], 1)
        self.assertEqual(result['packages']['foo']['lines-total'], 2)
        self.assertEqual(result['packages']['foo']['classes']['foo/file.ext']['methods']['(anonymous_1)'], ['1', '1'])
        self.assertEqual(result['packages']['foo']['classes']['foo/file.ext']['methods']['namedFn'], ['2', '0'])

    def test_exclude_package_from_parser(self):
        converter = LcovCobertura(
            'SF:foo/file.ext\nDA:1,1\nDA:2,0\nend_of_record\nSF:bar/file.ext\nDA:1,1\nDA:2,1\nend_of_record\n',
            '.',
            'foo')
        result = converter.parse()
        self.assertTrue('foo' not in result['packages'])
        self.assertTrue('bar' in result['packages'])
        # Verify that excluded package did not skew line coverage totals
        self.assertEqual(result['packages']['bar']['line-rate'], '1.0')

    def test_generate_cobertura_xml(self):
        converter = LcovCobertura(
            'TN:\nSF:foo/file.ext\nDA:1,1\nDA:2,0\nBRDA:1,1,1,1\nBRDA:1,1,2,0\nFN:1,(anonymous_1)\nFN:2,namedFn\nFNDA:1,(anonymous_1)\nend_of_record\n')
        TEST_XML = r"""<?xml version="1.0" ?>
<!DOCTYPE coverage
  SYSTEM 'http://cobertura.sourceforge.net/xml/coverage-04.dtd'>
<coverage branch-rate="0.5" branches-covered="1" branches-valid="2" complexity="0" line-rate="0.5" lines-covered="1" lines-valid="2" timestamp="1346815648000" version="2.0.3">
    <sources>
        <source>.</source>
    </sources>
    <packages>
        <package line-rate="0.5" branch-rate="0.5" name="foo" complexity="0">
            <classes>
                <class branch-rate="0.5" complexity="0" filename="Bar" line-rate="0.5" name="file.ext">
                    <methods>
                        <method name="(anonymous_1)" signature="" line-rate="1.0" branch-rate="1.0">
                            <lines>
                                <line hits="1" number="1" branch="false"/>
                            </lines>
                        </method>
                        <method name="namedFn" signature="" line-rate="0.0" branch-rate="0.0">
                            <lines>
                                <line hits="0" number="2" branch="false"/>
                            </lines>
                        </method>
                    </methods>
                    <lines>
                        <line branch="true" hits="1" number="1" condition-coverage="50% (1/2)"/>
                        <line branch="false" hits="0" number="2"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""

        parsed_lcov = {'packages': {
            'foo': {'branches-covered': 1, 'line-rate': '0.5', 'branch-rate': '0.5',
                    'lines-covered': 1, 'branches-total': 2, 'lines-total': 2,
                    'classes': {
                    'Bar': {'branches-covered': 1, 'lines-covered': 1,
                            'branches-total': 2,
                            'methods': {
                                '(anonymous_1)': ['1', '1'],
                                'namedFn': ['2', '0']
                            },
                            'lines': {
                                1: {'hits': '1', 'branches-covered': 1,
                                    'branches-total': 2, 'branch': 'true'},
                                2: {'hits': '0', 'branches-covered': 0,
                                    'branches-total': 0, 'branch': 'false'}
                            },
                            'lines-total': 2, 'name': 'file.ext'}},
                    }},
                       'summary': {'branches-covered': 1, 'branches-total': 2,
                                   'lines-covered': 1, 'lines-total': 2},
                       'timestamp': '1346815648000'}
        xml = converter.generate_cobertura_xml(parsed_lcov, indent="    ")
        self.assertXmlEquals(xml, TEST_XML)

    def test_treat_non_integer_line_execution_count_as_zero(self):
        converter = LcovCobertura(
            'SF:foo/file.ext\nDA:1,=====\nDA:2,2\nBRDA:1,1,1,1\nBRDA:1,1,2,0\nend_of_record\n')
        result = converter.parse()
        self.assertEqual(result['packages']['foo']['lines-covered'], 1)
        self.assertEqual(result['packages']['foo']['lines-total'], 2)

    @unittest.skipIf(find_executable("c++filt") is None,
                     "requires c++filt installed")
    def test_demangle(self):
        input_file = "{}/test_demangle.lcov".format(self.test_dir)
        output_file = "{}/test_demangle.xml".format(self.test_dir)

        with open(input_file, "w") as f:
            f.write("""\
TN:
SF:foo/foo.cpp
FN:3,_ZN3Foo6answerEv
FNDA:1,_ZN3Foo6answerEv
FN:8,_ZN3Foo3sqrEi
FNDA:1,_ZN3Foo3sqrEi
DA:3,1
DA:5,1
DA:8,1
DA:10,1
end_of_record""")
        main(["test_lcov_cobertura.py", "--output", output_file, "--demangle", input_file])

        TEST_XML = r"""<?xml version="1.0" ?>
<!DOCTYPE coverage
  SYSTEM 'http://cobertura.sourceforge.net/xml/coverage-04.dtd'>
<coverage branch-rate="0.0" branches-covered="0" branches-valid="0" complexity="0" line-rate="1.0" lines-covered="4" lines-valid="4" timestamp="1" version="2.0.3">
    <sources>
        <source>.</source>
    </sources>
    <packages>
        <package line-rate="1.0" branch-rate="0.0" name="foo" complexity="0">
            <classes>
                <class branch-rate="0.0" complexity="0" filename="foo/foo.cpp" line-rate="1.0" name="foo.foo.cpp">
                    <methods>
                        <method name="Foo::answer()" signature="" line-rate="1.0" branch-rate="1.0">
                            <lines>
                                <line hits="1" number="3" branch="false"/>
                            </lines>
                        </method>
                        <method name="Foo::sqr(int)" signature="" line-rate="1.0" branch-rate="1.0">
                            <lines>
                                <line hits="1" number="8" branch="false"/>
                            </lines>
                        </method>
                    </methods>
                    <lines>
                        <line branch="false" hits="1" number="3"/>
                        <line branch="false" hits="1" number="5"/>
                        <line branch="false" hits="1" number="8"/>
                        <line branch="false" hits="1" number="10"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""
        with open(output_file, "r") as f:
            xml = f.read()
        self.assertXmlEquals(xml, TEST_XML)

    @unittest.skipIf(find_executable("rustfilt") is None,
                     "requires rustfilt installed")
    def test_demangler_rustfilt(self):
        input_file = "{}/test_demangler_rustfilt.lcov".format(self.test_dir)
        output_file = "{}/test_demangler_rustfilt.xml".format(self.test_dir)
        with open(input_file, "w") as f:
            f.write("""\
SF:src/main.rs
FN:6,_RNvCsie3AuTHCqpB_10rust_hello4calc
FN:2,_RNvCsie3AuTHCqpB_10rust_hello4main
FNDA:1,_RNvCsie3AuTHCqpB_10rust_hello4calc
FNDA:1,_RNvCsie3AuTHCqpB_10rust_hello4main
FNF:2
FNH:2
DA:2,1
DA:3,1
DA:4,1
DA:6,1
DA:7,1
DA:8,0
DA:9,1
DA:10,1
DA:11,1
DA:12,1
BRF:0
BFH:0
LF:10
LH:9
end_of_record""")
        main(["test_lcov_cobertura.py", "--output", output_file, "--demangler=rustfilt", input_file])

        TEST_XML = """\
<?xml version="1.0" ?>
<!DOCTYPE coverage
  SYSTEM 'http://cobertura.sourceforge.net/xml/coverage-04.dtd'>
<coverage branch-rate="0.0" branches-covered="0" branches-valid="0" complexity="0" line-rate="0.9" lines-covered="9" lines-valid="10" timestamp="1620211505" version="2.0.3">
        <sources>
                <source>.</source>
        </sources>
        <packages>
                <package branch-rate="0.0" complexity="0" line-rate="0.9" name="src">
                        <classes>
                                <class branch-rate="0.0" complexity="0" filename="src/main.rs" line-rate="0.9" name="src.main.rs">
                                        <methods>
                                                <method branch-rate="1.0" line-rate="1.0" name="rust_hello::calc" signature="">
                                                        <lines>
                                                                <line branch="false" hits="1" number="6"/>
                                                        </lines>
                                                </method>
                                                <method branch-rate="1.0" line-rate="1.0" name="rust_hello::main" signature="">
                                                        <lines>
                                                                <line branch="false" hits="1" number="2"/>
                                                        </lines>
                                                </method>
                                        </methods>
                                        <lines>
                                                <line branch="false" hits="1" number="2"/>
                                                <line branch="false" hits="1" number="3"/>
                                                <line branch="false" hits="1" number="4"/>
                                                <line branch="false" hits="1" number="6"/>
                                                <line branch="false" hits="1" number="7"/>
                                                <line branch="false" hits="0" number="8"/>
                                                <line branch="false" hits="1" number="9"/>
                                                <line branch="false" hits="1" number="10"/>
                                                <line branch="false" hits="1" number="11"/>
                                                <line branch="false" hits="1" number="12"/>
                                        </lines>
                                </class>
                        </classes>
                </package>
        </packages>
</coverage>"""

        with open(output_file, "r") as f:
            xml = f.read()
        self.assertXmlEquals(xml, TEST_XML)

if __name__ == '__main__':
    unittest.main(verbosity=2)
