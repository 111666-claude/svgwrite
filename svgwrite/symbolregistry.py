#!/usr/bin/env python
#coding:utf-8
# Purpose: registry for reusable graphic symbols (<symbol> in defs + <use> instances)
# License: MIT License
"""
The **SymbolRegistry** registers supported basic shapes and groups as
**symbol** definitions inside the **defs** section of a **Drawing** and
creates **use** instances with individual position and transform.

Structurally identical content is registered only once and reuses the same
symbol, so every definition appears exactly once in **defs** no matter how
often it is placed on the drawing::

    dwg = svgwrite.Drawing('map.svg')
    registry = svgwrite.SymbolRegistry(dwg)

    icon = dwg.g()
    icon.add(dwg.circle(center=(0, 0), r=5))
    icon.add(dwg.line((-5, 0), (5, 0)))

    symbol_id = registry.register(icon)          # -> e.g. 'symbol1'
    registry.use(symbol_id, insert=(10, 20))     # first instance
    registry.use(symbol_id, insert=(50, 60), transform='rotate(45)')

Rules and errors:

* only basic shapes (line, rect, circle, ellipse, polyline, polygon, path)
  and groups (**g**) can be registered - anything else raises `ValueError`
* nested **symbol** or **use** elements inside registered content raise
  `ValueError`
* circular references (an element containing itself) raise `ValueError`
* empty groups raise `ValueError`
* a `symbol_id` already used for different content raises `ValueError`;
  identical content always returns the id of the existing symbol
"""
from svgwrite.base import BaseElement
from svgwrite.container import Symbol

#: element names that may be registered as (part of) a symbol
SUPPORTED_ELEMENTS = frozenset([
    'line', 'rect', 'circle', 'ellipse', 'polyline', 'polygon', 'path', 'g',
])

#: element names that must not appear inside registered content
FORBIDDEN_ELEMENTS = frozenset(['symbol', 'use'])


class SymbolRegistry(object):
    """ Registers graphic content as **symbol** definitions in the **defs**
    section of a **Drawing** and instantiates them as **use** elements.

    :param drawing: the :class:`~svgwrite.drawing.Drawing` the symbols and
        instances are added to
    :param string prefix: prefix for automatically generated symbol ids

    """

    def __init__(self, drawing, prefix='symbol'):
        self.drawing = drawing
        self.prefix = prefix
        self._symbols = {}       # symbol id -> Symbol object
        self._fingerprints = {}  # content fingerprint -> symbol id
        self._counter = 0

    def __len__(self):
        """ Count of registered symbol definitions. """
        return len(self._symbols)

    def __contains__(self, symbol_id):
        """ `True` if `symbol_id` is a registered symbol id. """
        return symbol_id in self._symbols

    @property
    def symbol_ids(self):
        """ Tuple of all registered symbol ids in registration order. """
        return tuple(self._symbols)

    def register(self, content, symbol_id=None):
        """ Register `content` as a **symbol** in the **defs** section of the
        drawing and return its reference id.

        :param content: a single supported SVG element (basic shape or group)
            or an iterable of such elements, which are combined into one symbol
        :param string symbol_id: explicit reference id, an id is generated
            automatically if omitted

        Structurally identical content (same elements, attributes and
        nesting, ignoring **id** attributes) is registered only once and the
        id of the existing symbol is returned.

        """
        if isinstance(content, BaseElement):
            elements = [content]
        else:
            elements = list(content)
        if not elements:
            raise ValueError("nothing to register: content is empty")

        fingerprint = tuple(self._fingerprint(element, set()) for element in elements)

        if fingerprint in self._fingerprints:
            existing_id = self._fingerprints[fingerprint]
            if symbol_id is not None and symbol_id != existing_id:
                raise ValueError(
                    "id conflict: identical content is already registered "
                    "as '%s', can not register it as '%s'" % (existing_id, symbol_id))
            return existing_id

        if symbol_id is None:
            symbol_id = self._generate_id()
        elif symbol_id in self._symbols or symbol_id in self._defs_ids():
            raise ValueError("id conflict: id '%s' is already in use" % symbol_id)

        symbol = Symbol(factory=self.drawing)
        symbol['id'] = symbol_id
        for element in elements:
            symbol.add(element)
        self.drawing.defs.add(symbol)

        self._symbols[symbol_id] = symbol
        self._fingerprints[fingerprint] = symbol_id
        return symbol_id

    def use(self, symbol_id, insert=None, transform=None, **extra):
        """ Create a **use** instance of a registered symbol, add it to the
        drawing and return the **use** element.

        :param string symbol_id: reference id returned by :meth:`register`
            (a leading ``'#'`` is accepted and stripped)
        :param 2-tuple insert: insert position (**x**, **y**) of this instance
        :param string transform: additional **transform** attribute for this
            instance (e.g. ``'rotate(45)'``)
        :param extra: additional SVG attributes as keyword-arguments

        """
        symbol_id = str(symbol_id).lstrip('#')
        if symbol_id not in self._symbols:
            raise ValueError("unknown symbol id: '%s'" % symbol_id)
        use = self.drawing.use(self._symbols[symbol_id], insert=insert, **extra)
        if transform is not None:
            use['transform'] = transform
        self.drawing.add(use)
        return use

    def place(self, content, insert=None, transform=None, symbol_id=None, **extra):
        """ Convenience method: register `content` (reusing an existing
        symbol for identical content) and place a **use** instance of it on
        the drawing. Returns the **use** element.

        """
        return self.use(self.register(content, symbol_id=symbol_id),
                        insert=insert, transform=transform, **extra)

    def _generate_id(self):
        used = self._defs_ids()
        while True:
            self._counter += 1
            symbol_id = "%s%d" % (self.prefix, self._counter)
            if symbol_id not in self._symbols and symbol_id not in used:
                return symbol_id

    def _defs_ids(self):
        """ Ids of all elements already present in the drawing's defs section. """
        return set(element.attribs['id']
                   for element in self.drawing.defs.elements
                   if 'id' in getattr(element, 'attribs', {}))

    def _fingerprint(self, element, active):
        """ Structural fingerprint of `element`: element name, attributes
        (sorted, without **id**) and fingerprints of all subelements.

        `active` holds the `id()` of all ancestors to detect circular
        references.

        """
        name = getattr(element, 'elementname', None)
        if name in FORBIDDEN_ELEMENTS:
            raise ValueError(
                "nested '%s' elements can not be registered as symbol content" % name)
        if name not in SUPPORTED_ELEMENTS or not isinstance(element, BaseElement):
            raise ValueError(
                "unsupported element '%s': only basic shapes (%s) and groups "
                "can be registered" % (name, ', '.join(sorted(SUPPORTED_ELEMENTS - {'g'}))))

        object_id = id(element)
        if object_id in active:
            raise ValueError("circular reference detected in '%s' element" % name)
        active.add(object_id)
        try:
            attribs = tuple(sorted(
                (key, self._normalize(value))
                for key, value in element.attribs.items() if key != 'id'))
            children = tuple(self._fingerprint(child, active) for child in element.elements)
        finally:
            active.discard(object_id)

        if name == 'g' and not children:
            raise ValueError("empty groups can not be registered as symbol content")
        return name, attribs, children

    @staticmethod
    def _normalize(value):
        """ Deterministic string representation of an attribute value. """
        if isinstance(value, (list, tuple)):
            return tuple(SymbolRegistry._normalize(v) for v in value)
        return str(value)
