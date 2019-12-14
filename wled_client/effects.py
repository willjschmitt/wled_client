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
        pass


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
        self._thread_active = True
        self._thread = Thread(target=self.thread_function)
        self._thread.start()

    def deactivate(self):
        if self._thread_active:
            self._thread_active = False
            self._thread.join()
            self._thread = None

        super().deactivate()


class SingleLedChasing(TemporalLightShow):
    def __init__(self, segment_groups: SegmentGroups, color: Color):
        super(SingleLedChasing, self).__init__(segment_groups, {})

        self.color = color

        self.pixel = 0

    def effect_loop(self):
        for segment_group in self.segment_groups.groups:
            pixels = segment_group.pixels
            pixels[self.pixel] = (0, 0, 0)
            self.pixel += 1
            self.pixel = self.pixel % len(pixels)
            pixels[self.pixel] = self.color
            segment_group.pixels = pixels
            time.sleep(0.1)
