import logging
from typing import Dict, List, Sequence, Tuple

from ledfx.devices import Device, Devices
from ledfx.effects import Effect
from ledfx.core import LedFxCore
import numpy as np
import voluptuous as vol


_LOGGER = logging.getLogger(__name__)


Color = Tuple[int, int, int]


class Segment(object):
    """A section of an LED light strip.

    Does not necessarily contain all of the pixels in a string/device.
    """
    CONFIG_SCHEMA = vol.Schema({
        vol.Required(
            'name',
            description='Friendly name for the segment in the group'): str,
        vol.Required(
            'device_id',
            description=(
                'The device identifier for the device that controls this '
                'segment')): str,
        vol.Required(
            'pixel_start',
            description=(
                'The first 0-indexed pixel on the device in this segment. '
                'Must not overlap with any other segment.')): int,
        vol.Required(
            'pixel_end',
            description=(
                'The last 0-indexed pixel on the device in this segment. '
                'Must not overlap with any other segment.')): int,
    })

    def __init__(self, config, segment_group, device_effects: Dict[str, Effect]):
        self.config = self.CONFIG_SCHEMA(config)
        self.group = segment_group

        self.device_effect = device_effects[self.config['device_id']]

    @property
    def pixels(self):
        return self.device_effect.pixels[
            self.config['pixel_start']: self.config['pixel_end']]

    @pixels.setter
    def pixels(self, pixels: Sequence[Color]):
        if len(pixels) != len(self.pixels):
            raise RuntimeError('Pixel sequence must be the size of the segment.')

        device_pixels = self.device_effect.pixels
        device_pixels[self.config['pixel_start']:self.config['pixel_end']] = pixels
        self.device_effect.pixels = device_pixels


class SegmentGroup(object):
    """A group of visually related LED pixel segments.

    These are not necessarily on the same device. Separate devices may control
    seemingly related segments, but they may be separate for wiring
    optimization.
    """
    CONFIG_SCHEMA = vol.Schema({
        vol.Required(
            'name',
            description='Friendly name for the parent Segment group'): str,
        vol.Required(
            'segments',
            description='Subclassed segments of '): [Segment.CONFIG_SCHEMA]
    })

    def __init__(self, config, device_effects: Dict[str, Effect]):
        self.config = self.CONFIG_SCHEMA(config)
        self.segments = sorted([
            Segment(segment, self, device_effects)
            for segment in self.config['segments']
        ], key=lambda segment: segment.config['pixel_start'])

    @property
    def pixels(self):
        return np.concatenate([segment.pixels for segment in self.segments])

    @pixels.setter
    def pixels(self, pixels: Sequence[Color]):
        if len(pixels) != len(self.pixels):
            raise RuntimeError('Pixel sequence must be the size of the segment group.')

        next_pixel = 0
        for segment in self.segments:
            segment_pixels = pixels[next_pixel:next_pixel + len(segment.pixels)]
            segment.pixels = segment_pixels


class SegmentGroups(object):
    """A simple, validated collection of all of the grouped segments.

    These will function as the controllable elements for effects.
    """
    def __init__(self, segment_group_configs, ledfx: LedFxCore,
                 device_effects: Dict[str, Effect]):
        self.groups = [
            SegmentGroup(group, device_effects)
            for group in segment_group_configs
        ]

        self.device_map = _map_groups_to_devices(ledfx.devices, self.groups)
        _check_unused_pixels(self.device_map)


class DeviceAndSegments(object):
    """A simple typed pair of a device and the segments it controls."""
    def __init__(self, device: Device, segments: List[Segment]):
        self.device = device
        self.segments = segments


def _map_groups_to_devices(devices: Devices, groups: Sequence[SegmentGroup]):
    """Builds a map of device id to the validated segments it controls.

    Args:
        devices: The Devices collection from LedFx that can be controlled.
        groups: The related segment groups to map to their controlling devices
            along with validating their form.

    Raises:
        RuntimeError: if the device does not exist, or pixels are assigned to
            more than one segment.
    """
    device_map: Dict[str, DeviceAndSegments] = {
        device.id: DeviceAndSegments(device, []) for device in devices.values()
    }
    for group in groups:
        for segment in group.segments:
            _map_segment_to_devices(segment, device_map)
    return device_map


def _map_segment_to_devices(
        segment: Segment, device_map: Dict[str, DeviceAndSegments]):
    """Adds a segment to the device map, validating it.

    Args:
        segment: The segment being added to the map.
        device_map: The partially initialized device map with the devices added
            and potentially some validated segments added.

    Raises:
        RuntimeError: if the device does not exist, or pixels are assigned to
            more than one segment.
    """
    device_id = segment.config['device_id']
    if device_id not in device_map:
        raise RuntimeError(
            f'Device {device_id} specified by segment '
            f'{segment.group.config["name"]}.{segment.config["name"]} does not '
            'exist')

    device_and_segments = device_map[device_id]
    device = device_and_segments.device
    existing_segments = device_and_segments.segments
    # Since the segments are sorted by pixel range, we could do this more
    # efficiently by performing a binary search and checking only one overlap
    # instead of comparing every element to each other. This is O(N^2), but
    # since the number of segments is effectively limited to 850 (max E1.31 for
    # WLED), the problem is pretty well bound.
    for existing_segment in existing_segments:
        if _segments_overlap(segment, existing_segment):
            raise RuntimeError(
                f'Segment {segment.group.config["name"]}.'
                f'{segment.config["name"]} overlaps with segment '
                f'{existing_segment.group.config["name"]}.'
                f'{existing_segment.config["name"]} on device '
                f'{segment.config["device_id"]}.')

    for i, existing_segment in enumerate(existing_segments):
        if segment.config['pixel_start'] > existing_segment.config['pixel_end']:
            existing_segments.insert(i + 1, segment)
    else:
        existing_segments.append(segment)


def _segments_overlap(segment1: Segment, segment2: Segment):
    """Checks if two segments overlap at all in any pixels."""
    start2 = segment2.config['pixel_start']
    end2 = segment2.config['pixel_end']
    start_is_in_segment2 = start2 <= segment1.config['pixel_start'] <= end2
    end_is_in_segment2 = start2 <= segment1.config['pixel_end'] <= end2
    return start_is_in_segment2 or end_is_in_segment2


def _check_unused_pixels(device_map: Dict[str, DeviceAndSegments]):
    """Checks if there are any pixels on the devices unassigned to segments.

    Logs a warning for unassigned pixels, since they will just be left off.
    """
    for device_and_segments in device_map.values():
        device = device_and_segments.device
        segments = device_and_segments.segments
        if len(segments) == 0:
            continue
        unused_segments = []
        last_pixel = -1
        for segment in segments:
            if segment.config['pixel_start'] - last_pixel > 1:
                unused_segments.append(
                    (last_pixel + 1, segment.config['pixel_start'] - 1))
            last_pixel = segment.config['pixel_end']
        if last_pixel < device.config['pixel_count'] - 1:
            unused_segments.append(
                (last_pixel + 1, device.config['pixel_count'] - 1))

        if len(unused_segments) > 0:
            _LOGGER.warning(
                'Device %s has the following unused pixels: %s.',
                device.id, unused_segments)


class ProxiedEffect(Effect):
    """An effect that will be updated by external functions for each segment.

    This abstracts the fact that Effect is concerned with a single device in its
    whole rather than many effects being processed on different segments behind
    a device.

    This effectively aggregates a number of segments behind a single effect.
    """
    def __init__(self, ledfx: LedFxCore):
        super(ProxiedEffect, self).__init__(ledfx, config={})

    def update_config(self, config):
        # TODO(willjschmitt): Overridden to pass, since we aren't able to
        # instantiate the base class with the current implementation. This is a
        # hack for now.
        validated_config = type(self).schema()(config)
        self._config = validated_config
