Gradient Inheritance
====================

.. automodule:: svgwrite.gradientinheritance

.. seealso::

  * http://www.w3.org/TR/SVG11/pservers.html#LinearGradients (inheritance rules)

A gradient may reference another gradient of the same type with the
**xlink:href** attribute and inherit its stops, geometry, coordinate system
(``gradientUnits``), transform (``gradientTransform``) and ``spreadMethod``.
Local attributes and local stops take precedence over the inherited ones.

Two entry points exist:

* :meth:`svgwrite.drawing.Drawing.check_gradient_inheritance` -- validate only,
  the drawing is not modified
* :meth:`svgwrite.drawing.Drawing.expand_gradient_inheritance` -- validate and
  materialize every chain into self contained gradients with closed references

.. autoclass:: svgwrite.gradientinheritance.GradientInheritance

Methods
-------

.. automethod:: svgwrite.gradientinheritance.GradientInheritance.validate

.. automethod:: svgwrite.gradientinheritance.GradientInheritance.resolve

.. automethod:: svgwrite.gradientinheritance.GradientInheritance.infos

.. automethod:: svgwrite.gradientinheritance.GradientInheritance.info_by_id

.. automethod:: svgwrite.gradientinheritance.GradientInheritance.expand

.. autoclass:: svgwrite.gradientinheritance.GradientInfo

.. autoclass:: svgwrite.gradientinheritance.GradientInheritanceError
