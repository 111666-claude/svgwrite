Style Registry
==============

.. automodule:: svgwrite.styling

.. autoclass:: svgwrite.styling.StyleRegistry
   :members:

Usage example
-------------

A map with thousands of markers that all share the same fill and stroke
no longer repeats those presentation attributes on every element::

    import svgwrite

    dwg = svgwrite.Drawing('map.svg')
    styles = dwg.style_registry

    # register once, get a stable class name back
    marker = styles.register({'fill': '#2266aa',
                              'stroke': '#111111',
                              'stroke-width': '1.5'})

    for x, y in positions:
        point = dwg.rect(insert=(x, y), size=(3, 3))
        styles.attach(point, marker)
        dwg.add(point)

The generated ``<defs>`` section contains a single ``<style>`` element with
one rule per distinct style, and equivalent style mappings always resolve to
the same class name.

Local presentation attributes still win: attaching a class to an element that
also sets ``fill`` explicitly moves that local value into the inline
``style`` attribute, which has a higher cascade priority than the generated
stylesheet.
