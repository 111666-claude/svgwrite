#!/usr/bin/env python
#coding:utf-8
# Author:  mozman
# Purpose: accessibility (ARIA) support - accessible names, descriptions and roles
# License: MIT License
"""
Accessibility support for SVG elements.

A ``<title>``/``<desc>`` pair alone is not a *reliable* accessible name:
many assistive technologies only expose it when the element explicitly
references the nodes.  This module adds semantic annotations to
:class:`~svgwrite.base.BaseElement` (and therefore to ``Drawing``, ``Group``
and all basic shapes):

* an **accessible name** - a ``<title>`` subelement with a stable ``id``,
  referenced by ``aria-labelledby``
* an **accessible description** - a ``<desc>`` subelement with a stable
  ``id``, referenced by ``aria-describedby``
* a **role** - the WAI-ARIA ``role`` attribute, validated against
  :data:`VALID_ROLES`
* a **language** - the ``xml:lang`` attribute

Update rules (no duplicate nodes, no conflicting IDs)
-----------------------------------------------------

Calling :meth:`Accessibility.set_accessible_name` more than once on the same
element *updates* the existing ``<title>``/``<desc>`` nodes in place - the
nodes and their IDs are stable, so the ARIA references never dangle and no
duplicate nodes are created.  A hand-written ``<title>``/``<desc>`` (added
with :meth:`~svgwrite.base.BaseElement.set_desc`) is *adopted*: it keeps its
position, gets an ``id`` if it has none, and its text is updated.  In strict
mode (``strict=True``) adopting a hand-written node raises
:class:`AccessibilityError` instead.

Inheritance rules for nested groups
-----------------------------------

* **language**: ``xml:lang`` follows XML rules - an element without its own
  ``xml:lang`` inherits the nearest ancestor's language; an explicit
  ``xml:lang`` overrides it.  :meth:`Accessibility.apply_language`
  materializes this: with ``override=False`` (default) it only fills in
  elements that have no explicit language (inherit), with ``override=True``
  it replaces every language in the subtree (override).
* **name**: an accessible name labels the element it is set on.  In the
  accessibility tree a group's name covers its whole subtree *unless* a
  descendant defines its own name/role, which overrides the inherited
  context for that descendant.

Validation
----------

:func:`validate_accessibility` walks an element tree and reports duplicate
IDs, dangling ``aria-labelledby``/``aria-describedby`` references, invalid
roles and bad ``<title>``/``<desc>`` reading order.  With ``strict=True``
it raises :class:`AccessibilityError` on the first problem.

.. note::

    The ``aria-*`` and ``role`` attributes are not part of the SVG 1.1/1.2
    attribute lists, so they are stored directly and are *not* checked by
    the SVG profile validator (debug mode).  Role values are validated
    against :data:`VALID_ROLES` by this module instead.

"""

from svgwrite.etree import etree

#: WAI-ARIA roles that are meaningful for SVG graphics elements
#: (WAI-ARIA 1.1 + W3C Graphics-ARIA module).
VALID_ROLES = frozenset([
    # graphics-aria module
    'graphics-document', 'graphics-object', 'graphics-symbol',
    # common document structure / widget roles used for SVG content
    'img', 'image', 'figure', 'group', 'region', 'presentation', 'none',
    'button', 'checkbox', 'link', 'list', 'listitem', 'menu', 'menubar',
    'menuitem', 'navigation', 'option', 'progressbar', 'radio', 'slider',
    'switch', 'tab', 'tablist', 'toolbar', 'tooltip', 'tree', 'treeitem',
    'banner', 'complementary', 'contentinfo', 'form', 'main', 'search',
    'application', 'document', 'heading', 'note', 'separator', 'status',
])

#: attribute names managed by this module
LABELLEDBY = 'aria-labelledby'
DESCRIBEDBY = 'aria-describedby'


class AccessibilityError(ValueError):
    """ Raised for accessibility annotation conflicts in strict mode and by
    :func:`validate_accessibility`.
    """


def _is_descriptive_node(element, elementname):
    """ True if `element` is a <title>/<desc> node (duck-typed, works for
    svgwrite.base.Title/Desc and any compatible object).
    """
    return getattr(element, 'elementname', None) == elementname and \
        hasattr(element, 'xml')


class Accessibility(object):
    """ Mixin for :class:`~svgwrite.base.BaseElement` adding accessible
    name, description, role and language support.
    """

    # -- internal helpers -------------------------------------------------

    def _a11y_generated_id(self, kind):
        """ Deterministic id for the managed <title>/`desc` node:
        ``'<element-id>-title'`` or ``'<element-id>-desc'``.
        """
        return '%s-%s' % (self.get_id(), kind)

    def _a11y_find_node(self, kind):
        """ Return the first <title>/<desc> subelement or None. """
        for element in self.elements:
            if _is_descriptive_node(element, kind):
                return element
        return None

    def _a11y_get_or_create_node(self, kind, strict):
        """ Return the (existing or newly created) <title>/<desc> node.

        An existing hand-written node (no ``id``) is adopted - or rejected
        with :class:`AccessibilityError` if `strict` is True.
        """
        node = self._a11y_find_node(kind)
        if node is not None:
            if node.xml.get('id') is None:
                if strict:
                    raise AccessibilityError(
                        "<%s> already has a hand-written <%s> element; "
                        "refusing to adopt it in strict mode." %
                        (self.elementname, kind))
                node.xml.set('id', self._a11y_generated_id(kind))
            return node

        # lazy import to avoid a circular import at module load time
        from svgwrite.base import Title, Desc
        node = Title('') if kind == 'title' else Desc('')
        node.xml.set('id', self._a11y_generated_id(kind))
        if kind == 'title':
            # <title> is always the first subelement (reading order)
            self.elements.insert(0, node)
        else:
            # <desc> directly after <title> if present, else first
            pos = 1 if len(self.elements) and \
                _is_descriptive_node(self.elements[0], 'title') else 0
            self.elements.insert(pos, node)
        return node

    def _a11y_remove_node(self, kind):
        """ Remove the managed <title>/<desc> node, returns True if removed.

        Only nodes carrying this element's generated id are removed;
        hand-written nodes (foreign or missing id) are left untouched.
        """
        node = self._a11y_find_node(kind)
        if node is not None and \
                node.xml.get('id') == self._a11y_generated_id(kind):
            self.elements.remove(node)
            return True
        return False

    # -- public API -------------------------------------------------------

    def set_accessible_name(self, name=None, desc=None, role=None, lang=None,
                            strict=False):
        """ Set or update the accessible name (and optionally description,
        role and language) of this element.

        Generates a ``<title>`` subelement with a stable ``id`` and points
        ``aria-labelledby`` at it; `desc` does the same with ``<desc>`` and
        ``aria-describedby``.  Repeated calls update the existing nodes in
        place - no duplicate nodes, no conflicting IDs.

        :param name: accessible name; `None` leaves the current name
            unchanged, an empty or whitespace-only string raises
            :class:`ValueError` (an element without a name should use
            :meth:`clear_accessibility` instead)
        :param desc: accessible description; `None` leaves it unchanged, an
            empty or whitespace-only string *removes* the managed
            description
        :param role: WAI-ARIA role, must be one of :data:`VALID_ROLES`,
            otherwise :class:`ValueError` is raised
        :param lang: language tag for ``xml:lang`` (e.g. ``'en'``); `None`
            leaves the language untouched (inherited from the ancestors)
        :param strict: if `True`, a pre-existing hand-written
            ``<title>``/``<desc>`` raises :class:`AccessibilityError`
            instead of being adopted
        :returns: `self` to allow chaining

        """
        if name is not None:
            name = str(name)
            if not name.strip():
                raise ValueError(
                    "accessible name must not be empty; "
                    "use clear_accessibility() to remove it.")
        if role is not None and role not in VALID_ROLES:
            raise ValueError(
                "'%s' is not a valid ARIA role for SVG content, "
                "see svgwrite.accessibility.VALID_ROLES." % role)

        if name is not None:
            title = self._a11y_get_or_create_node('title', strict)
            title.xml.text = name
            # direct attribute store: aria-* is not part of the SVG
            # profile attribute lists and must bypass the validator
            self.attribs[LABELLEDBY] = title.xml.get('id')

        if desc is not None:
            desc = str(desc)
            if desc.strip():
                node = self._a11y_get_or_create_node('desc', strict)
                node.xml.text = desc
                self.attribs[DESCRIBEDBY] = node.xml.get('id')
            else:
                # explicit removal of the managed description
                self._a11y_remove_node('desc')
                self.attribs.pop(DESCRIBEDBY, None)

        if role is not None:
            self.attribs['role'] = role
        if lang is not None:
            self.attribs['xml:lang'] = lang
        return self

    def set_accessible_description(self, desc, strict=False):
        """ Set or update only the accessible description.

        Shortcut for ``set_accessible_name(desc=desc)``; an empty `desc`
        removes the managed description.
        """
        return self.set_accessible_name(desc=desc, strict=strict)

    def get_accessible_name(self):
        """ Return the accessible name (text of the ``<title>`` node) or
        `None`.
        """
        title = self._a11y_find_node('title')
        return title.xml.text if title is not None else None

    def get_accessible_description(self):
        """ Return the accessible description (text of the ``<desc>`` node)
        or `None`.
        """
        desc = self._a11y_find_node('desc')
        return desc.xml.text if desc is not None else None

    def clear_accessibility(self):
        """ Remove the accessibility annotations managed by this module:
        the generated ``<title>``/``<desc>`` nodes and the ``aria-labelledby``,
        ``aria-describedby`` and ``role`` attributes.  Hand-written
        ``<title>``/``<desc>`` nodes (foreign or missing ``id``) are kept.
        """
        self._a11y_remove_node('title')
        self._a11y_remove_node('desc')
        self.attribs.pop(LABELLEDBY, None)
        self.attribs.pop(DESCRIBEDBY, None)
        self.attribs.pop('role', None)

    def apply_language(self, lang, recursive=True, override=False):
        """ Set ``xml:lang`` on this element (and its subtree).

        :param lang: language tag, e.g. ``'en'`` or ``'zh-Hans'``
        :param recursive: also apply to subelements
        :param override: `False` (default) only sets the language on
            elements that do not have an explicit ``xml:lang`` (*inherit*);
            `True` replaces the language on every element (*override*)
        :returns: `self` to allow chaining

        """
        if override or 'xml:lang' not in self.attribs:
            self.attribs['xml:lang'] = lang
        if recursive:
            for element in self.elements:
                if hasattr(element, 'apply_language'):
                    element.apply_language(lang, recursive=True,
                                           override=override)
        return self


def _walk(element):
    """ Yield `element` and all BaseElement-like descendants. """
    yield element
    for child in getattr(element, 'elements', []):
        if hasattr(child, 'elements'):
            for descendant in _walk(child):
                yield descendant


def _collect_ids(element):
    """ All ids defined directly by `element` (its own ``id`` attribute and
    the ids of its <title>/<desc> subelements).
    """
    ids = []
    element_id = getattr(element, 'attribs', {}).get('id')
    if element_id is not None:
        ids.append(element_id)
    for child in getattr(element, 'elements', []):
        if _is_descriptive_node(child, 'title') or \
                _is_descriptive_node(child, 'desc'):
            node_id = child.xml.get('id')
            if node_id is not None:
                ids.append(node_id)
    return ids


def validate_accessibility(root, strict=False):
    """ Validate the accessibility annotations of an element tree.

    Checks for:

    * duplicate ``id`` values (including generated title/desc ids)
    * dangling ``aria-labelledby`` / ``aria-describedby`` references
    * ``role`` values not in :data:`VALID_ROLES`
    * bad reading order (``<desc>`` before ``<title>``)

    :param root: root element of the tree (e.g. a ``Drawing``)
    :param strict: raise :class:`AccessibilityError` on the first problem
        instead of collecting issues
    :returns: list of issue strings, empty if the tree is valid

    """
    issues = []

    def report(message):
        if strict:
            raise AccessibilityError(message)
        issues.append(message)

    ids = {}
    for element in _walk(root):
        for element_id in _collect_ids(element):
            if element_id in ids:
                report("duplicate id '%s' (<%s> and <%s>)." %
                       (element_id, ids[element_id], element.elementname))
            else:
                ids[element_id] = element.elementname

    for element in _walk(root):
        attribs = getattr(element, 'attribs', {})
        for attribute in (LABELLEDBY, DESCRIBEDBY):
            reference = attribs.get(attribute)
            if reference:
                for token in str(reference).split():
                    if token not in ids:
                        report("dangling reference: <%s> %s='%s' - no "
                               "element with id '%s'." %
                               (element.elementname, attribute, reference,
                                token))
        role = attribs.get('role')
        if role is not None and role not in VALID_ROLES:
            report("invalid role '%s' at <%s>." % (role, element.elementname))

        # reading order: <title> must come before <desc>
        seen_desc = False
        for child in getattr(element, 'elements', []):
            if _is_descriptive_node(child, 'desc'):
                seen_desc = True
            elif _is_descriptive_node(child, 'title') and seen_desc:
                report("bad reading order at <%s>: <title> after <desc>." %
                       element.elementname)
                break
    return issues
