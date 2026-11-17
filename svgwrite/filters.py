#!/usr/bin/env python
#coding:utf-8
# Author:  mozman --<mozman@gmx.at>
# Purpose: filters module
# Created: 03.11.2010
# Copyright (C) 2010, Manfred Moitzi
# License: MIT License

from svgwrite.base import BaseElement
from svgwrite.mixins import XLink, Presentation
from svgwrite.utils import strlist, is_string

__all__ = ['Filter', 'FilterGraph', 'FilterGraphError']


class _feDistantLight(BaseElement):
    elementname = 'feDistantLight'

    def __init__(self, azimuth=0, elevation=0, **extra):
        super(_feDistantLight, self).__init__(**extra)
        if azimuth != 0:
            self['azimuth'] = azimuth
        if elevation != 0:
            self['elevation'] = elevation


class _fePointLight(BaseElement):
    elementname = 'fePointLight'

    def __init__(self, source=(0, 0, 0), **extra):
        super(_fePointLight, self).__init__(**extra)
        x, y, z = source
        if x != 0:
            self['x'] = x
        if y != 0:
            self['y'] = y
        if z != 0:
            self['z'] = z


class _feSpotLight(_fePointLight):
    elementname = 'feSpotLight'

    def __init__(self, source=(0, 0, 0), target=(0, 0, 0), **extra):
        super(_feSpotLight, self).__init__(source, **extra)
        x, y, z = target
        if x != 0:
            self['pointsAtX'] = x
        if y != 0:
            self['pointsAtY'] = y
        if z != 0:
            self['pointsAtZ'] = z


class _FilterPrimitive(BaseElement, Presentation):
    pass


class _FilterNoInput(_FilterPrimitive):
    def __init__(self, start=None, size=None, **extra):
        super(_FilterNoInput, self).__init__(**extra)
        if start is not None:
            self['x'] = start[0]
            self['y'] = start[1]
        if size is not None:
            self['width'] = size[0]
            self['height'] = size[1]


class _FilterRequireInput(_FilterNoInput):
    def __init__(self, in_='SourceGraphic', **extra):
        super(_FilterRequireInput, self).__init__(**extra)
        self['in'] = in_


class _feBlend(_FilterRequireInput):
    elementname = 'feBlend'


class _feColorMatrix(_FilterRequireInput):
    elementname = 'feColorMatrix'


class _feComponentTransfer(_FilterRequireInput):
    elementname = 'feComponentTransfer'

    def feFuncR(self, type_, **extra):
        return self.add(_feFuncR(type_, factory=self, **extra))

    def feFuncG(self, type_, **extra):
        return self.add(_feFuncG(type_, factory=self, **extra))

    def feFuncB(self, type_, **extra):
        return self.add(_feFuncB(type_, factory=self, **extra))

    def feFuncA(self, type_, **extra):
        return self.add(_feFuncA(type_, factory=self, **extra))


class _feFuncR(_FilterPrimitive):
    elementname = 'feFuncR'

    def __init__(self, type_, **extra):
        super(_feFuncR, self).__init__(**extra)
        self['type'] = type_


class _feFuncG(_feFuncR):
    elementname = 'feFuncG'


class _feFuncB(_feFuncR):
    elementname = 'feFuncB'


class _feFuncA(_feFuncR):
    elementname = 'feFuncA'


class _feComposite(_FilterRequireInput):
    elementname = 'feComposite'


class _feConvolveMatrix(_FilterRequireInput):
    elementname = 'feConvolveMatrix'


class _feDiffuseLighting(_FilterRequireInput):
    elementname = 'feDiffuseLighting'

    def feDistantLight(self, azimuth=0, elevation=0, **extra):
        return self.add(_feDistantLight(azimuth, elevation, **extra))

    def fePointLight(self, source=(0, 0, 0), **extra):
        return self.add(_fePointLight(source, **extra))

    def feSpotLight(self, source=(0, 0, 0), target=(0, 0, 0), **extra):
        return self.add(_feSpotLight(source, target, **extra))


class _feDisplacementMap(_FilterRequireInput):
    elementname = 'feDisplacementMap'


class _feFlood(_FilterNoInput):
    elementname = 'feFlood'


class _feGaussianBlur(_FilterRequireInput):
    elementname = 'feGaussianBlur'


class _feImage(_FilterNoInput, XLink):
    elementname = 'feImage'

    def __init__(self, href, start=None, size=None, **extra):
        super(_feImage, self).__init__(start, size, **extra)
        self.set_href(href)


class _feMergeNode(_FilterPrimitive):
    elementname = 'feMergeNode'


class _feMerge(_FilterNoInput):
    elementname = 'feMerge'
    def __init__(self, layernames, **extra):
        super(_feMerge, self).__init__(**extra)
        self.feMergeNode(layernames)

    def feMergeNode(self, layernames):
        for layername in layernames:
            self.add(_feMergeNode(in_=layername, factory=self))


class _feMorphology(_FilterRequireInput):
    elementname = 'feMorphology'


class _feOffset(_FilterRequireInput):
    elementname = 'feOffset'


class _feSpecularLighting(_feDiffuseLighting):
    elementname = 'feSpecularLighting'


class _feTile(_FilterRequireInput):
    elementname = 'feTile'


class _feTurbulence(_FilterNoInput):
    elementname = 'feTurbulence'


filter_factory = {
    'feBlend': _feBlend,
    'feColorMatrix': _feColorMatrix,
    'feComponentTransfer': _feComponentTransfer,
    'feComposite': _feComposite,
    'feConvolveMatrix': _feConvolveMatrix,
    'feDiffuseLighting': _feDiffuseLighting,
    'feDisplacementMap': _feDisplacementMap,
    'feFlood': _feFlood,
    'feGaussianBlur': _feGaussianBlur,
    'feImage': _feImage,
    'feMerge': _feMerge,
    'feMorphology': _feMorphology,
    'feOffset': _feOffset,
    'feSpecularLighting': _feSpecularLighting,
    'feTile': _feTile,
    'feTurbulence': _feTurbulence,
}


class _FilterBuilder(object):
    def __init__(self, cls, parent):
        self.cls = cls # primitive filter class to build
        self.parent = parent # the parent Filter() object

    def __call__(self, *args, **kwargs):
        kwargs['factory'] = self.parent # to get the _paramters object
        obj = self.cls(*args, **kwargs) # create an object of type 'cls'
        self.parent.add(obj) # add primitive filter to parent Filter()
        return obj


class Filter(BaseElement, XLink, Presentation):
    """
    The filter element is a container element for filter primitives, and
    also a **factory** for filter primitives.
    """
    elementname = 'filter'

    def __init__(self, start=None, size=None, resolution=None, inherit=None, **extra):
        """
        :param 2-tuple start: defines the start point of the filter effects region (**x**, **y**)
        :param 2-tuple size: defines the size of the filter effects region (**width**, **height**)
        :param resolution: takes the form ``'x-pixels [y-pixels]'``, and indicates
            the width and height of the intermediate images in pixels.
        :param inherit: inherits properties from Filter `inherit` see: **xlink:href**

        """
        super(Filter, self).__init__(**extra)
        if start is not None:
            self['x'] = start[0]
            self['y'] = start[1]
        if size is not None:
            self['width'] = size[0]
            self['height'] = size[1]
        if resolution is not None:
            if is_string(resolution):
                self['filterRes'] = resolution
            elif hasattr(resolution, '__iter__'):
                self['filterRes'] = strlist(resolution, ' ')
            else:
                self['filterRes'] = str(resolution)

        if inherit is not None:
            self.href = inherit
            self.update_id()

    def get_xml(self):
        self.update_id()
        return super(Filter, self).get_xml()

    def __getattr__(self, name):
        # create primitive filters by Filter.<filtername>(...)
        # and auto-add the new filter as subelement of Filter()
        if name in filter_factory:
            return _FilterBuilder(filter_factory[name], self)
        else:
            raise AttributeError("'%s' has no attribute '%s'" % (self.__class__.__name__, name))

    def graph(self):
        """
        Return a :class:`FilterGraph` that builds its primitives into this
        filter, auto-assigning ``result`` names and ordering the primitives
        by their dependencies.
        """
        return FilterGraph(self)


class FilterGraphError(ValueError):
    """Raised for invalid filter graph construction or build operations."""
    pass


class _GraphNode(object):
    """
    A node in a :class:`FilterGraph`, wrapping one filter primitive element.

    Use the node wherever an input reference is expected; it resolves to the
    node's (auto-assigned) ``result`` name.
    """
    def __init__(self, graph, element, dependencies):
        self.graph = graph
        self.element = element
        self.dependencies = dependencies

    @property
    def result(self):
        return self.element['result']

    def __str__(self):
        return self.result

    def __repr__(self):
        return "<%s %s result='%s'>" % (self.__class__.__name__,
                                        self.element.elementname,
                                        self.result)


class _GraphBuilder(object):
    def __init__(self, cls, graph):
        self.cls = cls # primitive filter class to build
        self.graph = graph # the parent FilterGraph() object

    def __call__(self, *args, **kwargs):
        return self.graph._add_node(self.cls, args, kwargs)


class FilterGraph(object):
    """
    Dependency-aware builder for SVG filter graphs.

    Create nodes with the same factory methods as :class:`Filter`
    (``feGaussianBlur``, ``feOffset``, ``feComposite``, ``feMerge``, ...).
    Inputs (``in_``, ``in2``, merge layer names) accept previously created
    nodes, their ``result`` names, or the well-known inputs
    (``SourceGraphic``, ``SourceAlpha``, ...). Every node gets a stable
    auto-assigned ``result`` name (``n1``, ``n2``, ...) unless an explicit
    ``result`` is given. :meth:`build` emits the primitives into a
    :class:`Filter` in a valid (topological) order.

    The classic drop-shadow example::

        graph = dwg.defs.add(dwg.filter()).graph()
        blur = graph.feGaussianBlur('SourceAlpha', stdDeviation=2)
        offset = graph.feOffset(blur, dx=4, dy=4)
        graph.feMerge([offset, 'SourceGraphic'])
        shadow_filter = graph.build()
    """

    #: well-known filter inputs defined by the SVG specification
    WELL_KNOWN_INPUTS = frozenset([
        'SourceGraphic', 'SourceAlpha', 'BackgroundImage',
        'BackgroundAlpha', 'FillPaint', 'StrokePaint',
    ])

    def __init__(self, filter_element=None):
        """
        :param filter_element: optional :class:`Filter` the graph builds into;
            if omitted, :meth:`build` creates a new one.
        """
        self._filter = filter_element
        self._nodes = [] # _GraphNode objects in creation order
        self._names = {} # result name -> _GraphNode
        self._counter = 0
        self._built = False

    def __getattr__(self, name):
        # create graph nodes by FilterGraph.<filtername>(...)
        if name in filter_factory:
            return _GraphBuilder(filter_factory[name], self)
        else:
            raise AttributeError("'%s' has no attribute '%s'" % (self.__class__.__name__, name))

    def __len__(self):
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes)

    def _auto_name(self):
        while True:
            self._counter += 1
            name = 'n%d' % self._counter
            if name not in self._names:
                return name

    def _resolve_input(self, value):
        """
        Resolve an input reference to a result name.

        Returns a 2-tuple (name, dependencies) where dependencies is a list
        of referenced :class:`_GraphNode` objects.
        """
        if isinstance(value, _GraphNode):
            if value.graph is not self:
                raise FilterGraphError(
                    "cross-filter reference: node %r belongs to a different "
                    "filter graph" % value.result)
            return value.result, [value]
        if is_string(value):
            if value in self.WELL_KNOWN_INPUTS:
                return value, []
            node = self._names.get(value)
            if node is not None:
                return value, [node]
            raise FilterGraphError(
                "missing input '%s': not a well-known filter input and no "
                "node with this result name exists in the graph" % value)
        raise FilterGraphError(
            "invalid filter input %r: expected a graph node or a result "
            "name" % (value,))

    def _add_node(self, cls, args, kwargs):
        args = list(args)
        kwargs = dict(kwargs)
        dependencies = []

        if issubclass(cls, _FilterRequireInput):
            if args:
                in_ = args.pop(0)
            else:
                in_ = kwargs.pop('in_', 'SourceGraphic')
            resolved, deps = self._resolve_input(in_)
            kwargs['in_'] = resolved
            dependencies.extend(deps)

        if 'in2' in kwargs:
            resolved, deps = self._resolve_input(kwargs['in2'])
            kwargs['in2'] = resolved
            dependencies.extend(deps)

        if cls is _feMerge:
            if args:
                layernames = args.pop(0)
            else:
                layernames = kwargs.pop('layernames', [])
            resolved_layers = []
            for layername in layernames:
                resolved, deps = self._resolve_input(layername)
                resolved_layers.append(resolved)
                dependencies.extend(deps)
            args.insert(0, resolved_layers)

        result = kwargs.pop('result', None)
        if result is None:
            result = self._auto_name()
        else:
            if not is_string(result):
                raise FilterGraphError(
                    "invalid result name %r: expected a string" % (result,))
            if result in self.WELL_KNOWN_INPUTS:
                raise FilterGraphError(
                    "result name '%s' is a reserved well-known filter "
                    "input" % result)
            if result in self._names:
                raise FilterGraphError(
                    "duplicate result name '%s' in filter graph" % result)
        kwargs['result'] = result

        if self._filter is not None:
            kwargs['factory'] = self._filter # to get the _parameter object
        element = cls(*args, **kwargs)
        node = _GraphNode(self, element, dependencies)
        self._nodes.append(node)
        self._names[result] = node
        return node

    def _collect_dependencies(self, node):
        """
        Re-read the input references of a node's element, so references
        changed by hand after node creation are honored by :meth:`build`.
        """
        element = node.element
        references = []
        for attr in ('in', 'in2'):
            if attr in element.attribs:
                references.append(element.attribs[attr])
        for subelement in element.elements: # e.g. feMergeNode
            if 'in' in subelement.attribs:
                references.append(subelement.attribs['in'])

        dependencies = []
        for reference in references:
            if reference in self.WELL_KNOWN_INPUTS:
                continue
            dependency = self._names.get(reference)
            if dependency is None:
                raise FilterGraphError(
                    "missing input '%s' referenced by node '%s': no node "
                    "with this result name exists in the graph"
                    % (reference, node.result))
            dependencies.append(dependency)
        return dependencies

    def _sorted_nodes(self):
        # Kahn's algorithm, stable by creation order
        dependencies = dict(
            (node, self._collect_dependencies(node)) for node in self._nodes)
        dependents = dict((node, []) for node in self._nodes)
        for node, deps in dependencies.items():
            for dep in deps:
                dependents[dep].append(node)
        ready = [node for node in self._nodes if not dependencies[node]]
        ordered = []
        while ready:
            node = ready.pop(0)
            ordered.append(node)
            for dependent in dependents[node]:
                dependencies[dependent].remove(node)
                if not dependencies[dependent]:
                    ready.append(dependent)
        if len(ordered) != len(self._nodes):
            cyclic = [node.result for node in self._nodes
                      if dependencies[node]]
            raise FilterGraphError(
                "cyclic dependency in filter graph involving: %s"
                % ', '.join(cyclic))
        return ordered

    def build(self, filter_element=None):
        """
        Add the graph's primitives to a :class:`Filter` in a valid
        dependency order and return the filter.

        :param filter_element: target filter; defaults to the filter the
            graph was created with, or a new :class:`Filter`.
        """
        if self._built:
            raise FilterGraphError("filter graph was already built")
        if not self._nodes:
            raise FilterGraphError("cannot build an empty filter graph")
        target = filter_element or self._filter or Filter()
        for node in self._sorted_nodes():
            target.add(node.element)
        self._built = True
        return target
