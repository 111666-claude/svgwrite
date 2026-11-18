#!/usr/bin/env python
# coding:utf-8
# Author: mozman --<mozman@gmx.at>
# Purpose: test gradient inheritance validation and expansion
# Created: 18.11.2026
# Copyright (C) 2026, Manfred Moitzi
# License: MIT License

import copy
import unittest

from svgwrite import Drawing
from svgwrite.gradients import LinearGradient, _GradientStop
from svgwrite.gradientinheritance import (
    GradientInheritance,
    GradientInheritanceError,
)


def make_three_level_chain():
    """ base -> mid -> top: a three level linear gradient chain.

    * base ('base'): coordinates (0,0)-(100,0), objectBoundingBox, two stops
    * mid  ('mid'):  inherits base, overrides x2, rotates 45 deg, no stops
    * top  ('top'):  inherits mid, local stops override the inherited ones,
      no local geometry
    """
    dwg = Drawing('inheritance.svg', profile='full', debug=True)
    base = dwg.linearGradient(start=(0, 0), end=(100, 0), id='base',
                              gradientUnits='objectBoundingBox')
    base.add_stop_color(0, 'white')
    base.add_stop_color(1, 'black')

    mid = dwg.linearGradient(inherit='#base', id='mid')
    mid['x2'] = 200
    mid.rotate(45)

    top = dwg.linearGradient(inherit='#mid', id='top')
    top.add_stop_color(0.25, 'red')
    top.add_stop_color(0.75, 'blue')

    dwg.defs.add(base)
    dwg.defs.add(mid)
    dwg.defs.add(top)
    return dwg, base, mid, top


class TestGradientInheritanceResolution(unittest.TestCase):
    def setUp(self):
        self.dwg, self.base, self.mid, self.top = make_three_level_chain()
        self.inh = GradientInheritance(self.dwg)

    def test_all_gradients_collected_in_document_order(self):
        infos = self.inh.infos()
        self.assertEqual([info.id for info in infos],
                         ['base', 'mid', 'top'])

    def test_chain_structure(self):
        info = self.inh.info_by_id('top')
        self.assertEqual(info.chain, ['top', 'mid', 'base'])
        self.assertEqual(info.parent_id, 'mid')
        self.assertEqual(info.href, '#mid')
        self.assertEqual(info.elementname, 'linearGradient')

    def test_effective_geometry_local_precedence(self):
        base = self.inh.info_by_id('base')
        self.assertEqual(base.geometry,
                         {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 0})

        mid = self.inh.info_by_id('mid')
        # x2 overridden locally, other coordinates inherited from base
        self.assertEqual(mid.geometry,
                         {'x1': 0, 'y1': 0, 'x2': 200, 'y2': 0})

        top = self.inh.info_by_id('top')
        # no local geometry at all: everything inherited through the chain
        self.assertEqual(top.geometry,
                         {'x1': 0, 'y1': 0, 'x2': 200, 'y2': 0})

    def test_effective_coordinate_system_inherited(self):
        for info in self.inh.infos():
            self.assertEqual(info.gradient_units, 'objectBoundingBox')

    def test_effective_transform(self):
        self.assertIsNone(self.inh.info_by_id('base').transform)
        mid = self.inh.info_by_id('mid')
        self.assertIn('rotate(45)', mid.transform)
        # top has no local transform: inherits mid's transform
        top = self.inh.info_by_id('top')
        self.assertEqual(top.transform, mid.transform)

    def test_effective_stops_local_stops_replace_inherited(self):
        base_stops = self.inh.info_by_id('base').stops
        self.assertEqual([s.attribs['stop-color'] for s in base_stops],
                         ['white', 'black'])

        # mid has no stops: inherits base stops
        mid_stops = self.inh.info_by_id('mid').stops
        self.assertEqual([s.attribs['stop-color'] for s in mid_stops],
                         ['white', 'black'])

        # top has local stops: they replace the inherited ones
        top_info = self.inh.info_by_id('top')
        self.assertEqual(
            [(s.attribs['offset'], s.attribs['stop-color'])
             for s in top_info.stops],
            [(0.25, 'red'), (0.75, 'blue')])

    def test_resolved_stops_are_copies(self):
        info = self.inh.info_by_id('mid')
        info.stops[0].attribs['stop-color'] = 'green'
        # original object untouched
        self.assertEqual(
            self.base.elements[0].attribs['stop-color'], 'white')

    def test_drawing_convenience_method(self):
        infos = self.dwg.check_gradient_inheritance()
        self.assertEqual(len(infos), 3)


class TestRadialInheritance(unittest.TestCase):
    def test_radial_geometry_and_stops(self):
        dwg = Drawing('radial.svg', profile='full')
        base = dwg.radialGradient(center=(10, 20), r=5, id='rbase')
        base.add_stop_color(0, 'white')
        base.add_stop_color(1, 'black')
        child = dwg.radialGradient(inherit=base, id='rchild')
        child['r'] = 9
        dwg.defs.add(base)
        dwg.defs.add(child)

        infos = GradientInheritance(dwg).infos()
        child_info = infos[1]
        self.assertEqual(child_info.geometry,
                         {'cx': 10, 'cy': 20, 'r': 9})
        self.assertEqual(
            [s.attribs['stop-color'] for s in child_info.stops],
            ['white', 'black'])


class TestValidateOnlyDoesNotMutate(unittest.TestCase):
    def test_validate_leaves_objects_untouched(self):
        dwg, base, mid, top = make_three_level_chain()
        before = [g.tostring() for g in (base, mid, top)]

        GradientInheritance(dwg).validate()

        after = [g.tostring() for g in (base, mid, top)]
        self.assertEqual(before, after)
        # references still present
        self.assertIn('xlink:href="#mid"', top.tostring())
        self.assertIn('xlink:href="#base"', mid.tostring())
        # mid still has no own stops
        self.assertEqual(mid.elements, [])


class TestExpansion(unittest.TestCase):
    def setUp(self):
        self.dwg, self.base, self.mid, self.top = make_three_level_chain()

    def test_expand_closes_references(self):
        GradientInheritance(self.dwg).expand()
        for gradient in (self.base, self.mid, self.top):
            self.assertNotIn('xlink:href', gradient.attribs)
            self.assertFalse(hasattr(gradient, 'href'))

    def test_expand_materializes_inherited_attributes(self):
        GradientInheritance(self.dwg).expand()

        self.assertEqual(self.mid.attribs['x1'], 0)
        self.assertEqual(self.mid.attribs['y1'], 0)
        self.assertEqual(self.mid.attribs['y2'], 0)
        self.assertEqual(self.mid.attribs['x2'], 200)  # local value kept
        self.assertEqual(self.mid.attribs['gradientUnits'],
                         'objectBoundingBox')
        self.assertIn('rotate(45)', self.mid.attribs['gradientTransform'])

        # top inherited everything through mid
        self.assertEqual(self.top.attribs['x2'], 200)
        self.assertEqual(self.top.attribs['x1'], 0)
        self.assertEqual(self.top.attribs['gradientUnits'],
                         'objectBoundingBox')
        self.assertIn('rotate(45)', self.top.attribs['gradientTransform'])

    def test_expand_materializes_inherited_stops(self):
        GradientInheritance(self.dwg).expand()

        # mid received deep copies of base stops
        self.assertEqual(
            [s.attribs['stop-color'] for s in self.mid.elements],
            ['white', 'black'])
        # top keeps its own local stops
        self.assertEqual(
            [s.attribs['stop-color'] for s in self.top.elements],
            ['red', 'blue'])

        # copies are independent: mutating an expanded stop of mid must not
        # touch base
        self.mid.elements[0].attribs['stop-color'] = 'green'
        self.assertEqual(
            self.base.elements[0].attribs['stop-color'], 'white')

    def test_expanded_objects_remain_serializable(self):
        GradientInheritance(self.dwg).expand()
        xml = self.dwg.tostring()
        self.assertIn('<linearGradient', xml)
        self.assertNotIn('xlink:href="#', xml)
        # full drawing round trip through pretty printing (parses the XML)
        self.dwg.tostring()
        mid_xml = self.mid.tostring()
        self.assertIn('stop-color="white"', mid_xml)
        self.assertIn('rotate(45)', mid_xml)
        # local stops of top are still serialized
        top_xml = self.top.tostring()
        self.assertIn('stop-color="red"', top_xml)
        self.assertIn('stop-color="blue"', top_xml)

    def test_expand_is_idempotent(self):
        inh = GradientInheritance(self.dwg)
        first = [info.attribs for info in inh.expand()]
        second = GradientInheritance(self.dwg).expand()
        self.assertEqual(
            [info.attribs for info in second], first)
        for gradient in (self.base, self.mid, self.top):
            self.assertNotIn('xlink:href', gradient.attribs)

    def test_expand_via_drawing_method(self):
        infos = self.dwg.expand_gradient_inheritance()
        self.assertEqual(len(infos), 3)
        self.assertNotIn('xlink:href', self.top.attribs)

    def test_original_structure_keeps_other_children(self):
        self.top.set_desc(title='derived gradient')
        GradientInheritance(self.dwg).expand()
        names = [e.elementname for e in self.top.elements]
        self.assertIn('title', names)
        self.assertEqual(names.count('stop'), 2)


class TestValidationErrors(unittest.TestCase):
    def _drawing_with(self, gradients):
        dwg = Drawing('bad.svg', profile='full')
        for gradient in gradients:
            dwg.defs.add(gradient)
        return dwg

    def test_missing_reference_id(self):
        dangling = LinearGradient(id='dangling', inherit='#ghost')
        dangling.add_stop_color(0, 'red')
        dwg = self._drawing_with([dangling])
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn("missing id '#ghost'", str(cm.exception))

    def test_reference_to_non_gradient_element(self):
        dwg = Drawing('bad.svg', profile='full')
        group = dwg.g(id='not-a-gradient')
        gradient = dwg.linearGradient(id='lg', inherit='#not-a-gradient')
        gradient.add_stop_color(0, 'red')
        dwg.defs.add(group)
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn('non-gradient element', str(cm.exception))

    def test_cross_type_inheritance(self):
        dwg = Drawing('bad.svg', profile='full')
        linear = dwg.linearGradient(id='lin')
        linear.add_stop_color(0, 'red')
        radial = dwg.radialGradient(id='rad', inherit='#lin')
        radial.add_stop_color(0, 'blue')
        dwg.defs.add(linear)
        dwg.defs.add(radial)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn('cross type', str(cm.exception))

    def test_duplicate_id(self):
        dwg = Drawing('bad.svg', profile='full')
        first = dwg.linearGradient(id='dup')
        first.add_stop_color(0, 'red')
        second = dwg.linearGradient(id='dup')
        second.add_stop_color(0, 'blue')
        dwg.defs.add(first)
        dwg.defs.add(second)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg)
        self.assertIn('duplicate id', str(cm.exception))

    def test_duplicate_id_on_non_gradient(self):
        dwg = Drawing('bad.svg', profile='full')
        g1 = dwg.g(id='dup')
        g2 = dwg.g(id='dup')
        gradient = dwg.linearGradient(id='lg')
        gradient.add_stop_color(0, 'red')
        dwg.defs.add(g1)
        dwg.defs.add(g2)
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg)

    def test_direct_cycle(self):
        dwg = Drawing('bad.svg', profile='full')
        a = dwg.linearGradient(id='a', inherit='#b')
        a.add_stop_color(0, 'red')
        b = dwg.linearGradient(id='b', inherit='#a')
        b.add_stop_color(0, 'blue')
        dwg.defs.add(a)
        dwg.defs.add(b)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn('cyclic', str(cm.exception))

    def test_three_node_cycle(self):
        dwg = Drawing('bad.svg', profile='full')
        a = dwg.linearGradient(id='a', inherit='#c')
        b = dwg.linearGradient(id='b', inherit='#a')
        c = dwg.linearGradient(id='c', inherit='#b')
        for gradient in (a, b, c):
            gradient.add_stop_color(0, 'red')
            dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        message = str(cm.exception)
        self.assertIn('cyclic', message)
        self.assertIn('a', message)
        self.assertIn('b', message)
        self.assertIn('c', message)

    def test_self_reference_is_a_cycle(self):
        dwg = Drawing('bad.svg', profile='full')
        a = dwg.linearGradient(id='a', inherit='#a')
        a.add_stop_color(0, 'red')
        dwg.defs.add(a)
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).validate()

    def test_empty_stops_chain_root(self):
        dwg = Drawing('bad.svg', profile='full')
        root = dwg.linearGradient(id='root')
        child = dwg.linearGradient(id='child', inherit='#root')
        dwg.defs.add(root)
        dwg.defs.add(child)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn('no stop colors', str(cm.exception))

    def test_empty_stops_local_gradient_is_ok_with_stops_in_chain(self):
        dwg, base, mid, top = make_three_level_chain()
        # mid itself has no stops: chain still valid because base has stops
        infos = GradientInheritance(dwg).validate()
        self.assertEqual(len(infos), 3)

    def test_invalid_offset_number_out_of_range(self):
        dwg = Drawing('bad.svg', profile='full')
        gradient = dwg.linearGradient(id='lg')
        gradient.add_stop_color(1.5, 'red')
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn('invalid stop offset', str(cm.exception))

    def test_invalid_negative_offset(self):
        dwg = Drawing('bad.svg', profile='full')
        gradient = dwg.linearGradient(id='lg')
        gradient.add_stop_color(-0.1, 'red')
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).validate()

    def test_invalid_offset_percentage_out_of_range(self):
        dwg = Drawing('bad.svg', profile='full')
        gradient = dwg.linearGradient(id='lg')
        gradient.add_stop_color('120%', 'red')
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).validate()

    def test_invalid_offset_garbage_string(self):
        # debug=False: the built-in validator stays silent so the inheritance
        # validator has to reject the malformed offset itself
        dwg = Drawing('bad.svg', profile='full', debug=False)
        gradient = dwg.linearGradient(id='lg')
        gradient.add_stop_color('soon', 'red')
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).validate()

    def test_stop_without_offset_attribute(self):
        dwg = Drawing('bad.svg', profile='full', debug=False)
        gradient = dwg.linearGradient(id='lg')
        gradient.add(_GradientStop(color='red', factory=gradient))
        dwg.defs.add(gradient)
        with self.assertRaises(GradientInheritanceError) as cm:
            GradientInheritance(dwg).validate()
        self.assertIn("without 'offset' attribute", str(cm.exception))

    def test_valid_percentage_offsets(self):
        dwg = Drawing('bad.svg', profile='full')
        gradient = dwg.linearGradient(id='lg')
        gradient.add_stop_color('0%', 'red')
        gradient.add_stop_color('50%', 'green')
        gradient.add_stop_color('100%', 'blue')
        dwg.defs.add(gradient)
        infos = GradientInheritance(dwg).validate()
        self.assertEqual(len(infos[0].stops), 3)

    def test_expand_refuses_bad_graph_without_mutation(self):
        dwg = Drawing('bad.svg', profile='full')
        dangling = dwg.linearGradient(id='dangling', inherit='#ghost')
        dangling.add_stop_color(0, 'red')
        dwg.defs.add(dangling)
        before = dangling.tostring()
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).expand()
        self.assertEqual(dangling.tostring(), before)
        self.assertIn('xlink:href="#ghost"', dangling.tostring())


class TestNestedAndObjectReferences(unittest.TestCase):
    def test_gradient_nested_outside_defs_is_found(self):
        dwg = Drawing('nested.svg', profile='full')
        base = dwg.linearGradient(id='base')
        base.add_stop_color(0, 'white')
        base.add_stop_color(1, 'black')
        group = dwg.g()
        child = dwg.linearGradient(id='child', inherit='#base')
        group.add(child)
        dwg.add(group)
        dwg.defs.add(base)

        infos = GradientInheritance(dwg).infos()
        self.assertEqual({info.id for info in infos}, {'base', 'child'})
        self.assertEqual(
            [s.attribs['stop-color']
             for s in GradientInheritance(dwg).info_by_id('child').stops],
            ['white', 'black'])

    def test_inherit_from_object_then_validate_and_expand(self):
        dwg = Drawing('objref.svg', profile='full')
        base = dwg.linearGradient(id='base', start=(0, 0), end=(10, 10))
        base.add_stop_color(0, 'white')
        base.add_stop_color(1, 'black')
        # pass the gradient object itself, like the existing API supports
        child = dwg.linearGradient(inherit=base, id='child')
        dwg.defs.add(base)
        dwg.defs.add(child)

        info = GradientInheritance(dwg).info_by_id('child')
        self.assertEqual(info.parent_id, 'base')
        self.assertEqual(info.geometry['x2'], 10)

        GradientInheritance(dwg).expand()
        self.assertNotIn('xlink:href', child.attribs)
        self.assertEqual(child.attribs['x2'], 10)
        self.assertEqual(
            [s.attribs['stop-color'] for s in child.elements],
            ['white', 'black'])

    def test_svg2_href_attribute_is_supported(self):
        dwg = Drawing('svg2.svg', profile='full')
        base = dwg.linearGradient(id='base')
        base.add_stop_color(0, 'white')
        child = dwg.linearGradient(id='child')
        child.attribs['href'] = '#base'
        dwg.defs.add(base)
        dwg.defs.add(child)

        info = GradientInheritance(dwg).info_by_id('child')
        self.assertEqual(info.parent_id, 'base')

        GradientInheritance(dwg).expand()
        self.assertNotIn('href', child.attribs)
        self.assertEqual(
            [s.attribs['stop-color'] for s in child.elements],
            ['white'])


class TestBadReferenceSVGFixture(unittest.TestCase):
    """ Build the 'bad reference SVG' scenarios and check both the raised
    errors and the serialization behavior of the valid drawing next to them.
    """
    def test_full_bad_reference_suite(self):
        dwg = Drawing('badrefs.svg', profile='full')

        good_base = dwg.linearGradient(id='good_base', start=(0, 0),
                                       end=(5, 5))
        good_base.add_stop_color(0, 'white')
        good_base.add_stop_color(1, 'black')
        good_child = dwg.linearGradient(id='good_child', inherit='#good_base')

        missing = dwg.linearGradient(id='missing', inherit='#nope')
        missing.add_stop_color(0, 'red')

        dwg.defs.add(good_base)
        dwg.defs.add(good_child)
        dwg.defs.add(missing)

        with self.assertRaises(GradientInheritanceError) as cm:
            dwg.check_gradient_inheritance()
        self.assertIn("missing id '#nope'", str(cm.exception))

        # the valid part of the drawing still serializes untouched
        self.assertIn('xlink:href="#good_base"', good_child.tostring())

        # remove the bad gradient: validation and expansion now succeed
        dwg.defs.elements.remove(missing)
        infos = dwg.expand_gradient_inheritance()
        self.assertEqual(len(infos), 2)
        xml = dwg.tostring()
        self.assertNotIn('xlink:href', xml)
        self.assertIn('x2="5"', xml)
        # inherited stops materialized into good_child
        self.assertIn('stop-color="white"', good_child.tostring())

    def test_deepcopy_of_drawing_still_validates(self):
        dwg, base, mid, top = make_three_level_chain()
        snapshot = copy.deepcopy(dwg)
        infos = GradientInheritance(snapshot).validate()
        self.assertEqual([i.id for i in infos], ['base', 'mid', 'top'])


class TestEdgeCases(unittest.TestCase):
    def test_drawing_without_gradients_validates_empty(self):
        dwg = Drawing('empty.svg', profile='full')
        self.assertEqual(GradientInheritance(dwg).validate(), [])
        self.assertEqual(dwg.check_gradient_inheritance(), [])

    def test_resolve_without_gradient_raises(self):
        dwg = Drawing('empty.svg', profile='full')
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).resolve()

    def test_expand_on_empty_drawing_is_a_noop(self):
        dwg = Drawing('empty.svg', profile='full')
        self.assertEqual(dwg.expand_gradient_inheritance(), [])

    def test_spread_method_inherited(self):
        dwg = Drawing('spread.svg', profile='full')
        base = dwg.linearGradient(id='base', spreadMethod='reflect')
        base.add_stop_color(0, 'white')
        child = dwg.linearGradient(id='child', inherit='#base')
        dwg.defs.add(base)
        dwg.defs.add(child)

        info = GradientInheritance(dwg).info_by_id('child')
        self.assertEqual(info.spread_method, 'reflect')

        GradientInheritance(dwg).expand()
        self.assertEqual(child.attribs['spreadMethod'], 'reflect')

    def test_info_by_id_rejects_cross_type_chain(self):
        dwg = Drawing('bad.svg', profile='full')
        linear = dwg.linearGradient(id='lin')
        linear.add_stop_color(0, 'red')
        radial = dwg.radialGradient(id='rad', inherit='#lin')
        radial.add_stop_color(0, 'blue')
        dwg.defs.add(linear)
        dwg.defs.add(radial)
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).info_by_id('rad')

    def test_info_by_unknown_id_raises(self):
        dwg = Drawing('bad.svg', profile='full')
        with self.assertRaises(GradientInheritanceError):
            GradientInheritance(dwg).info_by_id('ghost')

    def test_local_none_attribute_does_not_block_inheritance(self):
        dwg = Drawing('none.svg', profile='full')
        base = dwg.linearGradient(id='base', start=(1, 2), end=(3, 4))
        base.add_stop_color(0, 'white')
        child = dwg.linearGradient(id='child', inherit='#base')
        child.attribs['x1'] = None  # explicitly set but serializes away
        dwg.defs.add(base)
        dwg.defs.add(child)

        info = GradientInheritance(dwg).info_by_id('child')
        self.assertEqual(info.geometry['x1'], 1)
        GradientInheritance(dwg).expand()
        self.assertEqual(child.attribs['x1'], 1)


if __name__ == '__main__':
    unittest.main()
