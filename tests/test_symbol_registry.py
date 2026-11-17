#!/usr/bin/env python
#coding:utf-8
# Purpose: test symbol registry
# License: MIT License

import unittest

import svgwrite
from svgwrite.symbolregistry import SymbolRegistry


def make_icon(dwg, color='red'):
    """ A tactical map icon: circle with a cross and a label bar. """
    icon = dwg.g()
    icon.add(dwg.circle(center=(0, 0), r=10, fill='none', stroke=color))
    icon.add(dwg.line((-10, 0), (10, 0), stroke=color))
    icon.add(dwg.line((0, -10), (0, 10), stroke=color))
    return icon


class TestSymbolRegistry(unittest.TestCase):
    def setUp(self):
        self.dwg = svgwrite.Drawing('test.svg', profile='full')
        self.registry = SymbolRegistry(self.dwg)

    def test_identical_content_reuses_symbol(self):
        id1 = self.registry.register(make_icon(self.dwg))
        id2 = self.registry.register(make_icon(self.dwg))
        self.assertEqual(id1, id2)
        self.assertEqual(len(self.registry), 1)
        self.assertEqual(len(self.dwg.defs.elements), 1)

    def test_different_content_gets_new_symbol(self):
        id1 = self.registry.register(make_icon(self.dwg, color='red'))
        id2 = self.registry.register(make_icon(self.dwg, color='blue'))
        self.assertNotEqual(id1, id2)
        self.assertEqual(len(self.dwg.defs.elements), 2)

    def test_stable_generated_ids(self):
        self.assertEqual(self.registry.register(make_icon(self.dwg)), 'symbol1')
        self.assertEqual(self.registry.register(make_icon(self.dwg, color='blue')), 'symbol2')
        # re-registering known content returns the same (stable) id
        self.assertEqual(self.registry.register(make_icon(self.dwg)), 'symbol1')

    def test_explicit_symbol_id(self):
        symbol_id = self.registry.register(make_icon(self.dwg), symbol_id='tank')
        self.assertEqual(symbol_id, 'tank')
        self.assertIn('tank', self.registry)

    def test_two_identical_and_one_different_icon(self):
        # the scenario from the requirements: two identical icons, one different
        id_a = self.registry.register(make_icon(self.dwg))
        id_b = self.registry.register(make_icon(self.dwg))
        id_c = self.registry.register(make_icon(self.dwg, color='green'))
        self.assertEqual(id_a, id_b)
        self.assertNotEqual(id_a, id_c)

        use1 = self.registry.use(id_a, insert=(10, 20))
        use2 = self.registry.use(id_a, insert=(100, 200), transform='rotate(45)')
        use3 = self.registry.use(id_c, insert=(50, 60))

        # defs: exactly 2 symbol definitions, each defined once
        self.assertEqual(len(self.dwg.defs.elements), 2)
        # drawing body: defs + 3 use instances
        uses = [e for e in self.dwg.elements if e.elementname == 'use']
        self.assertEqual(len(uses), 3)
        self.assertEqual([u.attribs.get('x') for u in uses], [10, 100, 50])
        self.assertEqual([u.attribs.get('y') for u in uses], [20, 200, 60])
        self.assertEqual(use2['transform'], 'rotate(45)')
        self.assertIsNone(use1.attribs.get('transform'))

        xml = self.dwg.tostring()
        # each symbol serialized exactly once inside defs
        self.assertEqual(xml.count('<symbol'), 2)
        self.assertEqual(xml.count('<use'), 3)
        # references point at the symbol ids
        self.assertEqual(xml.count('xlink:href="#%s"' % id_a), 2)
        self.assertEqual(xml.count('xlink:href="#%s"' % id_c), 1)
        self.assertIn('id="%s"' % id_a, xml)
        self.assertIn('id="%s"' % id_c, xml)

    def test_register_list_of_elements(self):
        circle = self.dwg.circle(center=(0, 0), r=5)
        rect = self.dwg.rect(insert=(0, 0), size=(5, 5))
        symbol_id = self.registry.register([circle, rect])
        symbol = self.dwg.defs.elements[0]
        self.assertEqual(symbol['id'], symbol_id)
        self.assertEqual(len(symbol.elements), 2)

    def test_register_single_shape(self):
        symbol_id = self.registry.register(self.dwg.rect(insert=(0, 0), size=(5, 5)))
        self.assertIn(symbol_id, self.registry)

    def test_place_registers_and_uses(self):
        use = self.registry.place(make_icon(self.dwg), insert=(7, 8))
        self.assertEqual(use.elementname, 'use')
        self.assertEqual(use['x'], 7)
        self.assertEqual(len(self.dwg.defs.elements), 1)

    def test_use_with_hash_prefix(self):
        symbol_id = self.registry.register(make_icon(self.dwg))
        use = self.registry.use('#' + symbol_id, insert=(1, 2))
        self.assertEqual(use.elementname, 'use')

    def test_use_unknown_id(self):
        self.assertRaises(ValueError, self.registry.use, 'no-such-symbol')

    def test_id_conflict_with_different_content(self):
        self.registry.register(make_icon(self.dwg), symbol_id='icon')
        self.assertRaises(ValueError, self.registry.register,
                          make_icon(self.dwg, color='blue'), symbol_id='icon')

    def test_id_conflict_same_content_different_id(self):
        self.registry.register(make_icon(self.dwg), symbol_id='icon')
        self.assertRaises(ValueError, self.registry.register,
                          make_icon(self.dwg), symbol_id='other')

    def test_id_conflict_with_existing_defs_id(self):
        marker = self.dwg.marker(id='taken')
        self.dwg.defs.add(marker)
        self.assertRaises(ValueError, self.registry.register,
                          make_icon(self.dwg), symbol_id='taken')

    def test_generated_id_skips_existing_defs_ids(self):
        marker = self.dwg.marker(id='symbol1')
        self.dwg.defs.add(marker)
        self.assertEqual(self.registry.register(make_icon(self.dwg)), 'symbol2')

    def test_unsupported_element(self):
        self.assertRaises(ValueError, self.registry.register,
                          self.dwg.text('hello'))
        self.assertRaises(ValueError, self.registry.register,
                          self.dwg.image('test.png'))

    def test_unsupported_nested_element(self):
        icon = make_icon(self.dwg)
        icon.add(self.dwg.text('label'))
        self.assertRaises(ValueError, self.registry.register, icon)

    def test_nested_use_rejected(self):
        icon = make_icon(self.dwg)
        icon.add(self.dwg.use('#whatever'))
        self.assertRaises(ValueError, self.registry.register, icon)

    def test_nested_symbol_rejected(self):
        icon = make_icon(self.dwg)
        icon.add(self.dwg.symbol())
        self.assertRaises(ValueError, self.registry.register, icon)

    def test_register_symbol_or_use_rejected(self):
        self.assertRaises(ValueError, self.registry.register, self.dwg.symbol())
        self.assertRaises(ValueError, self.registry.register, self.dwg.use('#x'))

    def test_circular_reference_rejected(self):
        icon = make_icon(self.dwg)
        inner = self.dwg.g()
        inner.add(self.dwg.circle(center=(0, 0), r=1))
        icon.add(inner)
        inner.elements.append(icon)  # create a cycle
        self.assertRaises(ValueError, self.registry.register, icon)

    def test_empty_group_rejected(self):
        self.assertRaises(ValueError, self.registry.register, self.dwg.g())

    def test_nested_empty_group_rejected(self):
        icon = make_icon(self.dwg)
        icon.add(self.dwg.g())
        self.assertRaises(ValueError, self.registry.register, icon)

    def test_empty_content_rejected(self):
        self.assertRaises(ValueError, self.registry.register, [])

    def test_id_attribute_ignored_for_fingerprint(self):
        icon1 = make_icon(self.dwg)
        icon1['id'] = 'first'
        icon2 = make_icon(self.dwg)
        icon2['id'] = 'second'
        self.assertEqual(self.registry.register(icon1), self.registry.register(icon2))


if __name__ == '__main__':
    unittest.main()
