#!/usr/bin/env python
#coding:utf-8
# Purpose: test accessibility (ARIA) annotations
# License: MIT License

import unittest
import xml.etree.ElementTree as etree

import svgwrite
from svgwrite.accessibility import (
    AccessibilityError,
    VALID_ROLES,
    validate_accessibility,
)


def make_toolbar():
    """ Nested icon fixture: a toolbar group with two nested icon groups,
    each containing basic shapes.
    """
    dwg = svgwrite.Drawing('toolbar.svg', size=(64, 16))
    toolbar = dwg.add(dwg.g(id='toolbar'))
    save_icon = toolbar.add(dwg.g(id='save-icon'))
    save_icon.add(dwg.rect((1, 1), (14, 14)))
    save_icon.add(dwg.line((3, 8), (11, 8)))
    open_icon = toolbar.add(dwg.g(id='open-icon'))
    open_icon.add(dwg.circle((8, 8), 6))
    return dwg, toolbar, save_icon, open_icon


class TestAccessibleName(unittest.TestCase):
    def test_title_and_aria_reference(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', role='button')
        xml = save_icon.tostring()
        self.assertIn('<title id="save-icon-title">Save</title>', xml)
        self.assertIn('aria-labelledby="save-icon-title"', xml)
        self.assertIn('role="button"', xml)
        self.assertEqual(validate_accessibility(dwg), [])

    def test_desc_and_aria_reference(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', desc='Save the document')
        xml = save_icon.tostring()
        self.assertIn('<desc id="save-icon-desc">Save the document</desc>',
                      xml)
        self.assertIn('aria-describedby="save-icon-desc"', xml)
        self.assertEqual(validate_accessibility(dwg), [])

    def test_drawing_and_group_and_shape(self):
        # Drawing, Group and basic shapes all support the API
        dwg = svgwrite.Drawing('t.svg')
        dwg.set_accessible_name('Icon bar', role='toolbar')
        group = dwg.add(dwg.g())
        group.set_accessible_name('File actions')
        rect = group.add(dwg.rect((0, 0), (10, 10)))
        rect.set_accessible_name('Save icon', desc='Saves the file')
        self.assertEqual(dwg.get_accessible_name(), 'Icon bar')
        self.assertEqual(group.get_accessible_name(), 'File actions')
        self.assertEqual(rect.get_accessible_name(), 'Save icon')
        self.assertEqual(rect.get_accessible_description(), 'Saves the file')
        self.assertEqual(validate_accessibility(dwg), [])

    def test_reading_order_title_before_desc_before_shapes(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', desc='Save the document')
        names = [child.tag for child in save_icon.get_xml()]
        self.assertEqual(names[:2], ['title', 'desc'])
        self.assertEqual(names[2:], ['rect', 'line'])

    def test_desc_added_after_shapes_is_inserted_up_front(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_description('Save the document')
        names = [child.tag for child in save_icon.get_xml()]
        self.assertEqual(names[0], 'desc')

    def test_empty_name_raises(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        self.assertRaises(ValueError, save_icon.set_accessible_name, '')
        self.assertRaises(ValueError, save_icon.set_accessible_name, '   ')

    def test_invalid_role_raises(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        self.assertRaises(ValueError, save_icon.set_accessible_name,
                          'Save', role='not-a-role')
        self.assertNotIn('role', save_icon.attribs)

    def test_all_valid_roles_accepted(self):
        for role in VALID_ROLES:
            icon = svgwrite.Drawing('t.svg').g()
            icon.set_accessible_name('x', role=role)
            self.assertEqual(icon.attribs['role'], role)


class TestRepeatedUpdates(unittest.TestCase):
    """ Repeated-update fixture: annotating the same element twice must not
    create duplicate nodes or conflicting IDs.
    """
    def test_no_duplicate_title_nodes(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save')
        save_icon.set_accessible_name('Save as')
        titles = [e for e in save_icon.get_xml() if e.tag == 'title']
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].text, 'Save as')
        self.assertEqual(titles[0].get('id'), 'save-icon-title')

    def test_stable_ids_and_references(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', desc='Save the document')
        before = (save_icon.attribs['aria-labelledby'],
                  save_icon.attribs['aria-describedby'])
        save_icon.set_accessible_name('Save as', desc='Save with a new name')
        after = (save_icon.attribs['aria-labelledby'],
                 save_icon.attribs['aria-describedby'])
        self.assertEqual(before, after)
        self.assertEqual(validate_accessibility(dwg), [])

    def test_partial_update_keeps_other_annotations(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', desc='Save the document',
                                      role='button')
        save_icon.set_accessible_name('Save as')
        self.assertEqual(save_icon.get_accessible_description(),
                         'Save the document')
        self.assertEqual(save_icon.attribs['role'], 'button')

    def test_empty_desc_removes_description(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', desc='Save the document')
        save_icon.set_accessible_name('Save', desc='')
        self.assertIsNone(save_icon.get_accessible_description())
        self.assertNotIn('aria-describedby', save_icon.attribs)
        # name is untouched
        self.assertEqual(save_icon.get_accessible_name(), 'Save')

    def test_clear_accessibility(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_accessible_name('Save', desc='Save the document',
                                      role='button')
        save_icon.clear_accessibility()
        self.assertIsNone(save_icon.get_accessible_name())
        self.assertNotIn('aria-labelledby', save_icon.attribs)
        self.assertNotIn('aria-describedby', save_icon.attribs)
        self.assertNotIn('role', save_icon.attribs)
        self.assertEqual(validate_accessibility(dwg), [])


class TestHandWrittenDescriptions(unittest.TestCase):
    def test_adopt_handwritten_title(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_desc(title='Save')  # hand-written, no id
        save_icon.set_accessible_name('Save file')
        titles = [e for e in save_icon.get_xml() if e.tag == 'title']
        self.assertEqual(len(titles), 1)  # adopted, not duplicated
        self.assertEqual(titles[0].text, 'Save file')
        self.assertEqual(titles[0].get('id'), 'save-icon-title')
        self.assertEqual(save_icon.attribs['aria-labelledby'],
                         'save-icon-title')

    def test_strict_mode_rejects_handwritten_title(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_desc(title='Save')
        self.assertRaises(AccessibilityError,
                          save_icon.set_accessible_name, 'Save', strict=True)

    def test_strict_mode_rejects_handwritten_desc(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_desc(desc='Save the document')
        self.assertRaises(AccessibilityError,
                          save_icon.set_accessible_name, 'Save',
                          desc='new desc', strict=True)

    def test_clear_keeps_handwritten_nodes(self):
        dwg, toolbar, save_icon, _ = make_toolbar()
        save_icon.set_desc(title='Handwritten')
        save_icon['aria-labelledby'] = 'external-label'
        save_icon.clear_accessibility()
        # hand-written title has no generated id -> kept
        self.assertEqual(save_icon.get_accessible_name(), 'Handwritten')
        # but the dangling hand-set reference is removed
        self.assertNotIn('aria-labelledby', save_icon.attribs)


class TestNestedGroups(unittest.TestCase):
    def test_child_name_overrides_group_context(self):
        dwg, toolbar, save_icon, open_icon = make_toolbar()
        toolbar.set_accessible_name('Toolbar', role='toolbar')
        save_icon.set_accessible_name('Save', role='button')
        # open_icon has no own name -> covered by the group's name
        self.assertEqual(toolbar.get_accessible_name(), 'Toolbar')
        self.assertEqual(save_icon.get_accessible_name(), 'Save')
        self.assertIsNone(open_icon.get_accessible_name())
        self.assertEqual(validate_accessibility(dwg), [])

    def test_language_inherit(self):
        dwg, toolbar, save_icon, open_icon = make_toolbar()
        dwg.apply_language('en')
        self.assertEqual(dwg.attribs['xml:lang'], 'en')
        self.assertEqual(toolbar.attribs['xml:lang'], 'en')
        self.assertEqual(save_icon.attribs['xml:lang'], 'en')

    def test_language_explicit_override_wins_on_inherit(self):
        dwg, toolbar, save_icon, open_icon = make_toolbar()
        save_icon.set_accessible_name('Speichern', lang='de')
        dwg.apply_language('en')  # inherit: does not touch explicit 'de'
        self.assertEqual(save_icon.attribs['xml:lang'], 'de')
        self.assertEqual(open_icon.attribs['xml:lang'], 'en')

    def test_language_override_replaces_explicit(self):
        dwg, toolbar, save_icon, open_icon = make_toolbar()
        save_icon.set_accessible_name('Speichern', lang='de')
        dwg.apply_language('en', override=True)
        self.assertEqual(save_icon.attribs['xml:lang'], 'en')


class TestValidateAccessibility(unittest.TestCase):
    def test_duplicate_id(self):
        dwg = svgwrite.Drawing('t.svg')
        dwg.add(dwg.g(id='dup'))
        dwg.add(dwg.g(id='dup'))
        issues = validate_accessibility(dwg)
        self.assertTrue(any('duplicate id' in i for i in issues))

    def test_duplicate_id_strict_raises(self):
        dwg = svgwrite.Drawing('t.svg')
        dwg.add(dwg.g(id='dup'))
        dwg.add(dwg.g(id='dup'))
        self.assertRaises(AccessibilityError, validate_accessibility,
                          dwg, strict=True)

    def test_dangling_reference(self):
        dwg = svgwrite.Drawing('t.svg')
        icon = dwg.add(dwg.g())
        icon['aria-labelledby'] = 'no-such-id'
        issues = validate_accessibility(dwg)
        self.assertTrue(any('dangling reference' in i for i in issues))

    def test_dangling_reference_strict_raises(self):
        dwg = svgwrite.Drawing('t.svg')
        icon = dwg.add(dwg.g())
        icon['aria-labelledby'] = 'no-such-id'
        self.assertRaises(AccessibilityError, validate_accessibility,
                          dwg, strict=True)

    def test_invalid_role_detected(self):
        dwg = svgwrite.Drawing('t.svg')
        icon = dwg.add(dwg.g())
        icon.attribs['role'] = 'bogus'  # bypasses API validation
        issues = validate_accessibility(dwg)
        self.assertTrue(any('invalid role' in i for i in issues))

    def test_bad_reading_order_detected(self):
        dwg = svgwrite.Drawing('t.svg')
        icon = dwg.add(dwg.g())
        icon.set_desc(desc='desc first')
        icon.set_desc(title='title second')  # inserted before desc? no:
        # set_desc inserts title at position 0, so force bad order manually
        icon.elements.append(icon.elements.pop(0))  # title after desc
        issues = validate_accessibility(dwg)
        self.assertTrue(any('reading order' in i for i in issues))

    def test_valid_tree_has_no_issues(self):
        dwg, toolbar, save_icon, open_icon = make_toolbar()
        toolbar.set_accessible_name('Toolbar', role='toolbar', lang='en')
        save_icon.set_accessible_name('Save', desc='Save the document',
                                      role='button')
        open_icon.set_accessible_name('Open', role='button')
        self.assertEqual(validate_accessibility(dwg), [])

    def test_package_level_exports(self):
        self.assertIs(svgwrite.validate_accessibility, validate_accessibility)
        self.assertIs(svgwrite.AccessibilityError, AccessibilityError)
        self.assertIs(svgwrite.VALID_ROLES, VALID_ROLES)


class TestDebugMode(unittest.TestCase):
    """ aria-* and role attributes are not part of the SVG profile
    attribute lists; the API must work with validation (debug) enabled.
    """
    def test_debug_mode_full_profile(self):
        dwg = svgwrite.Drawing('t.svg', debug=True, profile='full')
        icon = dwg.add(dwg.g(id='icon'))
        icon.set_accessible_name('Save', role='button', lang='en')
        xml = dwg.tostring()  # get_xml validates all attributes
        self.assertIn('aria-labelledby="icon-title"', xml)

    def test_debug_mode_tiny_profile(self):
        dwg = svgwrite.Drawing('t.svg', debug=True, profile='tiny')
        icon = dwg.add(dwg.g(id='icon'))
        icon.set_accessible_name('Save', desc='Save the document')
        xml = dwg.tostring()
        self.assertIn('aria-describedby="icon-desc"', xml)


if __name__ == '__main__':
    unittest.main()
