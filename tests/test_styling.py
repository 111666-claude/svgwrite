#!/usr/bin/env python
#coding:utf-8
# Author:  mozman
# Purpose: test shared style registry
# Created: 18.11.2026
# Copyright (c) 2026, Manfred Moitzi
# License: MIT License

import unittest

import svgwrite
from svgwrite.drawing import Drawing
from svgwrite.styling import StyleRegistry, sync_inline_styles
from svgwrite.styling import normalize_property_name
from svgwrite.container import Style as ContainerStyle
from svgwrite.base import BaseElement
from svgwrite.mixins import Presentation


class Shape(BaseElement, Presentation):
    elementname = 'rect'


class TestStyleRegistryCore(unittest.TestCase):
    def test_register_returns_stable_name_and_dedupes(self):
        registry = StyleRegistry()
        name1 = registry.register({'fill': 'red', 'stroke': 'black'})
        name2 = registry.register({'stroke': 'black', 'fill': 'red'})
        self.assertEqual(name1, name2)
        self.assertEqual(registry.classes(), [name1])
        self.assertEqual(len(registry.rules()), 1)

    def test_distinct_styles_get_distinct_classes(self):
        registry = StyleRegistry()
        n1 = registry.register({'fill': 'red'})
        n2 = registry.register({'fill': 'blue'})
        n3 = registry.register({'fill': 'red', 'stroke': 'black'})
        self.assertEqual(len({n1, n2, n3}), 3)
        self.assertEqual(registry.classes(), [n1, n2, n3])

    def test_keyword_arguments_and_underscore_names(self):
        registry = StyleRegistry()
        name = registry.register(stroke_width=2, fill_opacity=0.5)
        style = dict(registry.rules()[0][1])
        self.assertEqual(style, {'stroke-width': '2', 'fill-opacity': '0.5'})
        self.assertEqual(
            normalize_property_name('stroke_width_'), 'stroke-width')

    def test_register_css_string(self):
        registry = StyleRegistry()
        name = registry.register_css('fill: red; stroke: black')
        self.assertEqual(
            dict(registry.rules()[0][1]),
            {'fill': 'red', 'stroke': 'black'})

    def test_css_text_order_is_stable(self):
        registry = StyleRegistry()
        registry.register({'stroke': 'black', 'fill': 'red'})
        registry.register({'fill': 'blue'})
        text = registry.get_css_text()
        self.assertEqual(text,
                         '.sw-style-0 {fill: red; stroke: black;}\n'
                         '.sw-style-1 {fill: blue;}')
        # deterministic across an equivalent second registry
        other = StyleRegistry()
        other.register({'fill': 'red', 'stroke': 'black'})
        other.register({'fill': 'blue'})
        self.assertEqual(other.get_css_text(), text)

    def test_empty_style_rejected(self):
        registry = StyleRegistry()
        with self.assertRaises(ValueError):
            registry.register({})
        with self.assertRaises(ValueError):
            registry.register_css('   ')
        with self.assertRaises(ValueError):
            registry.register_css(';;;')

    def test_unsupported_property_rejected(self):
        registry = StyleRegistry()
        with self.assertRaises(ValueError):
            registry.register({'not-a-property': 'red'})
        with self.assertRaises(ValueError):
            registry.register_css('bogus: red')

    def test_malformed_css_declaration_rejected(self):
        registry = StyleRegistry()
        with self.assertRaises(ValueError):
            registry.register_css('fill red')
        with self.assertRaises(ValueError):
            registry.register_css(': red')
        with self.assertRaises(ValueError):
            registry.register_css('fill:')

    def test_invalid_value_rejected_in_debug_mode(self):
        registry = StyleRegistry(debug=True)
        with self.assertRaises(TypeError):
            registry.register({'stroke-width': 'not-a-number'})
        with self.assertRaises(TypeError):
            registry.register({'fill': 123})

    def test_invalid_value_skipped_without_debug(self):
        registry = StyleRegistry(debug=False)
        # only the property whitelist and CSS safety checks remain
        name = registry.register({'stroke-width': 'not-a-number'})
        self.assertIn('stroke-width: not-a-number',
                      registry.get_css_text())
        self.assertTrue(name)

    def test_none_and_empty_values_rejected(self):
        registry = StyleRegistry()
        with self.assertRaises(ValueError):
            registry.register({'fill': None})
        with self.assertRaises(ValueError):
            registry.register({'fill': ''})

    def test_css_injection_attempts_rejected(self):
        registry = StyleRegistry()
        for bad in ('red; } .evil {fill: green', 'red{', 'red}',
                    'red]]>blue'):
            with self.assertRaises(ValueError):
                registry.register({'fill': bad})

    def test_tiny_profile_property_set(self):
        registry = StyleRegistry(profile='tiny')
        with self.assertRaises(ValueError):
            # writing-mode is a full-profile presentation property only
            registry.register({'writing-mode': 'lr-tb'})
        name = registry.register({'fill': 'red', 'stroke-width': 1})
        self.assertTrue(name)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            StyleRegistry(profile='bogus')


class TestCustomNamesAndConflicts(unittest.TestCase):
    def test_custom_name_is_used(self):
        registry = StyleRegistry()
        name = registry.register({'fill': 'red'}, name='marker')
        self.assertEqual(name, 'marker')
        self.assertEqual(
            registry.get_css_text(), '.marker {fill: red;}')

    def test_invalid_custom_name_rejected(self):
        registry = StyleRegistry()
        for bad in ('1abc', '-abc', '', 'a b', '.abc', 'a;b'):
            with self.assertRaises(ValueError):
                registry.register({'fill': 'red'}, name=bad)

    def test_custom_name_same_properties_is_idempotent(self):
        registry = StyleRegistry()
        n1 = registry.register({'fill': 'red'}, name='marker')
        n2 = registry.register({'fill': 'red'}, name='marker')
        self.assertEqual(n1, n2)
        self.assertEqual(registry.classes(), ['marker'])

    def test_custom_name_conflicting_properties_rejected(self):
        registry = StyleRegistry()
        registry.register({'fill': 'red'}, name='marker')
        with self.assertRaises(ValueError):
            registry.register({'fill': 'blue'}, name='marker')

    def test_auto_names_skip_custom_names(self):
        registry = StyleRegistry()
        registry.register({'fill': 'red'}, name='sw-style-0')
        name = registry.register({'fill': 'blue'})
        self.assertNotEqual(name, 'sw-style-0')
        self.assertEqual(name, 'sw-style-1')

    def test_attach_unknown_class_raises(self):
        registry = StyleRegistry()
        element = Shape()
        with self.assertRaises(KeyError):
            registry.attach(element, 'never-registered')


class TestAttachAndOverrides(unittest.TestCase):
    def setUp(self):
        self.registry = StyleRegistry()
        self.marker = self.registry.register(
            {'fill': 'red', 'stroke': 'black'})

    def test_attach_sets_class_attribute(self):
        element = Shape()
        self.registry.attach(element, self.marker)
        self.assertEqual(element['class'], self.marker)

    def test_user_classes_are_preserved(self):
        element = Shape(class_='user-a user-b')
        self.registry.attach(element, self.marker)
        self.assertEqual(
            element['class'].split(),
            ['user-a', 'user-b', self.marker])

    def test_attach_is_idempotent(self):
        element = Shape(class_='user-a')
        self.registry.attach(element, self.marker)
        self.registry.attach(element, self.marker)
        self.assertEqual(
            element['class'].split(), ['user-a', self.marker])

    def test_local_presentation_attribute_overrides_class(self):
        # presentation attributes have lower CSS priority than author CSS,
        # so the local value must be promoted to the inline style attribute
        element = Shape(fill='green')
        self.registry.attach(element, self.marker)
        self.assertNotIn('fill', element.attribs)
        xml = element.tostring()
        self.assertIn('class="%s"' % self.marker, xml)
        self.assertIn('style="fill: green"', xml)
        self.assertNotIn('fill="green"', xml)

    def test_non_colliding_attributes_remain_attributes(self):
        element = Shape(fill='green', opacity=0.7)
        self.registry.attach(element, self.marker)
        xml = element.tostring()
        self.assertIn('opacity="0.7"', xml)
        self.assertIn('style="fill: green"', xml)

    def test_existing_inline_style_keeps_priority(self):
        element = Shape(style='fill: navy', fill='green')
        self.registry.attach(element, self.marker)
        xml = element.tostring()
        # the inline style wins and the presentation attr is dropped
        self.assertIn('style="fill: navy"', xml)
        self.assertNotIn('fill=', xml.replace('style="fill: navy"', ''))

    def test_attribute_set_after_attach_is_promoted_on_serialization(self):
        element = Shape()
        self.registry.attach(element, self.marker)
        element['fill'] = 'green'
        sync_inline_styles(element)
        self.assertNotIn('fill', element.attribs)
        self.assertEqual(element.attribs['style'], 'fill: green')

    def test_multiple_classes_and_registries(self):
        other = StyleRegistry()
        # distinct explicit name: CSS classes share one global namespace, so
        # classes attached from different registries need distinct names
        extra = other.register({'opacity': '0.5'}, name='extra')
        element = Shape()
        self.registry.attach(element, self.marker)
        other.attach(element, extra)
        self.assertEqual(
            element['class'].split(), [self.marker, extra])
        xml = element.tostring()
        self.assertIn('class="%s %s"' % (self.marker, extra), xml)

    def test_same_named_class_from_two_registries_is_not_duplicated(self):
        other = StyleRegistry()
        other.register({'opacity': '0.5'})  # also mints 'sw-style-0'
        element = Shape()
        self.registry.attach(element, self.marker)
        other.attach(element, 'sw-style-0')
        # the existing token is kept, no duplicate class names
        self.assertEqual(element['class'].split(), [self.marker])
        # properties of both registries participate in override handling
        element['opacity'] = '0.9'
        sync_inline_styles(element)
        self.assertEqual(element.attribs['style'], 'opacity: 0.9')

    def test_attach_accepts_iterable_of_names(self):
        extra = self.registry.register({'opacity': '0.5'})
        element = Shape()
        self.registry.attach(element, [self.marker, extra])
        self.assertEqual(
            element['class'].split(), [self.marker, extra])


class TestDrawingIntegration(unittest.TestCase):
    def test_unused_registry_leaves_output_unchanged(self):
        dwg = Drawing()
        # touching the registry property but registering nothing
        self.assertIsInstance(dwg.style_registry, StyleRegistry)
        self.assertNotIn('<style', dwg.tostring())

    def test_style_element_lands_in_defs_and_escapes(self):
        dwg = Drawing()
        registry = dwg.style_registry
        name = registry.register({'fill': 'red', 'stroke': 'black'})
        rect = dwg.rect(insert=(0, 0), size=(2, 2))
        registry.attach(rect, name)
        dwg.add(rect)
        result = dwg.tostring()
        self.assertIn(
            '<defs><style type="text/css"><![CDATA['
            '.%s {fill: red; stroke: black;}]]></style></defs>' % name,
            result)
        self.assertIn('<rect class="%s"' % name, result)

    def test_xml_escaping_of_class_attribute(self):
        dwg = Drawing()
        registry = dwg.style_registry
        name = registry.register({'fill': 'red'})
        rect = dwg.rect(insert=(0, 0), size=(2, 2),
                        class_='a&b <c> "d"')
        registry.attach(rect, name)
        dwg.add(rect)
        result = dwg.tostring()
        self.assertIn('class="a&amp;b &lt;c&gt; &quot;d&quot; %s"' % name,
                      result)

    def test_pretty_output_still_parses(self):
        import xml.etree.ElementTree as ET
        dwg = Drawing()
        registry = dwg.style_registry
        name = registry.register({'fill': 'red'})
        rect = dwg.rect(insert=(0, 0), size=(2, 2), fill='green')
        registry.attach(rect, name)
        dwg.add(rect)
        from io import StringIO
        buf = StringIO()
        dwg.write(buf, pretty=True)
        # well-formed XML incl. the CDATA style block
        root = ET.fromstring(buf.getvalue().split('\n', 1)[1])
        self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')

    def test_drawing_profile_is_used(self):
        dwg = Drawing(profile='tiny')
        registry = dwg.style_registry
        self.assertEqual(registry.profile, 'tiny')
        with self.assertRaises(ValueError):
            registry.register({'writing-mode': 'lr'})

    def test_tiny_debug_mode_rejects_css_emission(self):
        # SVG Tiny 1.2 has no <style> element / CSS support
        dwg = Drawing(profile='tiny')  # debug defaults to True
        with self.assertRaises(ValueError):
            dwg.style_registry.register({'fill': 'red'})

    def test_tiny_non_debug_mode_emits_anyway(self):
        dwg = Drawing(profile='tiny', debug=False)
        registry = dwg.style_registry
        name = registry.register({'fill': 'red'})
        rect = dwg.rect(insert=(0, 0), size=(1, 1))
        registry.attach(rect, name)
        dwg.add(rect)
        result = dwg.tostring()
        self.assertIn('<style type="text/css">', result)
        self.assertIn('class="%s"' % name, result)

    def test_manual_embedded_stylesheet_coexists(self):
        dwg = Drawing()
        dwg.embed_stylesheet('.manual {stroke: green;}')
        registry = dwg.style_registry
        name = registry.register({'fill': 'red'})
        result = dwg.tostring()
        self.assertIn('.manual {stroke: green;}', result)
        self.assertIn('.%s {fill: red;}' % name, result)
        # two distinct <style> elements inside defs
        style_elements = [e for e in dwg.defs.elements
                          if e.elementname == 'style']
        self.assertEqual(len(style_elements), 2)
        self.assertIsInstance(style_elements[0], ContainerStyle)


class TestRepeatedShapesScenario(unittest.TestCase):
    """ The original use case: thousands of same-colored markers must share
    one rule, and local overrides must keep working. """

    def test_many_rects_and_paths_share_rules(self):
        dwg = Drawing()
        registry = dwg.style_registry
        marker = registry.register(
            {'fill': '#2266aa', 'stroke': '#111111', 'stroke-width': '1.5'})
        special = registry.register({'fill': '#aa2266'})
        self.assertEqual(len(registry.rules()), 2)

        for index in range(200):
            rect = dwg.rect(insert=(index, 0), size=(1, 1))
            registry.attach(rect, marker)
            dwg.add(rect)
        for index in range(50):
            path = dwg.path('M0 0 L1 1')
            registry.attach(path, marker)
            if index % 10 == 0:
                path['fill'] = '#aa2266'
                registry.attach(path, special)
            dwg.add(path)

        result = dwg.tostring()
        import re
        class_lists = re.findall(r'class="([^"]*)"', result)
        # exactly two CSS rules
        self.assertEqual(result.count('{'), 2)
        # all 250 shapes reference the marker rule
        marker_refs = sum(marker in tokens.split()
                          for tokens in class_lists)
        self.assertEqual(marker_refs, 250)
        # the five special paths reference the special rule too
        special_refs = sum(special in tokens.split()
                           for tokens in class_lists)
        self.assertEqual(special_refs, 5)
        self.assertEqual(result.count('.%s {' % special), 1)  # one rule
        # overridden paths carry an inline style instead of a fill attribute
        self.assertEqual(result.count('style="fill: #aa2266"'), 5)
        # the repeated fill/stroke attributes no longer bloat the elements
        self.assertNotIn('fill="#2266aa"', result)
        self.assertNotIn('stroke="#111111"', result)
        # deterministic output on a second, equivalently built drawing
        dwg2 = Drawing()
        r2 = dwg2.style_registry
        m2 = r2.register(
            {'fill': '#2266aa', 'stroke': '#111111', 'stroke-width': '1.5'})
        s2 = r2.register({'fill': '#aa2266'})
        self.assertEqual((m2, s2), (marker, special))
        self.assertEqual(r2.get_css_text(), registry.get_css_text())


if __name__ == '__main__':
    unittest.main()
