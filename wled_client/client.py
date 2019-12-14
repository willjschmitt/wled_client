import asyncio
import logging

from ledfx.__main__ import parse_args, setup_logging
from ledfx.core import LedFxCore
from ledfx.devices import Devices
from ledfx.effects import Effects
import ledfx.config as config_helpers
from ledfx.events import LedFxShutdownEvent

from segments import SegmentGroups, ProxiedEffect
from effects import SolidColorLightShow, SingleLedChasing
import colors


_LOGGER = logging.getLogger(__name__)


class LedFxClient(LedFxCore):
    def __init__(self, config_dir):
        super(LedFxClient, self).__init__(config_dir)
        self.segment_groups = None

    async def async_start(self, open_ui=False):
        # This overrides the LedFxCore async_start, so we can bind our own
        # mapped effects approach.

        _LOGGER.info("Starting ledfx")
        await self.http.start()

        self.devices = Devices(self)
        self.effects = Effects(self)

        # TODO: Deferr
        self.devices.create_from_config(self.config['devices'])

        self.device_effects = {
            device.id: ProxiedEffect(self)
            for device in self.devices.values()
        }

        for device in self.devices.values():
            device.set_effect(self.device_effects[device.id])


        self.segment_groups = SegmentGroups(
            self.config['segment_groups'], self, self.device_effects)

        # Alternating green/red bulb-like.
        show = SolidColorLightShow(self.segment_groups, (colors.RED, colors.GREEN), 1, 2)
        show.activate()

        # # Simple warm white bulb-like.
        # show = SolidColorLightShow(self.segment_groups, (colors.WARM_WHITE,), 1, 2)
        # show.activate()

        # # Multi color strand.
        # show = SolidColorLightShow(
        #     self.segment_groups,
        #     (colors.GREEN, colors.ORANGE, colors.RED, colors.YELLOW, colors.BLUE, colors.PURPLE),
        #     1, 2)
        # show.activate()

        # # Candi-cane
        # show = SolidColorLightShow(self.segment_groups, (colors.RED, colors.WARM_WHITE), 15, 0)
        # show.activate()

        # show = SingleLedChasing(self.segment_groups, colors.RED)
        # show.activate()

        if open_ui:
            import webbrowser
            webbrowser.open(self.http.base_url)

        await self.flush_loop()

    async def async_stop(self, exit_code=0):
        # This overrides the LedFxCore async_start, so we can prevent it
        # re-saving the config. We will manage the config entirely manually.

        if not self.loop:
            return

        _LOGGER.info('Stopping LedFx.')

        # Fire a shutdown event and flush the loop
        self.events.fire_event(LedFxShutdownEvent())
        await asyncio.sleep(0, loop=self.loop)

        await self.http.stop()

        # Cancel all the remaining task and wait
        tasks = [task for task in asyncio.Task.all_tasks() if task is not
             asyncio.tasks.Task.current_task()]
        list(map(lambda task: task.cancel(), tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        await self.flush_loop()
        self.executor.shutdown()
        self.exit_code = exit_code
        self.loop.stop()


def main():
    """Main entry point allowing external calls"""
    args = parse_args()
    config_helpers.ensure_config_directory(args.config)
    setup_logging(args.loglevel)

    ledfx = LedFxClient(config_dir = args.config)

    # Abstraction from device to segments that are totally independent.
    # Related segments map many-to-many with devices. That is, a circuit might
    # curve around in a seemingly unrelated direction for the sole purpose of
    # easy wiring.
    #
    # When setting an effect, it should be upon a set of related segments that
    # are coordinated across devices, rather than upon a single device, let
    # alone the whole device.
    #
    # This new effect class is applied not to a device but to segments or
    # segment groups. Once an effect is applied across segment groups, then each
    # device is updated with a manual setting of its pixels, which is then
    # flushed.
    #
    # Devices don't care about the way their pixels are set except that they
    # obtain their pixels from an Effect. A new Effect class, called
    # MappedEffect acts to aggregate pixel commands from all
    #
    # Effects manipulate Devices by setting the `pixels` attribute, and then
    # are picked up during the thread loop for the the device. This thread loop
    # processes the active effect by reading the `pixels` attribute, and simply
    # translating the pixel values into the right structure to emit for the
    # device.
    #
    # TemporalEffects work by updating the pixels in its own thread. This thread
    # updates asynchronously from the actual device networking thread loop.

    ledfx.start()


if __name__ == '__main__':
    main()