#!/usr/bin/env python
#coding:utf-8
# Purpose: test objectBoundingBox clipPath construction
# License: MIT License

import unittest
import xml.etree.ElementTree as ET

import svgwrite
from svgwrite.masking import (
    ClipPath,
    apply_clip_path,
    normalize_path_data,
    object_bounding_box_clip,
)
from svgwrite.path import Path

# a cloud shaped icon outline (absolute commands only)
CLOUD_PATH = (
    "M 30 70 "
    "C 15 70 10 55 20 48 "
    "C 15 35 30 28 38 35 "
    "C 42 22 62 22 66 34 "
    "C 80 32 88 44 82 54 "
    "C 90 60 84 70 74 70 "
    "L 30 70 "
    "Z"
)
CLOUD_BOUNDS = (10, 20, 80, 50)  # x, y, width, height


def expected_norm_x(x):
    return (x - CLOUD_BOUNDS[0]) / float(CLOUD_BOUNDS[2])


def expected_norm_y(y):
    return (y - CLOUD_BOUNDS[1]) / float(CLOUD_BOUNDS[3])


class TestNormalizePathData(unittest.TestCase):
    def test_simple_rect_normalization(self):
        d = normalize_path_data("M 10 20 L 90 20 L 90 70 L 10 70 Z",
                                (10, 20, 80, 50))
        self.assertEqual(d, "M 0 0 L 1 0 L 1 1 L 0 1 Z")

    def test_partial_coordinates(self):
        d = normalize_path_data("M 50 45 L 90 70", (10, 20, 80, 50))
        self.assertEqual(d, "M 0.5 0.5 L 1 1")

    def test_horizontal_vertical_commands(self):
        d = normalize_path_data("M 10 20 H 90 V 70", (10, 20, 80, 50))
        self.assertEqual(d, "M 0 0 H 1 V 1")

    def test_curve_commands(self):
        d = normalize_path_data(
            "M 10 20 C 10 20 90 20 90 70 S 90 70 10 70 Q 50 45 10 20 T 10 20",
            (10, 20, 80, 50))
        self.assertEqual(
            d, "M 0 0 C 0 0 1 0 1 1 S 1 1 0 1 Q 0.5 0.5 0 0 T 0 0")

    def test_arc_command(self):
        d = normalize_path_data("M 10 20 A 40 25 30 0 1 90 70",
                                (10, 20, 80, 50))
        self.assertEqual(d, "M 0 0 A 0.5 0.5 30 0 1 1 1")

    def test_implicit_lineto_after_moveto(self):
        d = normalize_path_data("M 10 20 90 20 90 70", (10, 20, 80, 50))
        self.assertEqual(d, "M 0 0 L 1 0 L 1 1")

    def test_compact_syntax_and_scientific_notation(self):
        d = normalize_path_data("M10,20L9e1,2e1", (10, 20, 80, 50))
        self.assertEqual(d, "M 0 0 L 1 0")


class TestNormalizePathDataErrors(unittest.TestCase):
    def test_zero_width_bounds(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L 1 1", (10, 20, 0, 50))

    def test_zero_height_bounds(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L 1 1", (10, 20, 80, 0))

    def test_negative_size_bounds(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L 1 1", (10, 20, -80, 50))
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L 1 1", (10, 20, 80, -50))

    def test_negative_coordinate_bounds(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L 1 1", (-10, 20, 80, 50))
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L 1 1", (10, -20, 80, 50))

    def test_malformed_bounds(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0", (10, 20, 80))
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0", None)

    def test_relative_commands_not_supported(self):
        with self.assertRaises(ValueError):
            normalize_path_data("m 10 20 l 80 50", (10, 20, 80, 50))

    def test_invalid_path_data(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 L foo", (10, 20, 80, 50))
        with self.assertRaises(ValueError):
            normalize_path_data("M 0 0 @ 1 1", (10, 20, 80, 50))
        with self.assertRaises(ValueError):
            normalize_path_data("", (10, 20, 80, 50))
        with self.assertRaises(ValueError):
            normalize_path_data("10 20 L 1 1", (10, 20, 80, 50))
        with self.assertRaises(ValueError):
            normalize_path_data("M 0", (10, 20, 80, 50))

    def test_invalid_arc_flags(self):
        with self.assertRaises(ValueError):
            normalize_path_data("M 10 20 A 40 25 30 2 1 90 70",
                                (10, 20, 80, 50))


class TestObjectBoundingBoxClip(unittest.TestCase):
    def test_clip_path_structure(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        clip = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS)
        self.assertIsInstance(clip, ClipPath)
        self.assertEqual(clip['clipPathUnits'], 'objectBoundingBox')
        # no transform on the generated clipPath: normalization is baked
        # into the coordinates
        self.assertNotIn('transform', clip.attribs)
        self.assertIn(clip, dwg.defs.elements)
        # exactly one child path with normalized coordinates
        self.assertEqual(len(clip.elements), 1)
        d = clip.elements[0].commands[0]
        self.assertTrue(d.startswith("M %s" % _fmt(expected_norm_x(30))))
        self.assertIn(_fmt(expected_norm_y(70)), d)

    def test_clip_path_xml(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        clip = object_bounding_box_clip(dwg, "M 10 20 L 90 20 L 90 70 Z",
                                        CLOUD_BOUNDS, id='cloud-clip')
        xml = clip.tostring()
        self.assertEqual(
            xml,
            '<clipPath clipPathUnits="objectBoundingBox" id="cloud-clip">'
            '<path d="M 0 0 L 1 0 L 1 1 Z" />'
            '</clipPath>')

    def test_apply_to_rect_image_group(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        clip = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS)
        rect = dwg.rect(insert=(10, 20), size=(80, 50))
        image = dwg.image("icon.png", insert=(10, 20), size=(80, 50))
        group = dwg.g()
        for element in (rect, image, group):
            apply_clip_path(element, clip)
            dwg.add(element)
            self.assertEqual(element['clip-path'],
                             "url(#%s)" % clip.get_id())
        # the whole drawing must be parseable, valid XML
        ET.fromstring(dwg.tostring())

    def test_repeated_application_does_not_duplicate(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        clip1 = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS)
        clip2 = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS)
        self.assertIs(clip1, clip2)
        clips = [e for e in dwg.defs.elements if isinstance(e, ClipPath)]
        self.assertEqual(len(clips), 1)

    def test_same_normalized_result_is_shared(self):
        # different absolute paths that normalize to the same shape share
        # one clipPath definition
        dwg = svgwrite.Drawing(size=(100, 100))
        clip1 = object_bounding_box_clip(
            dwg, "M 10 20 L 90 20 L 90 70 Z", (10, 20, 80, 50))
        clip2 = object_bounding_box_clip(
            dwg, "M 0 0 L 200 0 L 200 100 Z", (0, 0, 200, 100))
        self.assertIs(clip1, clip2)
        clips = [e for e in dwg.defs.elements if isinstance(e, ClipPath)]
        self.assertEqual(len(clips), 1)

    def test_source_path_object_is_not_modified(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        path = Path(d=CLOUD_PATH)
        commands_before = list(path.commands)
        attribs_before = dict(path.attribs)
        object_bounding_box_clip(dwg, path, CLOUD_BOUNDS)
        self.assertEqual(path.commands, commands_before)
        self.assertEqual(path.attribs, attribs_before)

    def test_path_object_with_transform_raises(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        path = Path(d=CLOUD_PATH)
        path.translate(5, 5)
        with self.assertRaises(ValueError):
            object_bounding_box_clip(dwg, path, CLOUD_BOUNDS)

    def test_duplicate_id_raises(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS, id='cloud')
        # same id but a different shape
        with self.assertRaises(ValueError):
            object_bounding_box_clip(
                dwg, "M 10 20 L 90 70 Z", CLOUD_BOUNDS, id='cloud')
        # id already used by another defs element
        dwg.defs.add(svgwrite.shapes.Circle(id='other'))
        with self.assertRaises(ValueError):
            object_bounding_box_clip(
                dwg, "M 10 20 L 90 70 Z", CLOUD_BOUNDS, id='other')

    def test_same_id_same_clip_is_stable(self):
        dwg = svgwrite.Drawing(size=(100, 100))
        clip1 = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS,
                                         id='cloud')
        clip2 = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS,
                                         id='cloud')
        self.assertIs(clip1, clip2)
        self.assertEqual(clip1.get_id(), 'cloud')

    def test_apply_clip_path_type_check(self):
        with self.assertRaises(TypeError):
            apply_clip_path(svgwrite.shapes.Rect(), "not-a-clip-path")


class TestTwoCanvasSizesAndRotatedTargets(unittest.TestCase):
    """ The same cloud clip is reused across two canvas sizes and rotated
    targets; the normalized XML coordinates and references must be stable.
    """

    def build_drawing(self, size, rotated):
        dwg = svgwrite.Drawing(size=size)
        clip = object_bounding_box_clip(dwg, CLOUD_PATH, CLOUD_BOUNDS,
                                        id='cloud-clip')
        rect = apply_clip_path(
            dwg.rect(insert=CLOUD_BOUNDS[:2], size=CLOUD_BOUNDS[2:]), clip)
        image = apply_clip_path(
            dwg.image("cloud.png", insert=CLOUD_BOUNDS[:2],
                      size=CLOUD_BOUNDS[2:]), clip)
        group = dwg.g()
        if rotated:
            group.rotate(45, center=(50, 45))
        group.add(apply_clip_path(
            dwg.rect(insert=CLOUD_BOUNDS[:2], size=CLOUD_BOUNDS[2:]), clip))
        for element in (rect, image, group):
            dwg.add(element)
        return dwg, clip

    def check_drawing(self, dwg, clip, rotated):
        xml = dwg.tostring()
        root = ET.fromstring(xml)  # must be valid XML
        ns = '{http://www.w3.org/2000/svg}'
        # exactly one clipPath definition, independent of canvas size
        clips = root.findall('.//%sclipPath' % ns)
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0].get('clipPathUnits'), 'objectBoundingBox')
        self.assertEqual(clips[0].get('id'), 'cloud-clip')
        # normalized coordinates of the cloud outline
        d = clips[0].find('%spath' % ns).get('d')
        commands = d.split()
        self.assertEqual(commands[0], 'M')
        self.assertEqual(float(commands[1]),
                         round(expected_norm_x(30), 6))
        self.assertEqual(float(commands[2]),
                         round(expected_norm_y(70), 6))
        # all cubic control points are normalized into target space
        self.assertIn('C', commands)
        c_index = commands.index('C')
        self.assertEqual(float(commands[c_index + 1]),
                         round(expected_norm_x(15), 6))
        self.assertEqual(float(commands[c_index + 2]),
                         round(expected_norm_y(70), 6))
        # every rect, image and group references the same clip
        reference = 'url(#cloud-clip)'
        for tag in ('rect', 'image'):
            for element in root.findall('.//%s%s' % (ns, tag)):
                self.assertEqual(element.get('clip-path'), reference)
        groups = root.findall('.//%sg' % ns)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        if rotated:
            self.assertEqual(group.get('transform'), 'rotate(45,50,45)')
        else:
            self.assertIsNone(group.get('transform'))
        # the rotated target inside the group still references the clip
        inner_rect = group.find('%srect' % ns)
        self.assertEqual(inner_rect.get('clip-path'), reference)
        return d

    def test_canvas_100x100(self):
        dwg, clip = self.build_drawing((100, 100), rotated=False)
        self.check_drawing(dwg, clip, rotated=False)

    def test_canvas_400x300(self):
        dwg, clip = self.build_drawing((400, 300), rotated=False)
        self.check_drawing(dwg, clip, rotated=False)

    def test_normalized_coordinates_are_canvas_independent(self):
        dwg1, _ = self.build_drawing((100, 100), rotated=False)
        dwg2, _ = self.build_drawing((400, 300), rotated=False)
        d1 = self.check_drawing(dwg1, _, rotated=False)
        d2 = self.check_drawing(dwg2, _, rotated=False)
        self.assertEqual(d1, d2)

    def test_rotated_target(self):
        dwg, clip = self.build_drawing((400, 300), rotated=True)
        self.check_drawing(dwg, clip, rotated=True)


def _fmt(value):
    text = '%.6f' % value
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


if __name__ == '__main__':
    unittest.main()
