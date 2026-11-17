#!/usr/bin/env python
# coding:utf-8
# Purpose: test automatic content bounding box / viewBox calculation
# License: MIT License

import math
import unittest

import svgwrite
from svgwrite.container import Group, Hyperlink, SVG
from svgwrite.masking import ClipPath
from svgwrite.boundingbox import (
    BoundingBox,
    BoundingBoxError,
    EmptyDrawingError,
    InvalidCoordinateError,
    PathParseError,
    UnsupportedElementError,
    calculate_bounds,
    fit_to_content,
)


def approx_box(testcase, box, expected, tol=1e-12):
    testcase.assertTrue(isinstance(box, BoundingBox))
    for got, want in zip(
            (box.minx, box.miny, box.maxx, box.maxy), expected):
        testcase.assertAlmostEqual(got, want, delta=tol)


class TestBoundingBoxClass(unittest.TestCase):
    def test_empty_box(self):
        box = BoundingBox()
        self.assertTrue(box.empty)
        self.assertIsNone(box.minx)

    def test_add_points(self):
        box = BoundingBox()
        box.add_point(3, 7).add_point(-2, 10).add_point(4, -1)
        self.assertEqual(
            (box.minx, box.miny, box.maxx, box.maxy), (-2, -1, 4, 10))
        self.assertFalse(box.empty)
        self.assertEqual((box.width, box.height), (6, 11))
        self.assertEqual(box.as_viewbox(), (-2, -1, 6, 11))

    def test_add_box_union(self):
        box = BoundingBox(0, 0, 1, 1)
        box.add_box(BoundingBox(-3, 2, 5, 4))
        self.assertEqual(
            (box.minx, box.miny, box.maxx, box.maxy), (-3, 0, 5, 4))

    def test_add_empty_box_is_noop(self):
        box = BoundingBox(0, 0, 1, 1)
        box.add_box(BoundingBox())
        self.assertEqual(
            (box.minx, box.miny, box.maxx, box.maxy), (0, 0, 1, 1))

    def test_non_finite_point_rejected(self):
        with self.assertRaises(InvalidCoordinateError):
            BoundingBox().add_point(float('inf'), 0)
        with self.assertRaises(InvalidCoordinateError):
            BoundingBox().add_point(1, float('nan'))

    def test_margin_scalar_and_tuple(self):
        box = BoundingBox(0, 0, 10, 20).add_margin(2)
        self.assertEqual(
            (box.minx, box.miny, box.maxx, box.maxy), (-2, -2, 12, 22))
        box = BoundingBox(0, 0, 10, 20).add_margin((1, 3))
        self.assertEqual(
            (box.minx, box.miny, box.maxx, box.maxy), (-1, -3, 11, 23))

    def test_negative_margin_rejected(self):
        with self.assertRaises(ValueError):
            BoundingBox(0, 0, 1, 1).add_margin(-0.1)

    def test_equality(self):
        self.assertEqual(BoundingBox(1, 2, 3, 4), BoundingBox(1, 2, 3, 4))
        self.assertNotEqual(BoundingBox(1, 2, 3, 4), BoundingBox(0, 2, 3, 4))


class TestBasicShapeBounds(unittest.TestCase):
    def test_rect(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.rect((10, 20), (30, 40)))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(10, 20, 40, 60))

    def test_rect_with_px_units(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.rect(('0px', '0px'), ('10px', '20px')))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 10, 20))

    def test_rect_physical_unit_rejected(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.rect(('1cm', 0), (2, 2)))
        with self.assertRaises(InvalidCoordinateError):
            calculate_bounds(dwg)

    def test_negative_rect_size_rejected(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.rect((0, 0), (-1, 2)))
        with self.assertRaises(InvalidCoordinateError):
            calculate_bounds(dwg)

    def test_circle(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.circle((10, -10), 5))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(5, -15, 15, -5))

    def test_ellipse(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.ellipse((0, 0), (3, 2)))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(-3, -2, 3, 2))

    def test_rotated_ellipse_exact_extents(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.ellipse((0, 0), (3, 2), transform='rotate(90)'))
        # rotation swaps the radii
        approx_box(self, calculate_bounds(dwg), (-2, -3, 2, 3))

    def test_line_polyline_polygon(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.line((-1, -2), (3, 4)))
        dwg.add(dwg.polyline([(0, 0), (5, -5), (-2, 2)]))
        dwg.add(dwg.polygon([(10, 10), (12, 10), (10, 13)]))
        self.assertEqual(
            calculate_bounds(dwg),
            BoundingBox(-2, -5, 12, 13))

    def test_missing_attribute_rejected(self):
        dwg = svgwrite.Drawing(debug=False)
        circle = dwg.circle((0, 0), 1)
        del circle.attribs['r']
        dwg.add(circle)
        with self.assertRaises(InvalidCoordinateError):
            calculate_bounds(dwg)


class TestTransforms(unittest.TestCase):
    def test_rotated_rect_about_origin(self):
        # rect (10,10)-(30,30), rotated 45 deg about the origin
        dwg = svgwrite.Drawing()
        rect = dwg.rect((10, 10), (20, 20))
        rect.rotate(45)
        dwg.add(rect)
        s = 10 * math.sqrt(2)
        approx_box(self, calculate_bounds(dwg),
                   (-s, s, s, 3 * s))

    def test_rotated_rect_about_center(self):
        dwg = svgwrite.Drawing()
        rect = dwg.rect((0, 0), (10, 10))
        rect.rotate(45, (5, 5))
        dwg.add(rect)
        d = 5 * math.sqrt(2)
        approx_box(self, calculate_bounds(dwg),
                   (5 - d, 5 - d, 5 + d, 5 + d))

    def test_nested_group_transforms_compose(self):
        dwg = svgwrite.Drawing()
        outer = Group()
        outer.translate(100, 200)
        inner = Group()
        inner.scale(2)
        inner.add(dwg.rect((0, 0), (10, 10)))
        outer.add(inner)
        dwg.add(outer)
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(100, 200, 120, 220))

    def test_shape_own_transform_is_applied(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.rect((0, 0), (10, 10),
                         transform='matrix(2 0 0 3 5 -7)'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(5, -7, 25, 23))

    def test_skew_transform(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.rect((0, 0), (10, 10), transform='skewX(45)'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 20, 10))

    def test_invalid_transform_rejected(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.rect((0, 0), (1, 1), transform='nonsense(1)'))
        with self.assertRaises(BoundingBoxError):
            calculate_bounds(dwg)

    def test_nested_svg_fragment_translation(self):
        dwg = svgwrite.Drawing(debug=False)
        fragment = SVG(insert=(7, 9), size=(100, 100))
        fragment.add(dwg.rect((0, 0), (10, 10)))
        dwg.add(fragment)
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(7, 9, 17, 19))

    def test_nested_svg_with_viewbox_rejected(self):
        dwg = svgwrite.Drawing(debug=False)
        fragment = SVG(insert=(0, 0), size=(10, 10))
        fragment.viewbox(0, 0, 5, 5)
        fragment.add(dwg.rect((0, 0), (2, 2)))
        dwg.add(fragment)
        with self.assertRaises(UnsupportedElementError):
            calculate_bounds(dwg)

    def test_hyperlink_container_is_traversed(self):
        dwg = svgwrite.Drawing()
        link = Hyperlink('http://example.com')
        link.add(dwg.rect((1, 2), (3, 4)))
        dwg.add(link)
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(1, 2, 4, 6))


class TestStrokeBounds(unittest.TestCase):
    def test_stroke_expands_bounds(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.line((0, 0), (10, 0),
                         stroke='black', **{'stroke-width': 4}))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(-2, -2, 12, 2))

    def test_default_stroke_width_is_one(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.line((0, 0), (10, 0), stroke='black'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(-0.5, -0.5, 10.5, 0.5))

    def test_stroke_none_does_not_expand(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.line((0, 0), (10, 0), stroke='none'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 10, 0))

    def test_no_stroke_attribute_does_not_expand(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.rect((0, 0), (10, 10)))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 10, 10))

    def test_stroke_inherited_from_group(self):
        dwg = svgwrite.Drawing(debug=False)
        group = Group()
        group['stroke'] = 'black'
        group['stroke-width'] = 4
        group.add(dwg.line((0, 0), (10, 0)))
        dwg.add(group)
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(-2, -2, 12, 2))

    def test_child_stroke_none_overrides_inheritance(self):
        dwg = svgwrite.Drawing(debug=False)
        group = Group()
        group['stroke'] = 'black'
        group['stroke-width'] = 4
        rect = dwg.rect((0, 0), (10, 10))
        rect['stroke'] = 'none'
        group.add(rect)
        dwg.add(group)
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 10, 10))

    def test_stroke_width_with_unit_rejected(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.line((0, 0), (1, 1), stroke='black',
                         **{'stroke-width': '2cm'}))
        with self.assertRaises(InvalidCoordinateError):
            calculate_bounds(dwg)

    def test_stroke_under_rotation(self):
        dwg = svgwrite.Drawing(debug=False)
        rect = dwg.rect((0, 0), (10, 10),
                        stroke='black', **{'stroke-width': 2})
        rect.rotate(90)
        dwg.add(rect)
        # rotated square occupies (-10,0)-(0,10), stroke adds 1 unit in
        # every root-space direction
        approx_box(self, calculate_bounds(dwg),
                   (-11, -1, 1, 11))


class TestPathBounds(unittest.TestCase):
    def test_moveto_lineto(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M 10 20 L 30 40'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(10, 20, 30, 40))

    def test_compact_path_syntax(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M0,0L1,1Q2,2 3,0C4,4 5,5 6,0z'))
        box = calculate_bounds(dwg)
        self.assertAlmostEqual(box.minx, 0.0)
        self.assertAlmostEqual(box.maxx, 6.0)
        self.assertGreater(box.maxy, 2.8)

    def test_relative_commands_match_absolute(self):
        abs_dwg = svgwrite.Drawing(debug=False)
        abs_dwg.add(abs_dwg.path(d='M10 10 L15 15 V10 H25'))
        rel_dwg = svgwrite.Drawing(debug=False)
        rel_dwg.add(rel_dwg.path(d='M10 10 l5 5 v-5 h10'))
        self.assertEqual(calculate_bounds(abs_dwg),
                         calculate_bounds(rel_dwg))

    def test_closepath_returns_to_subpath_start(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M5 5 L15 5 L15 15 Z L0 0'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 15, 15))

    def test_horizontal_vertical_commands(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M10 10 H20 V30 H10 Z'))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(10, 10, 20, 30))

    def test_cubic_curve_extremum_beyond_endpoints(self):
        # symmetric arch whose peak (y=75) is an interior extremum
        dwg = svgwrite.Drawing()
        dwg.add(dwg.path(d='M 0 0 C 0 100 100 100 100 0'))
        box = calculate_bounds(dwg)
        self.assertEqual(
            (box.minx, box.maxx, box.miny), (0.0, 100.0, 0.0))
        self.assertAlmostEqual(box.maxy, 75.0)

    def test_cubic_curve_with_thick_stroke(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.path(d='M 0 0 C 0 100 100 100 100 0',
                         stroke='black', **{'stroke-width': 10}))
        box = calculate_bounds(dwg)
        self.assertEqual(
            (box.minx, box.miny, box.maxx, box.maxy),
            (-5.0, -5.0, 105.0, 80.0))

    def test_quadratic_curve_extremum(self):
        # B(t) with control (50,40): the curve peak is half the control
        # offset, i.e. y = 20 at t = 0.5
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M0 0 Q50 40 100 0'))
        box = calculate_bounds(dwg)
        self.assertAlmostEqual(box.maxy, 20.0)
        self.assertEqual((box.minx, box.maxx), (0.0, 100.0))

    def test_smooth_s_and_t_commands(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(
            d='M0 0 C10 10 20 10 30 0 S50 -10 60 0 '
              'Q70 10 80 0 T100 0'))
        box = calculate_bounds(dwg)
        self.assertLess(box.miny, 0.0)
        self.assertGreater(box.maxy, 5.0)

    def test_path_built_from_command_objects(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d=['M', (0, 0), 'L', (10, 10)]))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 10, 10))

    def test_unparseable_path_raises(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M 0 0 L xx'))
        with self.assertRaises(PathParseError):
            calculate_bounds(dwg)

    def test_path_missing_coordinate_raises(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='M0 0 L'))
        with self.assertRaises(PathParseError):
            calculate_bounds(dwg)

    def test_arc_command_unsupported(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.path(d='M0 0 A 5 5 0 0 1 10 10'))
        with self.assertRaises(UnsupportedElementError):
            calculate_bounds(dwg)

    def test_path_without_moveto_raises(self):
        dwg = svgwrite.Drawing(debug=False)
        dwg.add(dwg.path(d='L 1 1'))
        with self.assertRaises(PathParseError):
            calculate_bounds(dwg)

    def test_transformed_cubic_matches_closed_form(self):
        # an interior extremum in root space only exists after rotation;
        # solving extrema in local space would miss it
        ctrl = [(-17.6, -34.9), (15.1, -42.8),
                (3.6, -13.4), (-44.2, 0.7)]
        angle = -166.5
        dwg = svgwrite.Drawing(debug=False)
        path = dwg.path(d=['M', ctrl[0], 'C', ctrl[1], ctrl[2], ctrl[3]])
        path.rotate(angle)
        dwg.add(path)
        box = calculate_bounds(dwg)

        rad = math.radians(angle)
        ca, sa = math.cos(rad), math.sin(rad)
        mapped = [(ca * x - sa * y, sa * x + ca * y) for x, y in ctrl]

        def component_values(index):
            v = [p[index] for p in mapped]
            d01, d12, d23 = v[1] - v[0], v[2] - v[1], v[3] - v[2]
            a = 3 * (d01 - 2 * d12 + d23)
            b = 6 * (d12 - d01)
            c = 3 * d01

            def point(t):
                mt = 1 - t
                return (mt ** 3 * v[0] + 3 * mt ** 2 * t * v[1]
                        + 3 * mt * t ** 2 * v[2] + t ** 3 * v[3])

            values = [point(0.0), point(1.0)]
            if abs(a) > 1e-14:
                disc = b * b - 4 * a * c
                self.assertGreaterEqual(disc, 0.0)
                disc = math.sqrt(disc)
                roots = ((-b - disc) / (2 * a), (-b + disc) / (2 * a))
                for t in roots:
                    if 0.0 < t < 1.0:
                        values.append(point(t))
            return min(values), max(values)

        minx, maxx = component_values(0)
        miny, maxy = component_values(1)
        approx_box(self, box, (minx, miny, maxx, maxy), tol=1e-9)


class TestUnsupportedAndEmpty(unittest.TestCase):
    def test_empty_drawing_raises(self):
        with self.assertRaises(EmptyDrawingError):
            calculate_bounds(svgwrite.Drawing())

    def test_only_defs_raises_empty(self):
        dwg = svgwrite.Drawing()
        dwg.defs.add(dwg.circle((0, 0), 100))
        with self.assertRaises(EmptyDrawingError):
            calculate_bounds(dwg)

    def test_defs_content_is_skipped_but_shapes_measured(self):
        dwg = svgwrite.Drawing()
        dwg.defs.add(dwg.circle((0, 0), 100))
        dwg.add(dwg.rect((0, 0), (1, 1)))
        self.assertEqual(calculate_bounds(dwg),
                         BoundingBox(0, 0, 1, 1))

    def test_text_unsupported(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.text('hello', (1, 2)))
        with self.assertRaises(UnsupportedElementError):
            calculate_bounds(dwg)

    def test_image_unsupported(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.image('http://example.com/a.png', (0, 0), (5, 5)))
        with self.assertRaises(UnsupportedElementError):
            calculate_bounds(dwg)

    def test_use_unsupported(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.use('#other', (0, 0), (5, 5)))
        with self.assertRaises(UnsupportedElementError):
            calculate_bounds(dwg)

    def test_animate_child_unsupported(self):
        from svgwrite.animate import Animate
        dwg = svgwrite.Drawing(debug=False)
        rect = dwg.rect((0, 0), (1, 1))
        rect.add(Animate('x', values='0;10', dur='5s'))
        dwg.add(rect)
        with self.assertRaises(UnsupportedElementError):
            calculate_bounds(dwg)

    def test_all_exceptions_share_base(self):
        for exc in (EmptyDrawingError, InvalidCoordinateError,
                    PathParseError, UnsupportedElementError):
            self.assertTrue(issubclass(exc, BoundingBoxError))


class TestFitToContent(unittest.TestCase):
    def test_sets_viewbox_without_margin(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.rect((0, 0), (10, 20)))
        box = dwg.fit_to_content()
        self.assertEqual(dwg['viewBox'], '0.0,0.0,10.0,20.0')
        self.assertEqual(box.as_viewbox(), (0.0, 0.0, 10.0, 20.0))

    def test_sets_viewbox_with_scalar_margin(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.rect((0, 0), (10, 20)))
        dwg.fit_to_content(margin=2)
        self.assertEqual(dwg['viewBox'], '-2.0,-2.0,14.0,24.0')

    def test_sets_viewbox_with_tuple_margin(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.rect((0, 0), (10, 20)))
        dwg.fit_to_content(margin=(1, 3))
        self.assertEqual(dwg['viewBox'], '-1.0,-3.0,12.0,26.0')

    def test_module_level_function_equals_method(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.circle((0, 0), 2))
        self.assertEqual(fit_to_content(dwg, 0.5),
                         dwg.fit_to_content(0.5))

    def test_fit_is_idempotent(self):
        dwg = svgwrite.Drawing()
        dwg.add(dwg.rect((0, 0), (10, 10)))
        dwg.fit_to_content(margin=1)
        first = dwg['viewBox']
        dwg.fit_to_content(margin=1)
        self.assertEqual(dwg['viewBox'], first)

    def test_fit_preserves_elements_and_serialization(self):
        dwg = svgwrite.Drawing()
        group = Group()
        group.rotate(30)
        group.add(dwg.rect((5, 5), (8, 8)))
        dwg.add(group)
        dwg.add(dwg.circle((20, 20), 4))
        before = dwg.tostring()
        box = dwg.fit_to_content(margin=1.5)
        after = dwg.tostring()
        # the only serialized difference is the newly added viewBox
        stripped = after.replace(
            ' viewBox="%s,%s,%s,%s"' % box.as_viewbox(), '', 1)
        self.assertEqual(stripped, before)
        # element order itself is untouched
        self.assertEqual([e.elementname for e in dwg.elements],
                         ['defs', 'g', 'circle'])

    def test_fit_empty_drawing_raises(self):
        with self.assertRaises(EmptyDrawingError):
            svgwrite.Drawing().fit_to_content()


class TestIntegratedSample(unittest.TestCase):
    """Rotated rectangle + cubic curve + thick stroke end-to-end sample."""

    def test_combined_drawing_bounds_and_xml(self):
        dwg = svgwrite.Drawing()
        rect = dwg.rect((-10, -10), (20, 20),
                        stroke='black', **{'stroke-width': 2})
        rect.rotate(45)
        dwg.add(rect)
        dwg.add(dwg.path(d='M 0 0 C 0 100 100 100 100 0',
                         stroke='black', **{'stroke-width': 10}))
        box = dwg.fit_to_content(margin=0)
        # rotated rect: corners at (±10√2, ±10√2), stroke adds 1 unit
        s = 10 * math.sqrt(2) + 1
        self.assertAlmostEqual(box.minx, -s, delta=1e-9)
        self.assertAlmostEqual(box.miny, -s, delta=1e-9)
        # cubic arch spans x 0..100 with stroke 5
        self.assertAlmostEqual(box.maxx, 105.0, delta=1e-9)
        # arch peak 75 plus stroke 5
        self.assertAlmostEqual(box.maxy, 80.0, delta=1e-9)
        # the produced XML still contains both shapes in original order
        xml = dwg.tostring()
        self.assertIn('<rect', xml)
        self.assertIn('<path', xml)
        self.assertLess(xml.index('<rect'), xml.index('<path'))
        self.assertIn('viewBox="', xml)


if __name__ == '__main__':
    unittest.main()
