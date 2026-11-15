#!/usr/bin/env python
# coding:utf-8
# Author: mozman
# Purpose: reuse equivalent graphic groups as shared <symbol> / <use>
# Created: 2026-11-15
# Copyright (C) 2026, Manfred Moitzi
# License: MIT License
"""
Opt-in de-duplication of repeated graphic groups.

An icon sprite (or any drawing built from repeated parts) often embeds the
same vector graphics over and over again. :meth:`Drawing.deduplicate` finds
the groups whose actual drawn content, styling and local transforms are
equivalent, hoists one copy of each equivalence class into the drawing's
``<defs>`` section as a shared ``<symbol>`` and replaces every remaining
instance in place by a ``<use>`` element referencing that symbol.

Only *self contained* groups are merged. A group is skipped when it contains
anything that cannot be safely rewritten, namely:

* external references (``<image>``/``<a>`` with non-fragment URIs,
  ``<script>``/``<style>``),
* references (``url(#...)`` or ``xlink:href``) pointing outside of the
  group,
* elements carrying a CSS ``class`` (the matching rules live outside of the
  group and cannot be compared),
* elements inside the group that are themselves referenced from outside of
  the group (an ``id`` that is used elsewhere must stay in place),
* unknown element types and interactive/animated elements.

Groups that merely reference their *own* internal elements (e.g. a shape
painted with a gradient defined inside the same group) are safe: their
internal ``id`` attributes are renamed consistently within the hoisted
symbol and inside every shared definition.

The transformation is opt-in (:meth:`Drawing.deduplicate`) and idempotent:
running it more than once never adds additional definitions or changes the
serialized output, and drawings never calling it are serialized exactly as
before.
"""
import copy
import re

from svgwrite.container import Group, Symbol, Use
from svgwrite.base import BaseElement
from svgwrite.etree import etree

# elements that pull in behaviour or resources which cannot be compared or
# rewritten safely
_DISALLOWED_ELEMENTS = frozenset((
    'script', 'style', 'a', 'image',
    # animations are time dependent behaviour, not static drawing content
    'animate', 'set', 'animateMotion', 'animateColor', 'animateTransform',
))

# every attribute capable of carrying an IRI reference, see SVG 1.1 chapter 17
_IRI_ATTRIBUTES = frozenset((
    'href', 'xlink:href',
    'fill', 'stroke', 'filter', 'clip-path', 'mask', 'marker-start',
    'marker-mid', 'marker-end', 'marker', 'cursor', 'color-profile',
    'baseline-shift',
))

# matches the '#fragment' part (or a whole '#fragment' reference)
_URL_REF_RE = re.compile(r'url\(\s*[\'"]?#([^)\'"\s]+)[\'"]?\s*\)')
_FRAGMENT_RE = re.compile(r'^#([^#\s]+)$')

_SYMBOL_ID_PREFIX = 'dedupe-symbol-'


def _iter_subtree(element):
    """ Yield `element` and every descendant element in document order.

    Wrapper objects used for ``title``/``desc``/``metadata`` do not expose an
    ``elements`` list and are therefore treated as leaves.
    """
    yield element
    children = getattr(element, 'elements', None)
    if children:
        for child in children:
            for sub in _iter_subtree(child):
                yield sub


def _extract_refs(attribute, value):
    """ Return the referenced fragment ids found in one attribute value. """
    if not isinstance(value, str):
        return ()
    refs = tuple(match.group(1) for match in _URL_REF_RE.finditer(value))
    if attribute in ('href', 'xlink:href'):
        match = _FRAGMENT_RE.match(value.strip())
        if match:
            refs += (match.group(1),)
    return refs


def _is_external_uri(attribute, value):
    """ True for href-like attributes pointing to an external resource. """
    if attribute not in ('href', 'xlink:href') or not isinstance(value, str):
        return False
    return not _FRAGMENT_RE.match(value.strip())


class _GroupReuser(object):
    """ Implements the group de-duplication for one :class:`Drawing`. """

    def __init__(self, drawing, min_occurrences=2):
        self.drawing = drawing
        self.min_occurrences = min_occurrences
        # ids of symbols already created by an earlier deduplicate() run
        self.known_symbol_ids = self._collect_symbol_ids()
        # id -> element, over the whole drawing
        self.id_index = {}
        # element -> set of ids referenced by that element
        self.references = {}
        self._build_indexes(drawing)
        # symbol ids created during this run
        self._symbol_counter = 0

    def _collect_symbol_ids(self):
        # only templates created by a previous deduplicate() run may be
        # referenced from an instance group; user defined defs content (e.g.
        # gradients) must still count as an external reference
        ids = set()
        for element in self.drawing.defs.elements:
            name = getattr(element, 'elementname', None)
            if name not in ('symbol', 'g'):
                continue
            element_id = element.attribs.get('id') if hasattr(element, 'attribs') else None
            if element_id is not None and str(element_id).startswith(_SYMBOL_ID_PREFIX):
                ids.add(str(element_id))
        return ids

    def _build_indexes(self, root):
        for element in _iter_subtree(root):
            if not hasattr(element, 'attribs'):
                continue
            element_id = element.attribs.get('id')
            if element_id is not None:
                self.id_index[str(element_id)] = element
            refs = set()
            for attribute, value in element.attribs.items():
                refs.update(_extract_refs(attribute, value))
            if refs:
                self.references[id(element)] = refs

    # -- safety ------------------------------------------------------------

    def _precheck(self, group):
        """ Return (internal_ids, ok) for a candidate group. """
        internal_ids = set()
        # first pass: collect every id declared inside the group
        for element in _iter_subtree(group):
            name = getattr(element, 'elementname', None)
            if name in _DISALLOWED_ELEMENTS:
                return internal_ids, False
            # CSS classes resolve against stylesheets outside the group
            if hasattr(element, 'attribs') and element.attribs.get('class'):
                return internal_ids, False
            if not isinstance(element, BaseElement) and name is None:
                # unknown wrapper element, cannot reason about its content
                return internal_ids, False
            if not hasattr(element, 'attribs'):
                continue
            element_id = element.attribs.get('id')
            if element_id is not None:
                internal_ids.add(str(element_id))

        # second pass: every reference has to stay inside the group
        for element in _iter_subtree(group):
            if not hasattr(element, 'attribs'):
                continue
            for attribute, value in element.attribs.items():
                if _is_external_uri(attribute, value):
                    return internal_ids, False
                for ref_id in _extract_refs(attribute, value):
                    if ref_id in internal_ids:
                        continue  # self contained reference
                    if ref_id in self.known_symbol_ids:
                        continue  # <use> from an earlier deduplicate() run
                    return internal_ids, False
        return internal_ids, True

    def _is_self_contained(self, group, internal_ids):
        """ No element outside `group` may reference an id inside it. """
        group_object_ids = set(id(e) for e in _iter_subtree(group))
        for element, refs in self.references.items():
            if element in group_object_ids:
                continue
            if refs & internal_ids:
                return False
        return True

    # -- canonical fingerprints -------------------------------------------

    def _build_path_map(self, root):
        """ Map every id inside `root` to the canonical id of its element.

        Canonical ids are derived from the element position inside the
        subtree, so two structurally identical subtrees whose local ids only
        differ in value get identical fingerprints.
        """
        path_map = {}

        def walk(element, path):
            if not hasattr(element, 'attribs'):
                return  # title/desc/metadata wrappers cannot carry ids
            element_id = element.attribs.get('id')
            if element_id is not None:
                path_map[str(element_id)] = 'id@' + path
            for index, child in enumerate(getattr(element, 'elements', ()) or ()):
                walk(child, path + '/' + str(index))

        walk(root, '')
        return path_map

    def _canonical_element(self, element, path_map):
        name = getattr(element, 'elementname', None)
        if not hasattr(element, 'attribs'):
            # title/desc/metadata wrapper: compare the rendered XML verbatim
            return ('wrapper', etree.tostring(element.get_xml()))

        attribs = []
        for attribute, value in sorted(element.attribs.items()):
            if value is None:
                continue
            value = str(value)
            if not value:
                continue
            if attribute == 'id':
                # local ids are positional, not structural
                value = path_map[value]
            elif attribute in _IRI_ATTRIBUTES:
                def rewrite(match):
                    return 'url(' + path_map.get(match.group(1),
                                                 match.group(0)) + ')'
                value = _URL_REF_RE.sub(rewrite, value)
                match = _FRAGMENT_RE.match(value.strip())
                if match and attribute in ('href', 'xlink:href'):
                    value = path_map.get(match.group(1), value)
            attribs.append((attribute, value))

        children = tuple(
            self._canonical_element(child, path_map)
            for child in (getattr(element, 'elements', ()) or ()))
        return (name, tuple(attribs), children)

    def _fingerprint(self, group):
        """ Canonical structure of a candidate group.

        The candidate group's own ``transform`` positions the instance and is
        preserved verbatim on the replacing ``<use>``, so it is excluded from
        the comparison; transforms of any nested groups are part of the drawn
        content and therefore remain included.
        """
        path_map = self._build_path_map(group)
        name, attribs, children = self._canonical_element(group, path_map)
        attribs = tuple(item for item in attribs if item[0] != 'transform')
        return (name, attribs, children)

    # -- rewriting ---------------------------------------------------------

    def _new_symbol_id(self):
        self._symbol_counter += 1
        base = _SYMBOL_ID_PREFIX + str(self._symbol_counter)
        candidate = base
        counter = 1
        existing = set(self.id_index)
        while candidate in existing:
            counter += 1
            candidate = '%s-%d' % (base, counter)
        return candidate

    def _rewrite_ids(self, element, rename):
        if not hasattr(element, 'attribs'):
            return
        element_id = element.attribs.get('id')
        if element_id is not None and str(element_id) in rename:
            element.attribs['id'] = rename[str(element_id)]
        for attribute, value in list(element.attribs.items()):
            if not isinstance(value, str):
                continue
            new_value = _URL_REF_RE.sub(
                lambda match: 'url(#' + rename.get(match.group(1),
                                                   match.group(1)) + ')',
                value)
            if attribute in ('href', 'xlink:href'):
                match = _FRAGMENT_RE.match(new_value.strip())
                if match:
                    new_value = '#' + rename.get(match.group(1),
                                                 match.group(1))
            if new_value != value:
                element.attribs[attribute] = new_value
        for child in getattr(element, 'elements', ()) or ():
            self._rewrite_ids(child, rename)

    def _replace_group(self, parent, group, symbol_id):
        use = Use('#' + symbol_id, factory=self.drawing)
        # carry over every attribute of the original group (transform,
        # presentation styles, ...) so inherited styling and the local
        # coordinate system are preserved; href keys belong to the new link
        for attribute, value in group.attribs.items():
            if attribute in ('href', 'xlink:href'):
                continue
            use.attribs[attribute] = value
        use.attribs.pop('id', None)  # instance groups must not keep the id
        index = parent.elements.index(group)
        parent.elements[index] = use

    def _hoist(self, group, members):
        internal_ids = set()
        for element in _iter_subtree(group):
            element_id = element.attribs.get('id') if hasattr(element, 'attribs') else None
            if element_id is not None:
                internal_ids.add(str(element_id))

        symbol_id = self._new_symbol_id()
        if self.drawing.profile == 'tiny':
            # SVG Tiny 1.2 has no <symbol> element; a named <g> in <defs>
            # referenced by <use> is the equivalent, viewport-free template
            template_container = Group(id=symbol_id, factory=self.drawing)
        else:
            # overflow="visible": without a viewBox a <symbol> still
            # establishes a new viewport whose default overflow is hidden,
            # which would clip and alter unit resolution relative to the
            # original inline group; visible makes the symbol behave exactly
            # like the replaced <g>
            template_container = Symbol(id=symbol_id, overflow='visible',
                                        factory=self.drawing)

        # deep copy: the template content is independent of the instance trees
        template = copy.deepcopy(group)
        rename = {}
        for old_id in sorted(internal_ids):
            rename[old_id] = '%s-%s' % (symbol_id, len(rename))
        self._rewrite_ids(template, rename)
        for child in template.elements:
            template_container.add(child)
        self.drawing.defs.add(template_container)

        # keep the bookkeeping indexes coherent
        self.id_index[symbol_id] = template_container
        for old_id, new_id in rename.items():
            self.id_index.pop(old_id, None)
            self.id_index[new_id] = template_container
        self.known_symbol_ids.add(symbol_id)

        for instance in members:
            parent = self._find_parent(instance)
            if parent is not None:
                self._replace_group(parent, instance, symbol_id)
        return template_container

    def _find_parent(self, target):
        def search(container):
            for child in container.elements:
                if child is target:
                    return container
                if getattr(child, 'elements', None):
                    found = search(child)
                    if found is not None:
                        return found
            return None
        return search(self.drawing)

    # -- main entry --------------------------------------------------------

    def _process_container(self, container):
        """ Recursively hoist repeated groups below `container`, top-down.

        A hoisted group's whole subtree is skipped afterwards, so content
        already moved into a template is never hoisted a second time.
        Returns the number of groups hoisted in this invocation.
        """
        hoisted = 0
        groups = [child for child in container.elements
                  if getattr(child, 'elementname', None) == 'g']
        classes = {}
        order = []
        for group in groups:
            internal_ids, ok = self._precheck(group)
            if not ok or not self._is_self_contained(group, internal_ids):
                continue
            fingerprint = self._fingerprint(group)
            if fingerprint not in classes:
                classes[fingerprint] = []
                order.append(fingerprint)
            classes[fingerprint].append(group)

        hoisted_groups = set()
        for fingerprint in order:
            members = classes[fingerprint]
            if len(members) < self.min_occurrences:
                continue
            self._hoist(members[0], members)
            hoisted_groups.update(members)
            hoisted += 1

        # recurse only into groups that were not themselves hoisted
        for group in groups:
            if group not in hoisted_groups and getattr(group, 'elements', None):
                hoisted += self._process_container(group)
        return hoisted

    def run(self):
        # fixed point iteration: after hoisting, enclosing groups may have
        # become equivalent (they now contain identical <use> elements);
        # rerun until a pass hoists nothing, which terminates because each
        # pass strictly reduces the number of renderable groups
        while self._process_container(self.drawing):
            pass


def deduplicate(drawing, min_occurrences=2):
    """ Replace equivalent self-contained groups by shared ``<symbol>``/``<use>``.

    :param drawing: the :class:`~svgwrite.drawing.Drawing` to optimize
    :param int min_occurrences: only groups occurring at least this many times
        are hoisted (default ``2``)
    :returns: the drawing, so calls can be chained

    The drawing is modified in place. The call is idempotent: invoking it
    again produces no additional definitions and leaves the serialized
    output unchanged.
    """
    _GroupReuser(drawing, min_occurrences=min_occurrences).run()
    return drawing
