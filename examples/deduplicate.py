#!/usr/bin/env python3
#coding:utf-8
# Author: mozman
# Purpose: show de-duplication of repeated icon groups
# Created: 2026-11-15
# Copyright (C) 2026, Manfred Moitzi
# License: MIT License
"""
An icon sprite embeds the same vector graphic several times. Without any
optimization every instance serializes the whole path data again.

``Drawing.deduplicate()`` is an opt-in rewrite: equivalent self-contained
groups are moved into the ``<defs>`` section once as a shared ``<symbol>``
and the instances become ``<use>`` references. Run this example and compare
the two generated files.
"""
import svgwrite


def build(drawing):
    def icon(tint, index):
        group = drawing.g()
        # the local gradient id differs per instance, but deduplicate()
        # rewrites internal ids when hoisting the shared symbol
        gradient = drawing.linearGradient(start=(0, 0), end=(20, 20),
                                          id='gradient-%s-%d' % (tint, index))
        gradient.add_stop_color(0, 'white').add_stop_color(1, tint)
        group.add(gradient)
        body = group.add(drawing.g(stroke='black', **{'stroke-width': 1}))
        body.add(drawing.rect(insert=(0, 0), size=(20, 20),
                              fill=gradient.get_funciri()))
        body.add(drawing.circle(center=(10, 10), r=5, fill='none'))
        return group

    colors = ('teal', 'teal', 'crimson', 'teal', 'crimson')
    for index, (x, tint) in enumerate(zip((10, 40, 70, 100, 130), colors)):
        instance = icon(tint, index)
        instance.translate(x, 10)
        drawing.add(instance)


def main():
    plain = svgwrite.Drawing('deduplicate_off.svg', size=(160, 40))
    build(plain)
    plain.save()

    optimized = svgwrite.Drawing('deduplicate_on.svg', size=(160, 40))
    build(optimized)
    optimized.deduplicate()  # opt-in reuse of the repeated groups
    optimized.save()

    print('plain size:     %d bytes' % len(plain.tostring()))
    print('optimized size: %d bytes' % len(optimized.tostring()))
    # calling it again does not change the output
    once = optimized.tostring()
    optimized.deduplicate()
    assert optimized.tostring() == once
    print('second call leaves the output unchanged')


if __name__ == '__main__':
    main()
