#!/usr/bin/env python
#coding:utf-8
# Author:  mozman
# Purpose: shared CSS class registry for presentation attributes
# Created: 18.11.2026
# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
"""
The **styling** module provides the :class:`StyleRegistry`, a shared style
registration that collapses repeated presentation attributes into reusable
CSS classes.

A map with thousands of markers that all share the same ``fill`` and
``stroke`` does not have to repeat those attributes on every element.
Instead the presentation attributes are registered once as a CSS rule in
a ``<style>`` element inside the ``<defs>`` section and the elements just
reference a stable class name::

    dwg = svgwrite.Drawing('map.svg')
    registry = dwg.style_registry
    marker_style = registry.register({'fill': 'red', 'stroke': 'black'})
    rect = dwg.rect(insert=(0, 0), size=(10, 10))
    registry.attach(rect, marker_style)

Equivalent styles share one rule -- registering the same property/value
mapping again returns the very same class name and does not create a
second rule.

Cascade note: per the SVG specification presentation attributes have a
*lower* priority than author CSS (the generated class rules). To keep the
intuitive rule "an explicit local attribute overrides the class",
:meth:`StyleRegistry.attach` moves conflicting presentation attributes
into the inline ``style`` attribute, which has a higher priority than
the generated stylesheet.
"""

from svgwrite.data import full11
from svgwrite.data import tiny12
from svgwrite.etree import CDATA
from svgwrite.utils import is_string
from svgwrite.validator2 import get_validator

# presentation attributes supported as reusable CSS classes, per profile
PRESENTATION_PROPERTIES = {
    'full': frozenset(full11.presentation_attributes),
    'basic': frozenset(full11.presentation_attributes),
    'none': frozenset(full11.presentation_attributes),
    'tiny': frozenset(tiny12.property_names) |
            frozenset(tiny12.media_group_names),
}

# characters that would break the generated CSS text or smuggle additional
# declarations/rules into the stylesheet
_CSS_FORBIDDEN = set(';{}')
# a (subset of a) valid CSS identifier as class name: start with a letter or
# underscore, followed by letters, digits, underscores or hyphens
_CSS_IDENT_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789_-')

DEFAULT_CLASS_PREFIX = 'sw-style'


def normalize_property_name(name):
    """ Normalize a keyword style property name.

    Mirrors :meth:`svgwrite.base.BaseElement.update`: trailing underscores
    are stripped and inner underscores are replaced by hyphens
    (``'stroke_width'`` -> ``'stroke-width'``).
    """
    return str(name).rstrip('_').replace('_', '-')


def _is_valid_class_name(name):
    if not is_string(name) or not name:
        return False
    if name[0] in '0123456789-' or name[0] not in _CSS_IDENT_CHARS:
        return False
    return all(char in _CSS_IDENT_CHARS for char in name)


class _RegistryStyle(object):
    """ The ``<style>`` element that renders the current registry state.

    Unlike :class:`svgwrite.container.Style` the CSS text is rendered lazily
    from the registry at serialization time, so registrations stay effective
    regardless of when they happen.
    """
    elementname = 'style'

    def __init__(self, registry):
        self._registry = registry
        self.attribs = {'type': 'text/css'}
        self.elements = []

    def get_xml(self):
        from svgwrite.etree import etree
        xml = etree.Element(self.elementname)
        xml.set('type', 'text/css')
        # CDATA keeps the CSS verbatim, any ']]>' sequence inside a value was
        # rejected while the rule was registered
        xml.append(CDATA(self._registry.get_css_text()))
        return xml

    def tostring(self):
        # same serialization path as BaseElement.tostring, incl. the CDATA
        # patch installed in svgwrite.etree
        from svgwrite.etree import etree
        xml_utf8_str = etree.tostring(self.get_xml(), encoding='utf-8')
        return xml_utf8_str.decode('utf-8')


class StyleRegistry(object):
    """ Registry for shared presentation-attribute styles.

    Presentation attributes are registered as reusable CSS classes and
    emitted once as a ``<style>`` element inside the drawing's ``<defs>``
    section. Equivalent styles (same property/value mapping) share one rule
    and one stable class name.

    :param drawing: the owning :class:`svgwrite.Drawing`, used to access the
        active profile and the ``<defs>`` section; can be omitted for a
        standalone registry
    :param str profile: ``'full'`` (also ``'basic'`` and ``'none'``) or
        ``'tiny'`` -- selects the supported presentation properties; defaults
        to the drawing profile or ``'full'``
    :param bool debug: validate registered values with the svgwrite
        validator; defaults to the drawing's debug setting, otherwise `True`
    """

    def __init__(self, drawing=None, profile=None, debug=None):
        self._drawing = drawing
        if profile is None:
            profile = drawing.profile if drawing is not None else 'full'
        if profile not in PRESENTATION_PROPERTIES:
            raise ValueError("Unsupported profile: '%s'" % profile)
        self.profile = profile
        if debug is None:
            debug = drawing.debug if drawing is not None else True
        self.debug = debug
        self._validator = get_validator(profile, debug)
        self._supported = PRESENTATION_PROPERTIES[profile]
        # canonical style tuple (sorted (property, value) pairs) -> class name
        self._styles = {}
        # class name -> canonical style tuple, registration order preserved
        self._rules = {}
        # user requested names already taken
        self._custom_names = set()
        self._counter = 0
        self._style_element = None

    @property
    def supported_properties(self):
        """ Frozen set of presentation property names accepted by this
        registry. """
        return self._supported

    def register(self, properties=None, name=None, **extra):
        """ Register a presentation-attribute style as a reusable class.

        :param properties: mapping of presentation properties to values,
            or a CSS declaration string (``'fill: red; stroke: black'``);
            underscores in keyword names are accepted just like on elements
        :param str name: optional explicit class name; must be a valid CSS
            identifier
        :param extra: additional presentation properties as keyword arguments
        :return: the stable class name referencing the rule
        :raises ValueError: empty style, unsupported/unknown property, bad
            custom class name or a name collision with a *different* style
        :raises TypeError: invalid property value in debug mode

        Registering an equivalent style again returns the same class name.
        Registering an existing custom name with the *same* properties also
        returns the existing name; a different style on that name raises
        :class:`ValueError`.
        """
        style = self._normalize(properties, extra)
        if not style:
            raise ValueError("Cannot register an empty style.")
        if name is not None and not _is_valid_class_name(name):
            raise ValueError(
                "Invalid class name %r: must be a valid CSS identifier "
                "starting with a letter or underscore." % name)

        existing = self._styles.get(style)
        if existing is not None:
            if name is not None and existing != name:
                raise ValueError(
                    "Class name %r is already used by an equivalent style "
                    "registered as %r." % (name, existing))
            return existing

        class_name = self._allocate_name(name, style)
        self._styles[style] = class_name
        self._rules[class_name] = style
        self._ensure_style_element()
        return class_name

    def register_css(self, declarations, name=None):
        """ Register styles given as a CSS declaration string.

        :param declarations: CSS text like ``'fill: red; stroke: black'``;
            only supported single ``property: value`` declarations are
            accepted, unsupported or malformed declarations raise
            :class:`ValueError`
        :param str name: optional explicit class name
        :return: the stable class name
        """
        return self.register(declarations, name=name)

    def attach(self, element, *class_names):
        """ Attach one or more registered classes to an SVG element.

        Existing ``class`` attributes (user supplied classes) are preserved;
        the registry classes are appended. Presentation attributes that
        collide with a registered class property are moved into the inline
        ``style`` attribute so that explicit local values still override the
        class rule (presentation attributes have lower CSS priority than
        author stylesheets).

        :param element: any :class:`svgwrite.base.BaseElement`
        :param class_names: class names returned by :meth:`register`
        :raises KeyError: a class name was never registered with this
            registry
        :return: the element
        """
        requested = []
        for item in class_names:
            if is_string(item):
                requested.append(item)
            else:  # accept iterables of class names
                requested.extend(item)
        for class_name in requested:
            if class_name not in self._rules:
                raise KeyError(
                    "Unknown style class %r: register it before attaching."
                    % class_name)

        previous = _split_classes(element.attribs.get('class'))
        # de-dupe within this attachment only; classes with the same name
        # coming from different registries are kept as given
        requested = [c for index, c in enumerate(requested)
                     if c not in requested[:index]]
        merged = previous + [c for c in requested if c not in previous]
        if merged:
            element.attribs['class'] = ' '.join(merged)

        # remember the registry so serialization can promote local overrides
        registries = getattr(element, '_style_registries', None)
        if registries is None:
            registries = element._style_registries = []
        if self not in registries:
            registries.append(self)
        sync_inline_styles(element)
        return element

    def classes(self):
        """ Return the registered class names in registration order. """
        return list(self._rules.keys())

    def rules(self):
        """ Return ``(class_name, ((property, value), ...))`` pairs in
        registration order. """
        return [(name, self._rules[name]) for name in self._rules]

    def get_css_text(self):
        """ Build the stylesheet text.

        Rules appear in registration order; properties inside a rule are
        sorted alphabetically so the output is deterministic.
        """
        lines = []
        for class_name, style in self._rules.items():
            declarations = '; '.join(
                '%s: %s' % (prop, value) for prop, value in style)
            lines.append('.%s {%s;}' % (class_name, declarations))
        return '\n'.join(lines)

    def _allocate_name(self, name, style):
        if name is not None:
            if name in self._rules and self._rules[name] != style:
                raise ValueError(
                    "Class name %r is already registered with different "
                    "properties." % name)
            self._custom_names.add(name)
            return name
        while True:
            candidate = '%s-%d' % (DEFAULT_CLASS_PREFIX, self._counter)
            self._counter += 1
            if candidate not in self._rules and \
                    candidate not in self._custom_names:
                return candidate

    def _normalize(self, properties, extra):
        """ Build the canonical, sorted tuple of (property, value) pairs. """
        items = []
        if properties is not None:
            if is_string(properties):
                items.extend(self._parse_declarations(properties))
            else:
                for key, value in dict(properties).items():
                    items.append((normalize_property_name(key), value))
        for key, value in extra.items():
            items.append((normalize_property_name(key), value))

        normalized = {}
        for prop, value in items:
            if prop not in self._supported:
                raise ValueError(
                    "Unsupported presentation property %r for profile %r."
                    % (prop, self.profile))
            value = self._check_value(prop, value)
            normalized[prop] = value
        return tuple(sorted(normalized.items()))

    def _check_value(self, prop, value):
        if value is None:
            raise ValueError(
                "Presentation property %r requires a value, got None." % prop)
        value = str(value)
        if not value:
            raise ValueError(
                "Presentation property %r requires a non-empty value." % prop)
        if any(char in value for char in _CSS_FORBIDDEN):
            raise ValueError(
                "Invalid value %r for property %r: ';', '{' and '}' are not "
                "allowed in registered style values." % (value, prop))
        if ']]>' in value:
            raise ValueError(
                "Invalid value %r for property %r: ']]>' is not allowed."
                % (value, prop))
        if self.debug:
            # validate against a generic graphics element that carries the
            # full presentation property set
            self._validator.check_svg_attribute_value('rect', prop, value)
        return value

    @staticmethod
    def _parse_declarations(text):
        declarations = []
        for declaration in text.split(';'):
            declaration = declaration.strip()
            if not declaration:
                continue
            if ':' not in declaration:
                raise ValueError(
                    "Malformed CSS declaration %r: expected 'property: "
                    "value'." % declaration)
            prop, value = declaration.split(':', 1)
            prop = prop.strip()
            value = value.strip()
            if not prop or not value:
                raise ValueError(
                    "Malformed CSS declaration %r: property and value must "
                    "not be empty." % declaration)
            declarations.append((normalize_property_name(prop), value))
        if not declarations:
            raise ValueError("No CSS declarations found in %r." % text)
        return declarations

    def _ensure_style_element(self):
        if self._style_element is not None or self._drawing is None:
            return
        if self.profile == 'tiny' and self.debug:
            # SVG Tiny 1.2 removed CSS support: its schema neither knows the
            # <style> element nor a 'style' attribute
            raise ValueError(
                "Shared CSS classes are not part of the SVG Tiny 1.2 "
                "profile. Use profile='full', or create the drawing with "
                "debug=False to emit a <style> element anyway (renderers "
                "still accept it, though it is not schema-valid Tiny).")
        self._style_element = _RegistryStyle(self)
        self._drawing.defs.add(self._style_element)


def _split_classes(value):
    if value is None:
        return []
    if not is_string(value):
        value = str(value)
    return value.split()


def _parse_inline_style(text):
    """ Parse an inline ``style`` attribute into an ordered list of
    ``(property, value)`` pairs. """
    pairs = []
    for declaration in text.split(';'):
        declaration = declaration.strip()
        if not declaration:
            continue
        if ':' not in declaration:
            # leave unknown content untouched by keeping it verbatim
            pairs.append((declaration, None))
            continue
        prop, value = declaration.split(':', 1)
        pairs.append((prop.strip(), value.strip()))
    return pairs


def _serialize_inline_style(pairs):
    parts = []
    for prop, value in pairs:
        parts.append(prop if value is None else '%s: %s' % (prop, value))
    return '; '.join(parts)


def sync_inline_styles(element):
    """ Promote local presentation attributes that collide with an attached
    registry class into the inline ``style`` attribute.

    Inline style declarations win (they keep their priority and the
    presentation attribute is simply dropped). This function is idempotent
    and is called automatically while the element is serialized.
    """
    registries = getattr(element, '_style_registries', None)
    if not registries:
        return
    class_names = set(_split_classes(element.attribs.get('class')))
    class_properties = set()
    for registry in registries:
        for class_name in class_names:
            style = registry._rules.get(class_name)
            if style is not None:
                class_properties.update(prop for prop, _value in style)
    if not class_properties:
        return

    inline_pairs = _parse_inline_style(element.attribs.get('style', ''))
    inline_properties = set(prop for prop, value in inline_pairs
                            if value is not None)

    for prop in sorted(class_properties):
        if prop not in element.attribs:
            continue
        local_value = element.attribs.pop(prop)
        if local_value is None or prop in inline_properties:
            # an explicit inline style already wins; nothing to promote
            continue
        inline_pairs.append((prop, str(local_value)))

    if inline_pairs:
        element.attribs['style'] = _serialize_inline_style(inline_pairs)
