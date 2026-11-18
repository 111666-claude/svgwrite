#!/usr/bin/env python
#coding:utf-8
# Author: mozman --<mozman@gmx.at>
# Purpose: gradient inheritance (xlink:href) validation and expansion
# Created: 18.11.2026
# Copyright (C) 2026, Manfred Moitzi
# License: MIT License
"""
Gradient inheritance support.

SVG :class:`~svgwrite.gradients.LinearGradient` and
:class:`~svgwrite.gradients.RadialGradient` elements may reference another
gradient with the **xlink:href** attribute and inherit its stops, coordinate
system and transform. Icon themes often derive many color schemes from one
base gradient, which produces long reference chains (``C -> B -> A``). This
module

* builds the reference graph of all linear/radial gradients inside a
  :class:`~svgwrite.drawing.Drawing`,
* resolves the *effective* stops, geometry, coordinate system and transform of
  every gradient (local properties take precedence over inherited ones),
* validates the graph and
* can expand the chains into self contained gradients with closed references
  while the original objects remain serializable.

SVG 1.1 inheritance rules (only same type gradients may reference each other):

* if the referencing gradient has no stops of its own, the stops of the
  referenced gradient are used; local stops replace the inherited ones;
* gradient attributes are inherited unless they are set locally.

Errors are reported as :class:`GradientInheritanceError`.
"""

import copy

from svgwrite.data import pattern

LINEAR_GRADIENT = 'linearGradient'
RADIAL_GRADIENT = 'radialGradient'
GRADIENT_ELEMENTS = frozenset([LINEAR_GRADIENT, RADIAL_GRADIENT])

# geometry attributes, specific per gradient type
LINEAR_GEOMETRY_ATTRIBS = frozenset(['x1', 'y1', 'x2', 'y2'])
RADIAL_GEOMETRY_ATTRIBS = frozenset(['cx', 'cy', 'r', 'fx', 'fy'])

# attributes that are inherited by reference (besides the geometry attrs)
SHARED_GRADIENT_ATTRIBS = frozenset([
    'gradientUnits', 'gradientTransform', 'spreadMethod',
])
INHERITABLE_ATTRIBS = (
    LINEAR_GEOMETRY_ATTRIBS | RADIAL_GEOMETRY_ATTRIBS | SHARED_GRADIENT_ATTRIBS
)

# attributes that establish the inheritance link itself
REFERENCE_ATTRIBS = frozenset(['xlink:href', 'href'])


class GradientInheritanceError(ValueError):
    """ Raised for invalid gradient inheritance graphs or gradient content. """


class GradientInfo(object):
    """ Resolved view of a single gradient.

    The values are *effective* values: local properties of the gradient take
    precedence, missing properties are inherited along the **xlink:href**
    chain.

    :ivar gradient: the original gradient element
    :ivar str elementname: ``'linearGradient'`` or ``'radialGradient'``
    :ivar str id: explicit SVG **id** attribute or ``None``
    :ivar str href: raw **xlink:href** value (``'#id'``) or ``None``
    :ivar str parent_id: referenced id without the leading ``'#'`` or ``None``
    :ivar dict attribs: effective inheritable SVG attributes
    :ivar list stops: effective stop elements (deep copies of
      :class:`~svgwrite.gradients._GradientStop` objects)
    :ivar list chain: ids of the inheritance chain, starting with the
      gradient itself and ending at the chain root (``None`` for gradients
      without an explicit id)
    """
    def __init__(self, gradient, parent_id, attribs, stops, chain):
        self.gradient = gradient
        self.elementname = gradient.elementname
        self.id = gradient.attribs.get('id')
        self.href = gradient.attribs.get('xlink:href')
        self.parent_id = parent_id
        self.attribs = dict(attribs)
        self.stops = list(stops)
        self.chain = list(chain)

    @property
    def geometry(self):
        """ Effective geometry attributes as `dict`
        (x1/y1/x2/y2 or cx/cy/r/fx/fy).
        """
        names = (LINEAR_GEOMETRY_ATTRIBS if self.elementname == LINEAR_GRADIENT
                 else RADIAL_GEOMETRY_ATTRIBS)
        return dict((name, self.attribs[name]) for name in names
                    if name in self.attribs)

    @property
    def transform(self):
        """ Effective **gradientTransform** value or ``None``. """
        return self.attribs.get('gradientTransform')

    @property
    def gradient_units(self):
        """ Effective **gradientUnits** value or ``None``. """
        return self.attribs.get('gradientUnits')

    @property
    def spread_method(self):
        """ Effective **spreadMethod** value or ``None``. """
        return self.attribs.get('spreadMethod')

    def __repr__(self):
        return "GradientInfo(elementname=%r, id=%r, parent_id=%r)" % (
            self.elementname, self.id, self.parent_id)


def _iter_elements(root):
    """ Iterate over root and every nested element, depth first. """
    stack = [root]
    while stack:
        element = stack.pop()
        yield element
        children = getattr(element, 'elements', None)
        if children:
            # extend reversed to keep document order when popping
            stack.extend(reversed(children))


def _local_stops(gradient):
    return [element for element in gradient.elements
            if element.elementname == 'stop']


def _gradient_label(gradient):
    id_ = gradient.attribs.get('id')
    return "id=%r" % id_ if id_ is not None else "<gradient without id>"


def _reference_target_id(gradient):
    """ Return the id referenced by the gradient (without the leading ``#``).

    Returns ``None`` when the gradient does not reference another gradient.
    """
    href = gradient.attribs.get('xlink:href')
    if href is None:
        href = gradient.attribs.get('href')  # SVG2 style href
    if href is None:
        return None
    if not isinstance(href, str) or not href.startswith('#') or len(href) < 2:
        raise GradientInheritanceError(
            "gradient %s has invalid reference %r: only same-document "
            "fragment references ('#id') are supported"
            % (_gradient_label(gradient), href))
    return href[1:]


def _validate_offset(stop, gradient):
    if 'offset' not in stop.attribs:
        raise GradientInheritanceError(
            "stop element without 'offset' attribute in gradient %s"
            % _gradient_label(gradient))
    offset = stop.attribs['offset']
    valid = False
    if isinstance(offset, bool):
        valid = False
    elif isinstance(offset, (int, float)):
        valid = 0 <= float(offset) <= 1
    elif isinstance(offset, str):
        match = pattern.percentage.match(offset)
        if match:
            valid = 0 <= float(match.group(1)) <= 100
        elif pattern.number.match(offset):
            valid = 0 <= float(offset) <= 1
    if not valid:
        raise GradientInheritanceError(
            "invalid stop offset %r in gradient %s: expected a number "
            "between 0 and 1 or a percentage between 0%% and 100%%"
            % (offset, _gradient_label(gradient)))


class GradientInheritance(object):
    """ Build, validate and resolve gradient inheritance chains of a drawing.

    :param drawing: a :class:`~svgwrite.drawing.Drawing` (or any container
      element) containing linear/radial gradients
    """
    def __init__(self, drawing):
        self.drawing = drawing
        self.gradients = []          # document order
        self._gradient_by_id = {}    # id -> gradient
        self._element_by_id = {}     # id -> any element with that id
        self._collect()

    # ------------------------------------------------------------------ #
    # graph construction
    # ------------------------------------------------------------------ #
    def _collect(self):
        duplicates = set()
        for element in _iter_elements(self.drawing):
            elementname = getattr(element, 'elementname', None)
            if elementname in GRADIENT_ELEMENTS:
                self.gradients.append(element)

            id_ = getattr(element, 'attribs', {}).get('id')
            if id_ is not None:
                if id_ in self._element_by_id:
                    duplicates.add(id_)
                else:
                    self._element_by_id[id_] = element

        if duplicates:
            raise GradientInheritanceError(
                "duplicate id attribute in drawing: %s"
                % ", ".join(sorted(duplicates)))

        for gradient in self.gradients:
            id_ = gradient.attribs.get('id')
            if id_ is not None:
                self._gradient_by_id[id_] = gradient

    # ------------------------------------------------------------------ #
    # validation
    # ------------------------------------------------------------------ #
    def validate(self):
        """ Validate every gradient in the drawing.

        Checks missing reference ids, references to non-gradient elements,
        cross type inheritance, reference cycles, empty stop lists and
        invalid stop offsets.

        :raises GradientInheritanceError: on the first problem found
        :returns: list of :class:`GradientInfo` objects (document order)
        """
        self._check_references()
        for gradient in self.gradients:
            self._walk_chain(gradient)
        self._check_stops()
        return [self.resolve(gradient) for gradient in self.gradients]

    def _check_references(self):
        for gradient in self.gradients:
            target_id = _reference_target_id(gradient)
            if target_id is None:
                continue
            target = self._element_by_id.get(target_id)
            if target is None:
                raise GradientInheritanceError(
                    "gradient %s references missing id '#%s'"
                    % (_gradient_label(gradient), target_id))
            if target.elementname not in GRADIENT_ELEMENTS:
                raise GradientInheritanceError(
                    "gradient %s references non-gradient element '#%s' (%s)"
                    % (_gradient_label(gradient), target_id,
                       target.elementname))
            if target.elementname != gradient.elementname:
                raise GradientInheritanceError(
                    "cross type gradient inheritance: %s %s cannot inherit "
                    "from %s '#%s'"
                    % (gradient.elementname, _gradient_label(gradient),
                       target.elementname, target_id))

    def _check_stops(self):
        for gradient in self.gradients:
            chain = self._walk_chain(gradient)
            if not _local_stops(chain[-1]):
                raise GradientInheritanceError(
                    "gradient %s has no stop colors and neither does its "
                    "inheritance chain (root %s)"
                    % (_gradient_label(gradient),
                       _gradient_label(chain[-1])))
            for stop in _local_stops(gradient):
                _validate_offset(stop, gradient)

    def _walk_chain(self, gradient):
        """ Follow the href chain and return it; detect cycles. """
        chain = []
        seen = set()
        current = gradient
        while current is not None:
            identity = id(current)
            if identity in seen:
                labels = [_gradient_label(item) for item in chain]
                labels.append(_gradient_label(current))
                raise GradientInheritanceError(
                    "cyclic gradient inheritance detected: %s"
                    % " -> ".join(labels))
            seen.add(identity)
            chain.append(current)
            target_id = _reference_target_id(current)
            if target_id is None:
                break
            target = self._gradient_by_id.get(target_id)
            if target is None:
                # reference integrity is validated separately
                raise GradientInheritanceError(
                    "gradient %s references missing or invalid id '#%s'"
                    % (_gradient_label(current), target_id))
            current = target
        return chain

    # ------------------------------------------------------------------ #
    # resolution
    # ------------------------------------------------------------------ #
    def resolve(self, gradient=None):
        """ Resolve the effective properties of one gradient.

        :param gradient: a gradient element of the drawing; if ``None`` the
          first gradient is used
        :returns: :class:`GradientInfo`
        """
        if gradient is None:
            if not self.gradients:
                raise GradientInheritanceError(
                    "the drawing contains no linear or radial gradient")
            gradient = self.gradients[0]
        chain = self._walk_chain(gradient)

        effective_attribs = {}
        effective_stops = []
        # root first -> child last, local values overwrite inherited ones
        for link in reversed(chain):
            for name in INHERITABLE_ATTRIBS:
                value = link.attribs.get(name)
                if value is not None:
                    effective_attribs[name] = value
            stops = _local_stops(link)
            if stops:
                # local stops replace the stops of the referenced gradient
                effective_stops = [copy.deepcopy(stop) for stop in stops]

        chain_ids = [item.attribs.get('id') for item in chain]
        return GradientInfo(gradient, _reference_target_id(gradient),
                            effective_attribs, effective_stops, chain_ids)

    def infos(self):
        """ Return :class:`GradientInfo` for every gradient (document order).

        Calls :meth:`validate` first.
        """
        return self.validate()

    def info_by_id(self, id_):
        """ Return the validated :class:`GradientInfo` of gradient `id_`. """
        gradient = self._gradient_by_id.get(id_)
        if gradient is None:
            raise GradientInheritanceError("no gradient with id %r" % id_)
        self.validate()
        return self.resolve(gradient)

    # ------------------------------------------------------------------ #
    # expansion
    # ------------------------------------------------------------------ #
    def expand(self):
        """ Expand every inheritance chain into self contained gradients.

        The gradient objects inside the drawing are modified in place:

        * the **xlink:href** reference (and the ``href`` instance attribute)
          is removed, so the expanded drawing has closed references;
        * inherited geometry, **gradientUnits**, **spreadMethod** and
          **gradientTransform** values are materialized, local attributes
          keep precedence;
        * inherited stops are copied into gradients without local stops;
          local stops are never replaced.

        The original objects stay valid and serializable, and calling
        :meth:`expand` again is a no-op.

        :raises GradientInheritanceError: if the graph does not validate
        :returns: list of :class:`GradientInfo` of the expanded gradients
        """
        infos = self.validate()
        for info in infos:
            gradient = info.gradient

            # materialize inherited attributes without overwriting local ones
            for name, value in info.attribs.items():
                if gradient.attribs.get(name) is None:
                    gradient.attribs[name] = value

            # materialize inherited stops only when the gradient has none
            if not _local_stops(gradient):
                for stop in info.stops:
                    gradient.add(copy.deepcopy(stop))

            # close the reference
            for name in REFERENCE_ATTRIBS:
                gradient.attribs.pop(name, None)
            if hasattr(gradient, 'href'):
                delattr(gradient, 'href')

        # rebuild the graph view from the now reference free gradients
        return GradientInheritance(self.drawing).validate()
