#!/usr/bin/env python
# coding:utf-8
# Purpose: compute the visible bounding box of svgwrite drawings
# License: MIT License
"""
Bounding box calculation for svgwrite drawings.

The fixed *viewBox* of a :class:`svgwrite.Drawing` does not know anything
about the shapes inside the drawing, so rotated or transformed content may
be clipped at the canvas edges.  This module walks the element tree,
computes the visible (geometric + stroke) bounds of every supported shape
in root canvas coordinates -- taking the affine transforms of nested
groups into account -- and provides an entry point to update the drawing's
*viewBox* automatically.

Supported geometry elements:

* ``rect`` (including rounded rectangles; the corner radii never expand
  beyond the rectangle itself)
* ``circle`` and ``ellipse``
* ``line``, ``polyline`` and ``polygon``
* ``path`` with the ``M``/``m``, ``L``/``l``, ``H``/``h``, ``V``/``v``,
  ``C``/``c``, ``S``/``s``, ``Q``/``q``, ``T``/``t`` and ``Z``/``z``
  commands (elliptical ``A``/``a`` arcs are not supported)

Unsupported elements (e.g. ``text`` or ``image``) and unparseable data
raise an explicit exception instead of producing silently wrong bounds.
"""

import math
import re

from svgwrite.utils import strlist

__all__ = [
    'BoundingBox',
    'BoundingBoxError',
    'EmptyDrawingError',
    'InvalidCoordinateError',
    'UnsupportedElementError',
    'PathParseError',
    'calculate_bounds',
    'fit_to_content',
]


class BoundingBoxError(Exception):
    """Base exception for bounding box calculation failures."""


class EmptyDrawingError(BoundingBoxError):
    """Raised when the drawing contains no supported visible geometry."""


class InvalidCoordinateError(BoundingBoxError):
    """Raised when an element carries coordinates that cannot be evaluated
    as plain user-space numbers (e.g. physical units such as ``'3cm'``)."""


class UnsupportedElementError(BoundingBoxError):
    """Raised for elements whose bounds cannot be computed (``text``,
    ``image``, ``use``, arc paths ...)."""


class PathParseError(BoundingBoxError):
    """Raised when a path ``d`` string cannot be parsed completely."""


# ---------------------------------------------------------------------------
# bounding box container
# ---------------------------------------------------------------------------

class BoundingBox(object):
    """An axis aligned bounding box in root canvas coordinates.

    Bounds are accumulated with :meth:`add_point` / :meth:`add_box`; an
    empty box has all four limits set to ``None``.
    """

    def __init__(self, minx=None, miny=None, maxx=None, maxy=None):
        self.minx = minx
        self.miny = miny
        self.maxx = maxx
        self.maxy = maxy

    @property
    def empty(self):
        """``True`` if no geometry has been added yet."""
        return self.minx is None

    @property
    def width(self):
        return self.maxx - self.minx

    @property
    def height(self):
        return self.maxy - self.miny

    def as_viewbox(self):
        """Return ``(minx, miny, width, height)`` as used by *viewBox*."""
        return self.minx, self.miny, self.width, self.height

    def add_point(self, x, y):
        if not (math.isfinite(x) and math.isfinite(y)):
            raise InvalidCoordinateError(
                "non-finite coordinate encountered: (%r, %r)" % (x, y))
        if self.empty:
            self.minx = self.maxx = x
            self.miny = self.maxy = y
        else:
            if x < self.minx:
                self.minx = x
            if x > self.maxx:
                self.maxx = x
            if y < self.miny:
                self.miny = y
            if y > self.maxy:
                self.maxy = y
        return self

    def add_box(self, other):
        if other is None or other.empty:
            return self
        self.add_point(other.minx, other.miny)
        self.add_point(other.maxx, other.maxy)
        return self

    def add_margin(self, margin):
        """Expand the box symmetrically.

        :param margin: a single number or a ``(horizontal, vertical)`` tuple
        :raises ValueError: for negative margins
        """
        if self.empty:
            return self
        if isinstance(margin, (tuple, list)):
            if len(margin) != 2:
                raise ValueError("margin tuple must have exactly 2 values")
            mx, my = margin
        else:
            mx = my = margin
        mx = float(mx)
        my = float(my)
        if mx < 0 or my < 0:
            raise ValueError("margin must not be negative")
        self.minx -= mx
        self.maxx += mx
        self.miny -= my
        self.maxy += my
        return self

    def __eq__(self, other):
        if not isinstance(other, BoundingBox):
            return NotImplemented
        return (self.minx, self.miny, self.maxx, self.maxy) == \
               (other.minx, other.miny, other.maxx, other.maxy)

    def __repr__(self):
        return "BoundingBox(minx=%r, miny=%r, maxx=%r, maxy=%r)" % (
            self.minx, self.miny, self.maxx, self.maxy)


# ---------------------------------------------------------------------------
# affine transform helpers: matrices are (a, b, c, d, e, f) mapping
#   x' = a*x + c*y + e
#   y' = b*x + d*y + f
# ---------------------------------------------------------------------------

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiply(m1, m2):
    """Return the matrix of applying *m1* then *m2* (SVG transform-list
    semantics: transforms are post-multiplied)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(matrix, x, y):
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _translate(tx, ty=0.0):
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def _scale(sx, sy=None):
    if sy is None:
        sy = sx
    return (sx, 0.0, 0.0, sy, 0.0, 0.0)


def _rotate(angle, cx=0.0, cy=0.0):
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    rot = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
    # rotate(angle, cx, cy) == translate(cx, cy) rotate translate(-cx, -cy)
    return _multiply(_multiply(_translate(cx, cy), rot),
                     _translate(-cx, -cy))


def _skew_x(angle):
    return (1.0, 0.0, math.tan(math.radians(angle)), 1.0, 0.0, 0.0)


def _skew_y(angle):
    return (1.0, math.tan(math.radians(angle)), 0.0, 1.0, 0.0, 0.0)


_TRANSFORM_RE = re.compile(
    r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_NUMBER_SPLIT_RE = re.compile(r"[,\s]+")


def parse_transform(transform):
    """Parse an SVG ``transform`` attribute into an affine matrix.

    :raises BoundingBoxError: if the transform-list cannot be parsed
    """
    if not transform:
        return IDENTITY
    matrix = IDENTITY
    pos = 0
    text = transform.strip()
    while pos < len(text):
        match = _TRANSFORM_RE.match(text, pos)
        if not match or match.start() != pos:
            raise BoundingBoxError(
                "unparseable transform attribute: %r" % transform)
        cmd = match.group(1)
        raw_args = match.group(2).strip()
        args = [_parse_number(token, "transform")
                for token in _NUMBER_SPLIT_RE.split(raw_args) if token]
        if cmd == 'matrix':
            if len(args) != 6:
                raise BoundingBoxError(
                    "matrix() requires 6 arguments: %r" % transform)
            step = tuple(args)
        elif cmd == 'translate':
            if len(args) not in (1, 2):
                raise BoundingBoxError(
                    "translate() requires 1 or 2 arguments: %r" % transform)
            step = _translate(*args)
        elif cmd == 'scale':
            if len(args) not in (1, 2):
                raise BoundingBoxError(
                    "scale() requires 1 or 2 arguments: %r" % transform)
            step = _scale(*args)
        elif cmd == 'rotate':
            if len(args) not in (1, 3):
                raise BoundingBoxError(
                    "rotate() requires 1 or 3 arguments: %r" % transform)
            step = _rotate(*args)
        elif cmd == 'skewX':
            if len(args) != 1:
                raise BoundingBoxError(
                    "skewX() requires 1 argument: %r" % transform)
            step = _skew_x(args[0])
        else:  # skewY
            if len(args) != 1:
                raise BoundingBoxError(
                    "skewY() requires 1 argument: %r" % transform)
            step = _skew_y(args[0])
        matrix = _multiply(matrix, step)
        pos = match.end()
        while pos < len(text) and text[pos] in " \t\n\r,":
            pos += 1
    return matrix


# ---------------------------------------------------------------------------
# number parsing
# ---------------------------------------------------------------------------

_UNIT_RE = re.compile(r"^([+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?)([a-z%]+)?$")


def _parse_number(value, context="coordinate"):
    """Parse an attribute value as a plain user-space number.

    A trailing ``px`` unit is accepted (user units are equivalent to px);
    any other unit or non numeric value raises :class:`InvalidCoordinateError`.
    """
    if isinstance(value, bool):  # bool is an int subclass -- reject it
        raise InvalidCoordinateError(
            "invalid %s value: %r" % (context, value))
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        match = _UNIT_RE.match(value.strip())
        if not match:
            raise InvalidCoordinateError(
                "invalid %s value: %r" % (context, value))
        number = float(match.group(1))
        unit = match.group(4)
        if unit is not None and unit != 'px':
            raise InvalidCoordinateError(
                "cannot evaluate %s with unit %r; only unit-less numbers "
                "and 'px' are supported" % (context, unit))
    else:
        raise InvalidCoordinateError(
            "invalid %s value: %r" % (context, value))
    if not math.isfinite(number):
        raise InvalidCoordinateError(
            "non-finite %s value: %r" % (context, value))
    return number


def _required_number(element, name):
    try:
        value = element.attribs[name]
    except KeyError:
        raise InvalidCoordinateError(
            "<%s> is missing required attribute %r"
            % (element.elementname, name))
    return _parse_number(value, name)


# ---------------------------------------------------------------------------
# bezier extremum helpers
#
# Bounds are always evaluated in *root* space: the affine transform is
# applied to every control point first (affine maps preserve bezier
# polygons), then the extrema of the resulting 1-D component polynomials
# are solved analytically.
# ---------------------------------------------------------------------------

def _cubic_roots(a, b, c):
    """Real roots of a*t^2 + b*t + c = 0 within the open interval (0, 1)."""
    roots = []
    if abs(a) < 1e-12:
        if abs(b) >= 1e-12:
            t = -c / b
            if 0.0 < t < 1.0:
                roots.append(t)
        return roots
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return roots
    disc = math.sqrt(disc)
    for t in ((-b - disc) / (2.0 * a), (-b + disc) / (2.0 * a)):
        if 0.0 < t < 1.0:
            roots.append(t)
    return roots


def _cubic_extrema(p0, p1, p2, p3):
    """Return all extrema parameter values of a root-space cubic bezier
    in both the x and y component."""
    result = []
    for i in (0, 1):
        v0, v1, v2, v3 = p0[i], p1[i], p2[i], p3[i]
        # B'(t) = 3(1-t)^2 (v1-v0) + 6(1-t)t (v2-v1) + 3t^2 (v3-v2)
        d01 = v1 - v0
        d12 = v2 - v1
        d23 = v3 - v2
        a = 3.0 * (d01 - 2.0 * d12 + d23)
        b = 6.0 * (d12 - d01)
        c = 3.0 * d01
        result.extend(_cubic_roots(a, b, c))
    return result


def _quadratic_to_cubic(p0, p1, p2):
    """Degree elevation: quadratic control polygon -> cubic control polygon."""
    c1 = (p0[0] + 2.0 / 3.0 * (p1[0] - p0[0]),
          p0[1] + 2.0 / 3.0 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2.0 / 3.0 * (p1[0] - p2[0]),
          p2[1] + 2.0 / 3.0 * (p1[1] - p2[1]))
    return p0, c1, c2, p2


def _cubic_point(p0, p1, p2, p3, t):
    mt = 1.0 - t
    x = (mt ** 3 * p0[0] + 3.0 * mt ** 2 * t * p1[0]
         + 3.0 * mt * t ** 2 * p2[0] + t ** 3 * p3[0])
    y = (mt ** 3 * p0[1] + 3.0 * mt ** 2 * t * p1[1]
         + 3.0 * mt * t ** 2 * p2[1] + t ** 3 * p3[1])
    return x, y


def _add_cubic(box, p0, p1, p2, p3):
    """Add the exact bounds of a cubic bezier given by root-space
    control points."""
    box.add_point(*p0)
    box.add_point(*p3)
    for t in _cubic_extrema(p0, p1, p2, p3):
        box.add_point(*_cubic_point(p0, p1, p2, p3, t))


def _add_quadratic(box, p0, p1, p2):
    _add_cubic(box, *_quadratic_to_cubic(p0, p1, p2))


# ---------------------------------------------------------------------------
# stroke handling
# ---------------------------------------------------------------------------

def _stroke_width(element, inherited):
    """Return the stroke width if the element is stroked, else 0.

    Presentation attributes (``stroke``, ``stroke-width``) are inherited
    from ancestor groups per SVG rules.  The value is expressed in the
    element's local user coordinate system.

    :raises InvalidCoordinateError: for non numeric stroke-width values
    """
    stroke = element.attribs.get('stroke', inherited.get('stroke'))
    if stroke is None or stroke == 'none':
        return 0.0
    width = element.attribs.get(
        'stroke-width', inherited.get('stroke-width'))
    if width is None:
        return 1.0  # SVG initial value
    width = _parse_number(width, 'stroke-width')
    if width < 0.0:
        raise InvalidCoordinateError(
            "stroke-width must not be negative: %r"
            % element.attribs.get('stroke-width'))
    return width


def _expand_for_stroke(box, element, matrix, inherited):
    """Grow an already computed root-space box by the half stroke width.

    The offset is the length of the transformed unit normal vector, which
    is a correct bound for every stroke under an arbitrary affine
    transformation (non-uniform scale, rotation, skew).
    """
    width = _stroke_width(element, inherited)
    if width <= 0.0:
        return box
    half = width / 2.0
    a, b, c, d = matrix[:4]
    offset_x = half * math.hypot(a, b)
    offset_y = half * math.hypot(c, d)
    box.minx -= offset_x
    box.maxx += offset_x
    box.miny -= offset_y
    box.maxy += offset_y
    return box


# ---------------------------------------------------------------------------
# per-element geometry (all bounds are computed directly in root space)
# ---------------------------------------------------------------------------

def _rect_bounds(element, matrix, inherited):
    x = _required_number(element, 'x')
    y = _required_number(element, 'y')
    width = _required_number(element, 'width')
    height = _required_number(element, 'height')
    if width < 0.0 or height < 0.0:
        raise InvalidCoordinateError(
            "rect width/height must not be negative")
    box = BoundingBox()
    # rounded corners stay inside the plain rectangle, so the four corners
    # of the rect remain its extreme points
    for lx, ly in ((x, y), (x + width, y),
                   (x + width, y + height), (x, y + height)):
        box.add_point(*_apply(matrix, lx, ly))
    return _expand_for_stroke(box, element, matrix, inherited)


def _ellipse_bounds(element, matrix, circular, inherited):
    cx = _required_number(element, 'cx')
    cy = _required_number(element, 'cy')
    if circular:
        rx = ry = _required_number(element, 'r')
    else:
        rx = _required_number(element, 'rx')
        ry = _required_number(element, 'ry')
    if rx < 0.0 or ry < 0.0:
        raise InvalidCoordinateError(
            "ellipse/circle radii must not be negative")
    a, b, c, d, e, f = matrix
    center_x, center_y = _apply(matrix, cx, cy)
    # exact extents of an affine mapped axis-aligned ellipse
    extent_x = math.hypot(rx * a, ry * c)
    extent_y = math.hypot(rx * b, ry * d)
    box = BoundingBox(center_x - extent_x, center_y - extent_y,
                      center_x + extent_x, center_y + extent_y)
    return _expand_for_stroke(box, element, matrix, inherited)


def _line_bounds(element, matrix, inherited):
    x1 = _required_number(element, 'x1')
    y1 = _required_number(element, 'y1')
    x2 = _required_number(element, 'x2')
    y2 = _required_number(element, 'y2')
    box = BoundingBox()
    box.add_point(*_apply(matrix, x1, y1))
    box.add_point(*_apply(matrix, x2, y2))
    return _expand_for_stroke(box, element, matrix, inherited)


def _point_bounds(element, matrix, points):
    box = BoundingBox()
    for point in points:
        try:
            x, y = point
        except (TypeError, ValueError):
            raise InvalidCoordinateError(
                "invalid point in <%s>: %r" % (element.elementname, point))
        box.add_point(*_apply(matrix, _parse_number(x, 'point'),
                              _parse_number(y, 'point')))
    return box


def _polyline_bounds(element, matrix, inherited):
    points = getattr(element, 'points', None)
    if not points:
        raise InvalidCoordinateError(
            "<%s> has no points" % element.elementname)
    box = _point_bounds(element, matrix, points)
    return _expand_for_stroke(box, element, matrix, inherited)


# ---------------------------------------------------------------------------
# path parsing
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"([a-zA-Z])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")


def _tokenize_path(d):
    tokens = []
    pos = 0
    length = len(d)
    while pos < length:
        char = d[pos]
        if char in " \t\n\r,":
            pos += 1
            continue
        match = _TOKEN_RE.match(d, pos)
        if not match:
            raise PathParseError(
                "unexpected character %r in path data: %r"
                % (d[pos], d))
        if match.group(1) is not None:
            tokens.append(('cmd', match.group(1)))
        else:
            tokens.append(('num', float(match.group(2))))
        pos = match.end()
    return tokens


def _read_number(tokens, index, d):
    if index >= len(tokens) or tokens[index][0] != 'num':
        raise PathParseError(
            "missing coordinate at token %d in path data: %r" % (index, d))
    return tokens[index][1], index + 1


def _read_point(tokens, index, d):
    x, index = _read_number(tokens, index, d)
    y, index = _read_number(tokens, index, d)
    return (x, y), index


def _path_bounds(element, matrix, inherited):
    # strlist() renders the exact d attribute without calling get_xml(),
    # so the element and its serialization order stay untouched
    d = strlist(element.commands, ' ')
    if not d:
        raise InvalidCoordinateError("<path> has no 'd' data")
    tokens = _tokenize_path(d)

    box = BoundingBox()
    # the state machine tracks points in local user space; each segment's
    # control points are mapped into root space before its bounds are solved
    current = None          # current point (local user space)
    start = None            # sub-path start point (local user space)
    prev_cubic = None       # previous cubic control point (local space)
    prev_quad = None        # previous quadratic control point (local space)
    last_cmd = None
    index = 0

    def root(point):
        return _apply(matrix, point[0], point[1])

    while index < len(tokens):
        kind, value = tokens[index]
        if kind == 'cmd':
            cmd = value
            index += 1
        else:
            # implicit repeat of the previous command; an implicit moveto
            # becomes a lineto per SVG spec
            if last_cmd is None:
                raise PathParseError(
                    "path data does not start with a moveto: %r" % d)
            cmd = 'L' if last_cmd.upper() == 'M' else last_cmd
        upper = cmd.upper()
        relative = cmd.islower()

        def resolve(point):
            if relative and current is not None:
                return (current[0] + point[0], current[1] + point[1])
            return point

        if upper == 'M':
            point, index = _read_point(tokens, index, d)
            current = resolve(point)
            start = current
            box.add_point(*root(current))
            prev_cubic = prev_quad = None
        elif upper == 'L':
            point, index = _read_point(tokens, index, d)
            if current is None:
                raise PathParseError(
                    "lineto before moveto in path data: %r" % d)
            current = resolve(point)
            box.add_point(*root(current))
            prev_cubic = prev_quad = None
        elif upper == 'T':
            point, index = _read_point(tokens, index, d)
            if current is None:
                raise PathParseError(
                    "lineto before moveto in path data: %r" % d)
            if prev_quad is None:
                control = current
            else:
                control = (2.0 * current[0] - prev_quad[0],
                           2.0 * current[1] - prev_quad[1])
            end = resolve(point)
            _add_quadratic(box, root(current), root(control), root(end))
            prev_quad = control
            prev_cubic = None
            current = end
        elif upper == 'H':
            x, index = _read_number(tokens, index, d)
            if current is None:
                raise PathParseError(
                    "lineto before moveto in path data: %r" % d)
            if relative:
                x += current[0]
            current = (x, current[1])
            box.add_point(*root(current))
            prev_cubic = prev_quad = None
        elif upper == 'V':
            y, index = _read_number(tokens, index, d)
            if current is None:
                raise PathParseError(
                    "lineto before moveto in path data: %r" % d)
            if relative:
                y += current[1]
            current = (current[0], y)
            box.add_point(*root(current))
            prev_cubic = prev_quad = None
        elif upper == 'C':
            if current is None:
                raise PathParseError(
                    "curveto before moveto in path data: %r" % d)
            c1, index = _read_point(tokens, index, d)
            c2, index = _read_point(tokens, index, d)
            end, index = _read_point(tokens, index, d)
            c1 = resolve(c1)
            c2 = resolve(c2)
            end = resolve(end)
            _add_cubic(box, root(current), root(c1), root(c2), root(end))
            current = end
            prev_cubic = c2
            prev_quad = None
        elif upper == 'S':
            if current is None:
                raise PathParseError(
                    "curveto before moveto in path data: %r" % d)
            c2, index = _read_point(tokens, index, d)
            end, index = _read_point(tokens, index, d)
            if prev_cubic is None:
                c1 = current
            else:
                c1 = (2.0 * current[0] - prev_cubic[0],
                      2.0 * current[1] - prev_cubic[1])
            c2 = resolve(c2)
            end = resolve(end)
            _add_cubic(box, root(current), root(c1), root(c2), root(end))
            current = end
            prev_cubic = c2
            prev_quad = None
        elif upper == 'Q':
            if current is None:
                raise PathParseError(
                    "quadratic curveto before moveto in path data: %r" % d)
            control, index = _read_point(tokens, index, d)
            end, index = _read_point(tokens, index, d)
            control = resolve(control)
            end = resolve(end)
            _add_quadratic(box, root(current), root(control), root(end))
            current = end
            prev_quad = control
            prev_cubic = None
        elif upper == 'Z':
            if start is None:
                raise PathParseError(
                    "closepath before moveto in path data: %r" % d)
            current = start
            prev_cubic = prev_quad = None
        elif upper == 'A':
            raise UnsupportedElementError(
                "elliptical arc commands (A/a) are not supported for "
                "bounding box calculation; path: %r" % d)
        else:
            raise PathParseError(
                "unknown path command %r in path data: %r" % (cmd, d))
        last_cmd = cmd

    if box.empty:
        raise PathParseError("path data contains no geometry: %r" % d)
    return _expand_for_stroke(box, element, matrix, inherited)


# ---------------------------------------------------------------------------
# tree traversal
# ---------------------------------------------------------------------------

_SHAPE_DISPATCH = {
    'rect': _rect_bounds,
    'circle': lambda elem, matrix, inherited:
        _ellipse_bounds(elem, matrix, True, inherited),
    'ellipse': lambda elem, matrix, inherited:
        _ellipse_bounds(elem, matrix, False, inherited),
    'line': _line_bounds,
    'polyline': _polyline_bounds,
    'polygon': _polyline_bounds,
    'path': _path_bounds,
}

# structural / non-rendering elements that are skipped or recursed into
_CONTAINER_NAMES = frozenset((
    'g', 'a', 'defs', 'clipPath', 'mask', 'marker', 'pattern', 'symbol',
    'linearGradient', 'radialGradient', 'solidColor', 'style', 'script',
    'title', 'desc', 'metadata', 'switch',
))

# animation elements do not change the static geometry themselves, but
# animation can move geometry at runtime, so measuring them is refused
_ANIMATION_NAMES = frozenset((
    'animate', 'animateMotion', 'animateTransform', 'animateColor', 'set',
))

_UNSUPPORTED_HINT = {
    'text': 'text extent depends on font rendering and cannot be measured',
    'tspan': 'text extent depends on font rendering and cannot be measured',
    'tref': 'text extent depends on font rendering and cannot be measured',
    'textPath': 'text extent depends on font rendering and cannot be measured',
    'textArea': 'text extent depends on font rendering and cannot be measured',
    'tbreak': 'text extent depends on font rendering and cannot be measured',
    'image': 'external image content has no inspectable geometry',
    'use': 'references are not resolved during bounding box calculation',
    'animate': 'animated geometry may change at runtime and is not measured',
    'animateMotion': 'animated geometry may change at runtime and is not measured',
    'animateTransform': 'animated geometry may change at runtime and is not measured',
    'animateColor': 'animated geometry may change at runtime and is not measured',
    'set': 'animated geometry may change at runtime and is not measured',
}

# presentation attributes inherited by descendants per SVG rules
_INHERITED_ATTRS = ('stroke', 'stroke-width')


def _element_matrix(element, parent_matrix, nested=False):
    """Combine the parent matrix with the element's own transform.

    A nested ``svg`` fragment additionally translates by its x/y origin;
    nested fragments with their own *viewBox* establish a new coordinate
    system that cannot be evaluated here.
    """
    matrix = parent_matrix
    if element.elementname == 'svg' and nested:
        if 'viewBox' in element.attribs:
            raise UnsupportedElementError(
                "nested <svg> elements with a viewBox are not supported")
        x = _parse_number(element.attribs.get('x', 0.0), 'x')
        y = _parse_number(element.attribs.get('y', 0.0), 'y')
        matrix = _multiply(matrix, _translate(x, y))
    transform = element.attribs.get('transform')
    if transform:
        matrix = _multiply(matrix, parse_transform(transform))
    return matrix


def _inherited_presentation(element, parent_inherited):
    """Resolve the presentation context a child element inherits."""
    inherited = dict(parent_inherited)
    for attr in _INHERITED_ATTRS:
        if attr in element.attribs:
            inherited[attr] = element.attribs[attr]
    return inherited


def _walk(element, matrix, box, inherited=None):
    if inherited is None:
        inherited = {}
    name = getattr(element, 'elementname', '')
    if not name or not hasattr(element, 'attribs'):
        # Title/Desc/Metadata style objects are non-rendering metadata
        return

    if name in _SHAPE_DISPATCH:
        shape_matrix = _element_matrix(element, matrix, nested=True)
        box.add_box(
            _SHAPE_DISPATCH[name](element, shape_matrix, inherited))
        # shapes may carry non-rendering children (e.g. <animate>); walk
        # them as well so unsupported children are reported instead of
        # being silently ignored
        child_inherited = _inherited_presentation(element, inherited)
        for child in element.elements:
            _walk(child, shape_matrix, box, child_inherited)
        return

    if name in _ANIMATION_NAMES:
        raise UnsupportedElementError(
            "<%s>: %s" % (name, _UNSUPPORTED_HINT[name]))

    if name in _CONTAINER_NAMES or name == 'svg':
        if name == 'defs':
            # referenced definitions are not rendered directly
            return
        child_matrix = _element_matrix(element, matrix, nested=True)
        child_inherited = _inherited_presentation(element, inherited)
        for child in element.elements:
            _walk(child, child_matrix, box, child_inherited)
        return

    hint = _UNSUPPORTED_HINT.get(name)
    if hint is None:
        hint = "element type is not supported"
    raise UnsupportedElementError(
        "<%s>: %s" % (name, hint))


def calculate_bounds(drawing):
    """Calculate the visible bounding box of *drawing*.

    :param drawing: a :class:`svgwrite.Drawing` (or any container element)
    :returns: :class:`BoundingBox` in root canvas coordinates, including
      half the stroke width of every stroked element (stroke presentation
      attributes set on ancestor groups are inherited)
    :raises EmptyDrawingError: when no supported visible shape exists
    :raises InvalidCoordinateError: for coordinates that are not plain
      user-space numbers
    :raises PathParseError: for unparseable path data
    :raises UnsupportedElementError: for ``text``, ``image``, ``use`` and
      other elements without computable geometry
    """
    box = BoundingBox()
    matrix = _element_matrix(drawing, IDENTITY)
    inherited = _inherited_presentation(drawing, {})
    for child in drawing.elements:
        _walk(child, matrix, box, inherited)
    if box.empty:
        raise EmptyDrawingError(
            "drawing contains no supported visible geometry")
    return box


def fit_to_content(drawing, margin=0.0):
    """Recalculate the *viewBox* of *drawing* from its content.

    :param drawing: a :class:`svgwrite.Drawing`
    :param margin: a single number applied on all four sides or a
      ``(horizontal, vertical)`` tuple
    :returns: the margin-adjusted :class:`BoundingBox`
    :raises BoundingBoxError: see :func:`calculate_bounds`

    Only the *viewBox* attribute is changed; the drawing size, the
    contained elements and their serialization order are not modified.
    """
    box = calculate_bounds(drawing)
    box.add_margin(margin)
    drawing.viewbox(*box.as_viewbox())
    return box
