Bounding Box
============

.. automodule:: svgwrite.boundingbox

Overview
--------

A fixed *viewBox* does not adapt to the shapes inside a drawing, so rotated
or otherwise transformed content may be clipped at the canvas edges. The
:mod:`svgwrite.boundingbox` module walks the element tree and computes the
visible bounding box of the supported geometry in root canvas coordinates:

* ``rect``, ``circle``, ``ellipse``
* ``line``, ``polyline``, ``polygon``
* ``path`` with the ``M``/``m``, ``L``/``l``, ``H``/``h``, ``V``/``v``,
  ``C``/``c``, ``S``/``s``, ``Q``/``q``, ``T``/``t`` and ``Z``/``z``
  commands

The affine transforms of nested groups (translate, scale, rotate, skewX,
skewY and matrix) are composed while traversing the tree, and the half
stroke width of every stroked element (including stroke presentation
attributes inherited from ancestor groups) is added to the bounds.

Update the *viewBox* of a drawing to fit its content::

    import svgwrite

    dwg = svgwrite.Drawing('example.svg')
    dwg.add(dwg.rect((10, 10), (50, 50)))
    dwg.fit_to_content(margin=5)

Unsupported or invalid input never produces silently wrong bounds; the
calculation raises one of the exceptions documented below.

Entry Points
------------

.. autofunction:: svgwrite.boundingbox.calculate_bounds

.. autofunction:: svgwrite.boundingbox.fit_to_content

.. automethod:: svgwrite.drawing.Drawing.calculate_bounds

.. automethod:: svgwrite.drawing.Drawing.fit_to_content

Bounding Box
------------

.. autoclass:: svgwrite.boundingbox.BoundingBox
   :members:

Exceptions
----------

.. automodule:: svgwrite.boundingbox

.. autoclass:: svgwrite.boundingbox.BoundingBoxError
.. autoclass:: svgwrite.boundingbox.EmptyDrawingError
.. autoclass:: svgwrite.boundingbox.InvalidCoordinateError
.. autoclass:: svgwrite.boundingbox.UnsupportedElementError
.. autoclass:: svgwrite.boundingbox.PathParseError

Unsupported Content
-------------------

The following elements have no computable static geometry and raise
:class:`~svgwrite.boundingbox.UnsupportedElementError`:

* ``text`` and all text related elements (font dependent extent)
* ``image`` (external raster content)
* ``use`` (references are not resolved)
* animation elements (geometry may change at runtime)
* elliptical arc path commands ``A``/``a``
* nested ``svg`` fragments that define their own *viewBox*

Coordinates have to be plain user-space numbers; a trailing ``px`` unit is
accepted, while physical units such as ``cm`` or ``%`` raise
:class:`~svgwrite.boundingbox.InvalidCoordinateError`.
