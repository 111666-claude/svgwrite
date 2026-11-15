#!/usr/bin/env python
# coding:utf-8
# Author: mozman --<mozman@gmx.at>
# Purpose: test reuse module (shared symbol/use de-duplication)
# Created: 2026-11-15
# Copyright (C) 2026, Manfred Moitzi
# License: MIT License
import re
import unittest

from svgwrite import Drawing
from svgwrite.reuse import deduplicate


def ids_and_refs(xml):
    ids = set(re.findall(r'id="([^"]+)"', xml))
    refs = (re.findall(r'url\(#([^)]+)\)', xml)
            + re.findall(r'xlink:href="#([^"]+)"', xml))
    return ids, refs


class RepeatedIcon(object):
    """ Build the nested-group icon used by most tests. """

    def __init__(self, drawing, gradient_id):
        self.drawing = drawing
        self.gradient_id = gradient_id

    def build(self):
        dwg = self.drawing
        group = dwg.g()
        gradient = dwg.linearGradient(start=(0, 0), end=(20, 20),
                                      id=self.gradient_id)
        gradient.add_stop_color(0, 'white').add_stop_color(1, 'teal')
        group.add(gradient)
        nested = group.add(dwg.g(stroke='black', **{'stroke-width': 1}))
        nested.add(dwg.rect(insert=(0, 0), size=(20, 20),
                            fill='url(#%s)' % self.gradient_id))
        nested.add(dwg.circle(center=(10, 10), r=5, fill='none'))
        return group


class TestDeduplicateStructure(unittest.TestCase):
    def _drawing_with_three_icons(self):
        dwg = Drawing()
        for index, x in enumerate((0, 30, 60)):
            group = RepeatedIcon(dwg, 'lg%d' % index).build()
            group.translate(x, 0)
            dwg.add(group)
        return dwg

    def test_hoists_one_symbol_and_replaces_instances(self):
        dwg = self._drawing_with_three_icons()
        dwg.deduplicate()
        xml = dwg.tostring()

        self.assertEqual(xml.count('<symbol'), 1)
        self.assertEqual(xml.count('<use'), 3)
        # the whole original inline content moved into the symbol
        self.assertIn('<linearGradient', xml.split('</symbol>')[0])
        self.assertIn('<g stroke="black"', xml.split('</symbol>')[0])
        # symbol is inside defs
        self.assertIn('<defs><symbol', xml)
        # every instance keeps its own positioning transform
        self.assertEqual(
            re.findall(r'<use[^>]*transform="([^"]+)"', xml),
            ['translate(0,0)', 'translate(30,0)', 'translate(60,0)'])

    def test_all_ids_unique_and_all_references_resolve(self):
        dwg = self._drawing_with_three_icons()
        dwg.deduplicate()
        ids, refs = ids_and_refs(dwg.tostring())
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ref in ids for ref in refs))

    def test_gradient_ids_rewritten_inside_symbol(self):
        dwg = self._drawing_with_three_icons()
        dwg.deduplicate()
        xml = dwg.tostring()
        # original per-instance gradient ids are gone
        self.assertNotIn('id="lg0"', xml)
        # the surviving gradient id matches its url(#...) reference
        gradient_ids = re.findall(
            r'<linearGradient id="([^"]+)"', xml)
        self.assertEqual(len(gradient_ids), 1)
        self.assertIn('url(#%s)' % gradient_ids[0], xml)

    def test_symbol_carries_overflow_visible(self):
        dwg = self._drawing_with_three_icons()
        dwg.deduplicate()
        self.assertIn('overflow="visible"', dwg.tostring())

    def test_idempotent_serialization(self):
        dwg = self._drawing_with_three_icons()
        dwg.deduplicate()
        once = dwg.tostring()
        dwg.deduplicate()
        twice = dwg.tostring()
        dwg.deduplicate(min_occurrences=1)
        thrice = dwg.tostring()
        self.assertEqual(once, twice)
        self.assertEqual(once, thrice)

    def test_module_function_and_method_equivalent(self):
        dwg1 = self._drawing_with_three_icons()
        dwg2 = self._drawing_with_three_icons()
        dwg1.deduplicate()
        deduplicate(dwg2)
        self.assertEqual(dwg1.tostring(), dwg2.tostring())

    def test_returns_drawing(self):
        dwg = self._drawing_with_three_icons()
        self.assertIs(dwg.deduplicate(), dwg)


class TestEquivalenceRules(unittest.TestCase):
    def test_different_styles_are_separate_classes(self):
        dwg = Drawing()
        red = dwg.g(**{'style': 'fill:red'})
        red.add(dwg.rect(insert=(0, 0), size=(2, 2)))
        blue = dwg.g(**{'style': 'fill:blue'})
        blue.add(dwg.rect(insert=(0, 0), size=(2, 2)))
        red2 = dwg.g(**{'style': 'fill:red'})
        red2.add(dwg.rect(insert=(0, 0), size=(2, 2)))
        dwg.add(red); dwg.add(blue); dwg.add(red2)

        dwg.deduplicate()
        xml = dwg.tostring()
        self.assertEqual(xml.count('<symbol'), 1)
        self.assertEqual(xml.count('<use'), 2)
        # the differing blue instance stays inline
        self.assertIn('style="fill:blue"', xml)
        self.assertEqual(xml.count('style="fill:red"'), 2)

    def test_inner_transform_is_part_of_the_content(self):
        dwg = Drawing()
        for x, rotation in ((0, None), (30, 45)):
            group = dwg.g()
            group.translate(x, 0)
            inner = group.add(dwg.g())
            if rotation is not None:
                inner.rotate(rotation)
            inner.add(dwg.rect(insert=(0, 0), size=(4, 4)))
            dwg.add(group)
        before = dwg.tostring()
        dwg.deduplicate()
        xml = dwg.tostring()
        # the two outer groups differ in their inner transform and therefore
        # stay completely untouched
        self.assertIn('rotate(45)', xml)
        self.assertEqual(xml.count('<symbol'), 0)
        self.assertEqual(xml.count('<use'), 0)
        self.assertEqual(before, xml)

    def test_equivalent_nested_groups_merge_fully(self):
        dwg = Drawing()
        for x in (0, 30, 60):
            group = dwg.g()
            group.translate(x, 5)
            inner = group.add(dwg.g())
            inner.rotate(90)
            inner.add(dwg.rect(insert=(0, 0), size=(4, 4), fill='green'))
            dwg.add(group)
        dwg.deduplicate()
        xml = dwg.tostring()
        self.assertEqual(xml.count('<symbol'), 1)
        self.assertEqual(xml.count('<use'), 3)
        self.assertIn('rotate(90)', xml.split('</symbol>')[0])

    def test_title_difference_prevents_merge(self):
        dwg = Drawing()
        first = dwg.g()
        first.set_desc(title='A')
        first.add(dwg.rect(insert=(0, 0), size=(2, 2)))
        second = dwg.g()
        second.set_desc(title='B')
        second.add(dwg.rect(insert=(0, 0), size=(2, 2)))
        dwg.add(first); dwg.add(second)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_min_occurrences_threshold(self):
        dwg = Drawing()
        for _ in range(2):
            group = dwg.g()
            group.add(dwg.rect(insert=(0, 0), size=(3, 3)))
            dwg.add(group)
        before = dwg.tostring()
        dwg.deduplicate(min_occurrences=3)
        self.assertEqual(before, dwg.tostring())

    def test_sibling_order_preserved(self):
        dwg = Drawing()
        dwg.add(dwg.rect(insert=(0, 0), size=(50, 2), fill='yellow'))
        first = dwg.g()
        first.add(dwg.circle(center=(1, 1), r=1))
        dwg.add(first)
        dwg.add(dwg.text('x', insert=(0, 0)))
        second = dwg.g()
        second.add(dwg.circle(center=(1, 1), r=1))
        dwg.add(second)

        dwg.deduplicate()
        order = re.findall(r'<(rect|use|text)\b', dwg.tostring())
        self.assertEqual(order, ['rect', 'use', 'text', 'use'])


class TestSafetyGuards(unittest.TestCase):
    def _pair_of_groups(self, build):
        dwg = Drawing()
        dwg.add(build(dwg))
        dwg.add(build(dwg))
        return dwg

    def test_external_gradient_reference_skips_group(self):
        dwg = Drawing()
        dwg.defs.add(dwg.linearGradient(id='ext'))

        def build():
            group = dwg.g()
            group.add(dwg.rect(insert=(0, 0), size=(5, 5), fill='url(#ext)'))
            return group

        dwg.add(build()); dwg.add(build())
        before = dwg.tostring()
        self.assertIn('fill="url(#ext)"', before)
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_inbound_reference_skips_group(self):
        dwg = Drawing()
        first = dwg.g()
        first.add(dwg.linearGradient(id='shared'))
        first.add(dwg.rect(fill='url(#shared)', insert=(0, 0), size=(5, 5)))
        second = dwg.g()
        second.add(dwg.linearGradient(id='other'))
        second.add(dwg.rect(fill='url(#other)', insert=(0, 0), size=(5, 5)))
        dwg.add(first); dwg.add(second)
        # an element outside the groups references the inner gradient
        dwg.add(dwg.rect(fill='url(#shared)', insert=(9, 9), size=(2, 2)))
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_script_is_skipped(self):
        def build(dwg):
            group = dwg.g()
            group.add(dwg.script(content='alert(1)'))
            group.add(dwg.rect(insert=(0, 0), size=(3, 3)))
            return group
        dwg = self._pair_of_groups(build)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_external_image_is_skipped(self):
        def build(dwg):
            group = dwg.g()
            group.add(dwg.image('http://example.com/x.png',
                                insert=(0, 0), size=(3, 3)))
            return group
        dwg = self._pair_of_groups(build)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_data_uri_image_is_skipped(self):
        def build(dwg):
            group = dwg.g()
            group.add(dwg.image('data:image/png;base64,AAAA',
                                insert=(0, 0), size=(3, 3)))
            return group
        dwg = self._pair_of_groups(build)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_css_class_is_skipped(self):
        def build(dwg):
            group = dwg.g()
            group.add(dwg.rect(insert=(0, 0), size=(3, 3), **{'class': 'btn'}))
            return group
        dwg = self._pair_of_groups(build)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_hyperlink_is_skipped(self):
        def build(dwg):
            group = dwg.g()
            group.add(dwg.a('http://example.com'))
            return group
        dwg = self._pair_of_groups(build)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_animation_is_skipped(self):
        def build(dwg):
            group = dwg.g()
            rect = dwg.rect(insert=(0, 0), size=(3, 3))
            rect.add(dwg.animate('x', values='0;10', dur='5s'))
            group.add(rect)
            return group
        dwg = self._pair_of_groups(build)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_group_carrying_own_id_is_skipped(self):
        # the id might be targeted from outside the document (DOM/scripts);
        # without proof of safety the group stays untouched
        dwg = Drawing()
        first = dwg.g(id='myicon')
        first.add(dwg.path(d='M0,0 L1,1'))
        second = dwg.g()
        second.add(dwg.path(d='M0,0 L1,1'))
        dwg.add(first); dwg.add(second)
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())
        self.assertIn('id="myicon"', dwg.tostring())


class TestDefinitionsAndCompatibility(unittest.TestCase):
    def test_preexisting_defs_content_is_kept(self):
        dwg = Drawing()
        dwg.defs.add(dwg.linearGradient(id='preexisting'))
        first = dwg.g()
        first.add(dwg.path(d='M0,0 L1,1'))
        second = dwg.g()
        second.add(dwg.path(d='M0,0 L1,1'))
        dwg.add(first); dwg.add(second)
        dwg.deduplicate()
        xml = dwg.tostring()
        self.assertIn('id="preexisting"', xml)
        self.assertEqual(xml.count('<symbol'), 1)

    def test_nested_use_remains_valid_and_idempotent(self):
        dwg = Drawing()
        dwg.defs.add(dwg.rect(insert=(0, 0), size=(4, 4), id='tile'))
        for x in (0, 20):
            group = dwg.g()
            group.translate(x, 0)
            group.add(dwg.use('#tile'))
            dwg.add(group)
        dwg.deduplicate()
        once = dwg.tostring()
        ids, refs = ids_and_refs(once)
        self.assertTrue(all(ref in ids for ref in refs))
        self.assertIn('id="tile"', once)
        dwg.deduplicate()
        self.assertEqual(once, dwg.tostring())

    def test_serialization_unchanged_without_call(self):
        dwg = Drawing()
        for _ in range(3):
            group = dwg.g()
            group.add(dwg.rect(insert=(0, 0), size=(2, 2)))
            dwg.add(group)
        xml = dwg.tostring()
        self.assertNotIn('<symbol', xml)
        self.assertNotIn('<use', xml)

    def test_empty_drawing(self):
        dwg = Drawing()
        before = dwg.tostring()
        dwg.deduplicate()
        self.assertEqual(before, dwg.tostring())

    def test_tiny_profile(self):
        dwg = Drawing(profile='tiny')
        for _ in range(2):
            group = dwg.g()
            group.add(dwg.rect(insert=(0, 0), size=(2, 2)))
            dwg.add(group)
        dwg.deduplicate()
        xml = dwg.tostring()
        self.assertIn('baseProfile="tiny"', xml)
        # SVG Tiny has no <symbol>: a named <g> in defs is the template
        self.assertNotIn('<symbol', xml)
        self.assertEqual(xml.count('<use'), 2)
        ids, refs = ids_and_refs(xml)
        self.assertTrue(all(ref in ids for ref in refs))


if __name__ == '__main__':
    unittest.main()
