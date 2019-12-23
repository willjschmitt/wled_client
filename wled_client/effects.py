import logging
import time
from threading import Thread
from typing import Sequence

import voluptuous as vol

from segments import SegmentGroups, Color

_LOGGER = logging.getLogger(__name__)


class LightShow(object):
    def __init__(self, segment_groups: SegmentGroups):
        self.segment_groups = segment_groups

    def activate(self):
        pass

    def deactivate(self):
        for segment_group in self.segment_groups.groups:
            pixels = segment_group.pixels
            pixels[:] = (0, 0, 0)
            segment_group.pixels = pixels

    @property
    def colors(self):
        raise NotImplementedError('colors accessor not implemented')

    @colors.setter
    def colors(self, colors):
        raise NotImplementedError('colors setter not implemented')


class SolidColorLightShow(LightShow):
    def __init__(self, segment_groups: SegmentGroups,
                 colors: Sequence[Color], size_of_color: int = 1,
                 space_between: int = 0):
        super(SolidColorLightShow, self).__init__(segment_groups)

        self._colors = colors
        self._size_of_color = size_of_color
        self._space_between = space_between

    def activate(self):
        for segment_group in self.segment_groups.groups:
            pixels = segment_group.pixels

            i = 0
            color_block = 0
            while i < len(pixels):
                pixels[i:i+self._size_of_color] = self._colors[color_block % len(self.colors)]
                color_block += 1
                i += self._size_of_color + self._space_between
            segment_group.pixels = pixels

    @property
    def colors(self):
        return self._colors

    @colors.setter
    def colors(self, colors):
        self._colors = colors


class TemporalLightShow(LightShow):
    DEFAULT_RATE = 1.0 / 60.0

    _thread_active = False
    _thread = None

    CONFIG_SCHEMA = vol.Schema({
        vol.Optional('speed', default=1.0, description="Speed of the effect"): vol.Coerce(float)
    })

    def __init__(self, segment_groups, config):
        super(TemporalLightShow, self).__init__(segment_groups)

        self._config = self.CONFIG_SCHEMA(config)

    def thread_function(self):

        while self._thread_active:
            startTime = time.time()

            # Treat the return value of the effect loop as a speed modifier
            # such that effects that are nartually faster or slower can have
            # a consistent feel.
            sleep_interval = self.effect_loop()
            if sleep_interval is None:
                sleep_interval = 1.0
            sleep_interval = sleep_interval * self.DEFAULT_RATE

            # Calculate the time to sleep accounting for potential heavy
            # frame assembly operations
            time_to_sleep = (sleep_interval / self._config['speed']) - (time.time() - startTime)
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)

    def effect_loop(self):
        """
        Triggered periodically based on the effect speed and
        any additional effect modifiers
        """
        pass

    def activate(self):
        print('')
        self._thread_active = True
        self._thread = Thread(target=self.thread_function)
        self._thread.start()

    def deactivate(self):
        if self._thread_active:
            self._thread_active = False
            self._thread.join()
            self._thread = None

        super().deactivate()


class LedChasing(TemporalLightShow):
    def __init__(self, segment_groups: SegmentGroups, colors: Sequence[Color]):
        super(LedChasing, self).__init__(segment_groups, {})

        self._colors = colors
        self._pixel = 0

    def effect_loop(self):
        for segment_group in self.segment_groups.groups:
            pixels = segment_group.pixels
            pixels[self._pixel] = (0, 0, 0)
            self._pixel += 1
            pixel_indicies = (
                (self._pixel + i) % len(pixels) for i in range(len(pixels)))
            self._pixel = self._pixel % len(pixels)

            for i, pixel_index in enumerate(pixel_indicies):
                pixels[pixel_indicies] = self._colors[i]
            segment_group.pixels = pixels

        return 0.1

    @property
    def colors(self):
        return self._colors

    @colors.setter
    def colors(self, colors):
        self._colors = colors
