#!/usr/bin/env python
#coding:utf-8
# Purpose: test filter graph builder
# License: MIT License

import unittest

from svgwrite import filters


class TestFilterGraphShadow(unittest.TestCase):
    """Four-node drop-shadow graph: blur -> offset -> tint -> merge."""

    def build_graph(self):
        graph = filters.FilterGraph()
        blur = graph.feGaussianBlur('SourceAlpha', stdDeviation=2)
        offset = graph.feOffset(blur, dx=4, dy=4)
        tint = graph.feColorMatrix(offset, type_='matrix',
                                   values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.5 0')
        merge = graph.feMerge([tint, 'SourceGraphic'])
        return graph, (blur, offset, tint, merge)

    def test_auto_result_names(self):
        graph, nodes = self.build_graph()
        self.assertEqual([node.result for node in nodes],
                         ['n1', 'n2', 'n3', 'n4'])

    def test_xml_order_and_references(self):
        graph, nodes = self.build_graph()
        f = graph.build()
        self.assertEqual(
            f.tostring(),
            '<filter>'
            '<feGaussianBlur in="SourceAlpha" result="n1" stdDeviation="2" />'
            '<feOffset dx="4" dy="4" in="n1" result="n2" />'
            '<feColorMatrix in="n2" result="n3" type="matrix" '
            'values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.5 0" />'
            '<feMerge result="n4">'
            '<feMergeNode in="n3" />'
            '<feMergeNode in="SourceGraphic" />'
            '</feMerge>'
            '</filter>')

    def test_build_into_existing_filter(self):
        f = filters.Filter()
        graph = f.graph()
        blur = graph.feGaussianBlur('SourceAlpha', stdDeviation=2)
        offset = graph.feOffset(blur, dx=4, dy=4)
        graph.feMerge([offset, 'SourceGraphic'])
        result = graph.build()
        self.assertIs(result, f)
        self.assertEqual(
            f.tostring(),
            '<filter>'
            '<feGaussianBlur in="SourceAlpha" result="n1" stdDeviation="2" />'
            '<feOffset dx="4" dy="4" in="n1" result="n2" />'
            '<feMerge result="n3">'
            '<feMergeNode in="n2" />'
            '<feMergeNode in="SourceGraphic" />'
            '</feMerge>'
            '</filter>')


class TestFilterGraphInputs(unittest.TestCase):
    def test_reference_by_result_name(self):
        graph = filters.FilterGraph()
        blur = graph.feGaussianBlur('SourceGraphic', result='blurred')
        offset = graph.feOffset('blurred', dx=1, dy=1)
        self.assertEqual(offset.element['in'], 'blurred')

    def test_explicit_result_names(self):
        graph = filters.FilterGraph()
        node = graph.feOffset('SourceGraphic', dx=1, dy=1, result='shifted')
        self.assertEqual(node.result, 'shifted')
        self.assertEqual(node.element.tostring(),
                         '<feOffset dx="1" dy="1" in="SourceGraphic" result="shifted" />')

    def test_auto_names_skip_handwritten_names(self):
        graph = filters.FilterGraph()
        graph.feOffset('SourceGraphic', result='n1')
        node = graph.feGaussianBlur('n1')
        self.assertEqual(node.result, 'n2')

    def test_composite_dual_input(self):
        graph = filters.FilterGraph()
        blur = graph.feGaussianBlur('SourceAlpha', stdDeviation=2)
        comp = graph.feComposite(blur, in2='SourceGraphic', operator='in')
        self.assertEqual(comp.element['in'], 'n1')
        self.assertEqual(comp.element['in2'], 'SourceGraphic')

    def test_composite_node_in2(self):
        graph = filters.FilterGraph()
        flood = graph.feFlood(flood_color='red')
        blur = graph.feGaussianBlur('SourceAlpha', stdDeviation=2)
        comp = graph.feComposite(flood, in2=blur, operator='in')
        self.assertEqual(comp.element['in'], 'n1')
        self.assertEqual(comp.element['in2'], 'n2')

    def test_merge_by_result_names(self):
        graph = filters.FilterGraph()
        graph.feOffset('SourceAlpha', dx=2, dy=2, result='shadow')
        merge = graph.feMerge(['shadow', 'SourceGraphic'])
        self.assertEqual(
            merge.element.tostring(),
            '<feMerge result="n1">'
            '<feMergeNode in="shadow" />'
            '<feMergeNode in="SourceGraphic" />'
            '</feMerge>')

    def test_no_input_primitives(self):
        graph = filters.FilterGraph()
        flood = graph.feFlood(flood_color='blue')
        self.assertNotIn('in', flood.element.attribs)
        turbulence = graph.feTurbulence(baseFrequency='0.1')
        self.assertNotIn('in', turbulence.element.attribs)

    def test_existing_single_node_api_still_works(self):
        f = filters.Filter()
        f.feGaussianBlur('input1', stdDeviation=2)
        self.assertEqual(f.tostring(),
                         '<filter><feGaussianBlur in="input1" stdDeviation="2" /></filter>')


class TestFilterGraphErrors(unittest.TestCase):
    def test_empty_graph(self):
        graph = filters.FilterGraph()
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.build()
        self.assertIn('empty', str(ctx.exception))

    def test_duplicate_result_name(self):
        graph = filters.FilterGraph()
        graph.feOffset('SourceGraphic', result='dup')
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.feGaussianBlur('SourceGraphic', result='dup')
        self.assertIn("duplicate result name 'dup'", str(ctx.exception))

    def test_reserved_result_name(self):
        graph = filters.FilterGraph()
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.feOffset('SourceGraphic', result='SourceGraphic')
        self.assertIn('reserved', str(ctx.exception))

    def test_missing_input(self):
        graph = filters.FilterGraph()
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.feGaussianBlur('no-such-result')
        self.assertIn("missing input 'no-such-result'", str(ctx.exception))

    def test_missing_input_in2(self):
        graph = filters.FilterGraph()
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.feComposite('SourceGraphic', in2='no-such-result')
        self.assertIn('missing input', str(ctx.exception))

    def test_missing_input_in_merge(self):
        graph = filters.FilterGraph()
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.feMerge(['SourceGraphic', 'no-such-result'])
        self.assertIn('missing input', str(ctx.exception))

    def test_cross_filter_reference(self):
        graph1 = filters.FilterGraph()
        graph2 = filters.FilterGraph()
        node = graph1.feOffset('SourceGraphic', dx=1, dy=1)
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph2.feGaussianBlur(node)
        self.assertIn('cross-filter reference', str(ctx.exception))

    def test_cyclic_dependency(self):
        graph = filters.FilterGraph()
        first = graph.feOffset('SourceGraphic', dx=1, dy=1)
        second = graph.feGaussianBlur(first, stdDeviation=2)
        # tamper with the first node so it depends on the second
        first.element['in'] = second.result
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.build()
        self.assertIn('cyclic dependency', str(ctx.exception))

    def test_missing_input_at_build_time(self):
        graph = filters.FilterGraph()
        node = graph.feOffset('SourceGraphic', dx=1, dy=1)
        node.element['in'] = 'deleted-result'
        with self.assertRaises(filters.FilterGraphError) as ctx:
            graph.build()
        self.assertIn("missing input 'deleted-result'", str(ctx.exception))

    def test_build_twice(self):
        graph = filters.FilterGraph()
        graph.feFlood()
        graph.build()
        with self.assertRaises(filters.FilterGraphError):
            graph.build()

    def test_errors_are_value_errors(self):
        self.assertTrue(issubclass(filters.FilterGraphError, ValueError))


class TestFilterGraphOrdering(unittest.TestCase):
    def test_topological_order_after_tampering(self):
        graph = filters.FilterGraph()
        merge = graph.feMerge(['SourceGraphic'])
        blur = graph.feGaussianBlur('SourceGraphic', stdDeviation=2)
        # rewire the merge to depend on the blur: blur must be emitted first
        merge.element.elements[0]['in'] = blur.result
        f = graph.build()
        self.assertEqual(
            f.tostring(),
            '<filter>'
            '<feGaussianBlur in="SourceGraphic" result="n2" stdDeviation="2" />'
            '<feMerge result="n1"><feMergeNode in="n2" /></feMerge>'
            '</filter>')

    def test_diamond_dependency(self):
        graph = filters.FilterGraph()
        blur = graph.feGaussianBlur('SourceAlpha', stdDeviation=2)
        offset = graph.feOffset(blur, dx=4, dy=4)
        flood = graph.feFlood(flood_color='black')
        comp = graph.feComposite(flood, in2=offset, operator='in')
        graph.feMerge([comp, 'SourceGraphic'])
        f = graph.build()
        names = [child.elementname for child in f.elements]
        self.assertEqual(names, ['feGaussianBlur', 'feFlood', 'feOffset',
                                 'feComposite', 'feMerge'])


if __name__ == '__main__':
    unittest.main()
