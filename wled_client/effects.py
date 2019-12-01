from typing import Sequence

from segments import SegmentGroups, Color


class LightShow(object):
    def __init__(self, segment_groups: SegmentGroups):
        self.segment_groups = segment_groups


class SolidColorLightShow(LightShow):
    def __init__(self, segment_groups: SegmentGroups,
                 colors: Sequence[Color], size_of_color: int = 1,
                 space_between: int = 0):
        super(SolidColorLightShow, self).__init__(segment_groups)

        self.colors = colors
        self.size_of_color = size_of_color
        self.space_between = space_between

    def activate(self):
        for segment_group in self.segment_groups.groups:
            pixels = segment_group.pixels

            i = 0
            color_block = 0
            while i < len(pixels):
                pixels[i:i+self.size_of_color] = self.colors[color_block % len(self.colors)]
                color_block += 1
                i += self.size_of_color + self.space_between
            segment_group.pixels = pixels
