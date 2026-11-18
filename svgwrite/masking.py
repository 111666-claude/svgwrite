#!/usr/bin/env python
#coding:utf-8
# Author:  mozman --<mozman@gmx.at>
# Purpose: masking module
# Created: 30.10.2010
# Copyright (C) 2010, Manfred Moitzi
# License: MIT License

import re

from svgwrite.base import BaseElement
from svgwrite.mixins import Transform
from svgwrite.path import Path
from svgwrite.utils import is_string, strlist


class ClipPath(BaseElement, Transform):
    """
    The clipping path restricts the region to which paint can be applied.
    Conceptually, any parts of the drawing that lie outside of the region
    bounded by the currently active clipping path are not drawn. A clipping
    path can be thought of as a mask wherein those pixels outside the clipping
    path are black with an alpha value of zero and those pixels inside the
    clipping path are white with an alpha value of one (with the possible
    exception of anti-aliasing along the edge of the silhouette).

    A **clipPath** element can contain **path** elements, **text** elements,
    basic shapes (such as **circle**) or a **use** element. If a **use**
    element is a child of a **clipPath** element, it must directly reference
    **path**, **text** or basic shape elements. Indirect references are an
    error.
    """
    elementname = 'clipPath'


class Mask(BaseElement):
    """
    In SVG, you can specify that any other graphics object or **g** element
    can be used as an alpha mask for compositing the current object into the
    background.

    A **mask** can contain any graphical elements or container elements such
    as a **g**.
    """
    elementname = 'mask'

    def __init__(self, start=None, size=None, **extra):
        super(Mask, self).__init__(**extra)
        if start is not None:
            self['x'] = start[0]
            self['y'] = start[1]
        if size is not None:
            self['width'] = size[0]
            self['height'] = size[1]


# ---------------------------------------------------------------------------
# objectBoundingBox clipPath construction
# ---------------------------------------------------------------------------
#
# Build a reusable <clipPath clipPathUnits="objectBoundingBox"> from an
# absolute path and a target rectangle.  The path coordinates are normalized
# into the [0, 1] coordinate space of the target rectangle, so a single
# clipping shape (e.g. a cloud icon) can be shared by many target elements
# (rect, image, group) of different sizes.

_PATH_TOKEN_RE = re.compile(
    r"([AaCcHhLlMmQqSsTtVvZz])"
    r"|([-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?)(?:[eE][-+]?[0-9]+)?)"
)

# number of numeric arguments per (absolute) path command
_PATH_ARG_COUNT = {
    'M': 2, 'L': 2, 'T': 2,
    'H': 1, 'V': 1,
    'C': 6, 'S': 4, 'Q': 4,
    'A': 7,
}

# commands whose argument groups are (x, y) coordinate pairs
_PATH_PAIR_COMMANDS = frozenset(['M', 'L', 'T'])
_PATH_TWO_PAIR_COMMANDS = frozenset(['S', 'Q'])


def _is_path_command(token):
    return len(token) == 1 and token in 'AaCcHhLlMmQqSsTtVvZz'


def _tokenize_path_data(d):
    """ Split path data string `d` into command letters and numbers.

    :raises ValueError: on unexpected characters
    """
    tokens = []
    pos = 0
    end = len(d)
    while pos < end:
        char = d[pos]
        if char.isspace() or char == ',':
            pos += 1
            continue
        match = _PATH_TOKEN_RE.match(d, pos)
        if match is None:
            raise ValueError(
                "invalid path data at position %d: %r" % (pos, d[pos:pos + 10]))
        tokens.append(match.group(0))
        pos = match.end()
    return tokens


def _parse_absolute_path(d):
    """ Parse path data string `d` into a list of (letter, args) tuples.

    Only absolute commands (uppercase letters) are accepted, because
    normalizing relative commands into objectBoundingBox space requires
    tracking the current point through nested transformations.

    :raises ValueError: on relative commands or malformed path data
    """
    tokens = _tokenize_path_data(d)
    if not tokens:
        raise ValueError("empty path data")
    if not _is_path_command(tokens[0]):
        raise ValueError("path data must start with a command letter")
    commands = []
    index = 0
    count = len(tokens)
    letter = None
    moveto_pending = False
    while index < count:
        token = tokens[index]
        if _is_path_command(token):
            letter = token
            index += 1
            if letter in 'Zz':
                commands.append(('Z', ()))
                letter = None
                moveto_pending = False
                continue
            if letter.islower():
                raise ValueError(
                    "relative path command %r is not supported, "
                    "use absolute commands only" % letter)
            moveto_pending = (letter == 'M')
        elif letter is None:  # number without a preceding command
            raise ValueError(
                "path data must start with a command letter")
        arity = _PATH_ARG_COUNT[letter]
        args = tokens[index:index + arity]
        if len(args) < arity or any(_is_path_command(arg) for arg in args):
            raise ValueError(
                "not enough arguments for path command %r" % letter)
        try:
            args = tuple(float(arg) for arg in args)
        except ValueError:
            raise ValueError(
                "invalid numeric argument for path command %r" % letter)
        index += arity
        if letter == 'A':
            _validate_arc_args(args)
        commands.append((letter, args))
        if moveto_pending:
            # implicit coordinate pairs after 'M' are lineto commands
            letter = 'L'
            moveto_pending = False
    return commands


def _validate_arc_args(args):
    large_arc, sweep = args[3], args[4]
    if large_arc not in (0, 1) or sweep not in (0, 1):
        raise ValueError(
            "arc flags must be 0 or 1, got %r" % (args,))
    if args[0] < 0 or args[1] < 0:
        raise ValueError("arc radii must not be negative")


def _validate_bounds(bounds):
    """ Check the target rectangle and return it as (x, y, width, height).

    :raises ValueError: for malformed, zero-sized or negative bounds
    """
    try:
        x, y, width, height = bounds
    except (TypeError, ValueError):
        raise ValueError(
            "bounds must be a 4-tuple (x, y, width, height), got %r"
            % (bounds,))
    for value in (x, y, width, height):
        if not isinstance(value, (int, float)):
            raise ValueError(
                "bounds values must be numbers, got %r" % (value,))
    if width == 0 or height == 0:
        raise ValueError(
            "target rectangle has zero width or height: %r" % (bounds,))
    if width < 0 or height < 0:
        raise ValueError(
            "target rectangle has negative width or height: %r" % (bounds,))
    if x < 0 or y < 0:
        raise ValueError(
            "target rectangle has negative coordinates: %r" % (bounds,))
    return x, y, width, height


def _format_number(value):
    text = '%.6f' % value
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('', '-0'):
        text = '0'
    return text


def _normalize_commands(commands, bounds):
    """ Normalize absolute path `commands` into the [0, 1] space of `bounds`.
    """
    x, y, width, height = bounds

    def norm_x(value):
        return (value - x) / width

    def norm_y(value):
        return (value - y) / height

    normalized = []
    for letter, args in commands:
        if letter in _PATH_PAIR_COMMANDS:
            normalized.append((letter, (norm_x(args[0]), norm_y(args[1]))))
        elif letter == 'H':
            normalized.append((letter, (norm_x(args[0]),)))
        elif letter == 'V':
            normalized.append((letter, (norm_y(args[0]),)))
        elif letter == 'C':
            normalized.append((letter, (
                norm_x(args[0]), norm_y(args[1]),
                norm_x(args[2]), norm_y(args[3]),
                norm_x(args[4]), norm_y(args[5]),
            )))
        elif letter in _PATH_TWO_PAIR_COMMANDS:
            normalized.append((letter, (
                norm_x(args[0]), norm_y(args[1]),
                norm_x(args[2]), norm_y(args[3]),
            )))
        elif letter == 'A':
            normalized.append((letter, (
                args[0] / width, args[1] / height, args[2],
                int(args[3]), int(args[4]),
                norm_x(args[5]), norm_y(args[6]),
            )))
        else:  # 'Z'
            normalized.append((letter, ()))
    return normalized


def _commands_to_string(commands):
    parts = []
    for letter, args in commands:
        parts.append(letter)
        parts.extend(_format_number(arg) for arg in args)
    return ' '.join(parts)


def normalize_path_data(d, bounds):
    """ Normalize absolute path data string `d` into the objectBoundingBox
    space of the target rectangle `bounds` = (x, y, width, height).

    :param string d: path data, absolute commands only
    :param bounds: 4-tuple (x, y, width, height) of the target rectangle
    :returns: normalized path data string with coordinates in [0, 1] space

    :raises ValueError: for invalid path data, relative commands and
        zero-sized or negative target rectangles
    """
    bounds = _validate_bounds(bounds)
    commands = _parse_absolute_path(d)
    return _commands_to_string(_normalize_commands(commands, bounds))


def _extract_path_data(path):
    """ Get the absolute path data string from `path`.

    :param path: path data string or :class:`svgwrite.path.Path` object
    :raises ValueError: if the path carries a (nested) transformation
    :raises TypeError: for unsupported path objects
    """
    if is_string(path):
        return path
    if isinstance(path, Path):
        if 'transform' in path.attribs:
            raise ValueError(
                "nested transformations are not supported: the source path "
                "must not carry a 'transform' attribute")
        if path.commands:
            return strlist(path.commands, ' ')
        d = path.attribs.get('d')
        if d:
            return d
        raise ValueError("path object contains no path data")
    raise TypeError(
        "path must be a path data string or a Path object, got %r"
        % type(path).__name__)


def _iter_def_ids(element):
    element_id = element.attribs.get('id')
    if element_id is not None:
        yield element_id
    for child in getattr(element, 'elements', ()):
        for child_id in _iter_def_ids(child):
            yield child_id


def object_bounding_box_clip(drawing, path, bounds, id=None):
    """ Create (or reuse) a reusable :class:`ClipPath` with
    ``clipPathUnits='objectBoundingBox'`` in the *defs* section of `drawing`.

    The absolute `path` (a path data string or a :class:`svgwrite.path.Path`
    object) is normalized into the [0, 1] coordinate space of the target
    rectangle `bounds`.  The source path object is never modified.  Calling
    this function again with a path and bounds that normalize to the same
    result returns the already registered clipPath instead of adding a
    duplicate definition.

    :param drawing: a :class:`svgwrite.Drawing` (or any object with a
        ``defs`` container)
    :param path: absolute path data string or Path object
    :param bounds: 4-tuple (x, y, width, height) of the target rectangle
    :param string id: optional explicit id for the clipPath element
    :returns: the :class:`ClipPath` element stored in ``drawing.defs``

    :raises ValueError: for invalid path data, relative path commands,
        nested transformations on the source path, zero-sized or negative
        target rectangles and duplicate ids
    """
    defs = getattr(drawing, 'defs', None)
    if defs is None:
        raise TypeError("drawing must provide a 'defs' container")
    registry = drawing.__dict__.setdefault('_object_box_clip_registry', {})
    normalized_d = normalize_path_data(_extract_path_data(path), bounds)
    existing = registry.get(normalized_d)
    if existing is not None:
        if id is not None and existing.get_id() != id:
            raise ValueError(
                "duplicate id %r: an identical clipPath with id %r already "
                "exists" % (id, existing.get_id()))
        return existing
    if id is not None and id in set(_iter_def_ids(defs)):
        raise ValueError(
            "duplicate id %r: an element with this id already exists in "
            "the defs section" % id)
    clip = ClipPath(clipPathUnits='objectBoundingBox', factory=drawing)
    if id is not None:
        clip['id'] = id
    clip.add(Path(d=normalized_d, factory=drawing))
    defs.add(clip)
    registry[normalized_d] = clip
    return clip


def apply_clip_path(element, clip_path):
    """ Apply `clip_path` to `element` (e.g. rect, image or group) by
    setting its ``clip-path`` attribute to a stable ``url(#id)`` reference.

    :param element: the target element (rect, image, group, ...)
    :param clip_path: a :class:`ClipPath` element
    :returns: `element`

    :raises TypeError: if `clip_path` is not a :class:`ClipPath`
    """
    if not isinstance(clip_path, ClipPath):
        raise TypeError(
            "clip_path must be a ClipPath element, got %r"
            % type(clip_path).__name__)
    element['clip-path'] = clip_path.get_funciri()
    return element
