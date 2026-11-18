#!/usr/bin/env python
#coding:utf-8
# Author: mozman --<mozman@gmx.at>
# Purpose: gradient inheritance (xlink:href) validation and expansion example
# Created: 18.11.2026
# Copyright (C) 2026, Manfred Moitzi
# License: MIT License

"""Icon theme example: one base gradient derives several color schemes through
a three level **xlink:href** inheritance chain.

Run this script to write three SVG files:

* ``gradient_inheritance_chained.svg`` - original gradients with references
* ``gradient_inheritance_expanded.svg`` - self contained gradients, references
  closed by :meth:`Drawing.expand_gradient_inheritance`
* ``gradient_inheritance_bad_ref.svg`` - a drawing with a bad reference,
  rejected by :meth:`Drawing.check_gradient_inheritance` before it is written
"""
try:
    import svgwrite
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import svgwrite
from svgwrite.gradientinheritance import GradientInheritanceError


def build_theme_drawing(name):
    dwg = svgwrite.Drawing(name, size=('24cm', '8cm'), profile='full')
    dwg.viewbox(width=240, height=80)

    # level 1: the base gradient defines geometry, coordinate system,
    # transform and the default stops
    base = dwg.linearGradient(
        start=(0, 0), end=(100, 0), id='theme_base',
        gradientUnits='userSpaceOnUse')
    base.rotate(15)
    base.add_stop_color(0, '#2b2d42')
    base.add_stop_color(1, '#8d99ae')

    # level 2: inherits stops and everything else, only overrides x2
    wide = dwg.linearGradient(inherit=base, id='theme_wide')
    wide['x2'] = 200

    # level 3: inherits geometry/coordinate system/transform through the
    # chain but overrides the stops with a local color scheme
    hot = dwg.linearGradient(inherit='#theme_wide', id='theme_hot')
    hot.add_stop_color('0%', '#f72585')
    hot.add_stop_color('50%', '#b5179e')
    hot.add_stop_color('100%', '#7209b7')

    for gradient in (base, wide, hot):
        dwg.defs.add(gradient)

    dwg.add(dwg.rect((10, 10), (70, 60),
                     fill=base.get_paint_server()))
    dwg.add(dwg.rect((85, 10), (70, 60),
                     fill=wide.get_paint_server()))
    dwg.add(dwg.rect((160, 10), (70, 60),
                     fill=hot.get_paint_server()))
    return dwg, base, wide, hot


def main():
    # --- valid drawing: check only, the objects stay untouched ---------- #
    dwg, base, wide, hot = build_theme_drawing(
        'gradient_inheritance_chained.svg')
    infos = dwg.check_gradient_inheritance()
    for info in infos:
        print("%s chain=%s geometry=%s units=%s transform=%r stops=%d" % (
            info.id, info.chain, info.geometry, info.gradient_units,
            info.transform, len(info.stops)))
    dwg.save()

    # --- expand the chains into self contained gradients ---------------- #
    dwg.expand_gradient_inheritance()
    dwg.saveas('gradient_inheritance_expanded.svg')
    print("expanded XML:\n%s" % dwg.tostring())

    # --- bad reference: validation has to reject the drawing ------------ #
    bad = svgwrite.Drawing('gradient_inheritance_bad_ref.svg', profile='full')
    dangling = bad.linearGradient(id='dangling', inherit='#removed_theme')
    dangling.add_stop_color(0, 'red')
    dangling.add_stop_color(1, 'blue')
    bad.defs.add(dangling)
    try:
        bad.check_gradient_inheritance()
    except GradientInheritanceError as error:
        print("bad reference rejected: %s" % error)
    else:
        raise AssertionError("expected GradientInheritanceError")


if __name__ == '__main__':
    main()
