import logging

from flask import Flask, Response
from flask import request
from effects import SolidColorLightShow, LedChasing
import colors

_LOGGER = logging.getLogger(__name__)


_EFFECT_MAP = {
    'DEFAULT': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups, (colors.COLOR_MAP['WARM_WHITE'],), 1, 3),
    'ALTERNATE_COLORS': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups, effect_colors, 1, 3),
    'CANDY_CANE': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups,
        (colors.COLOR_MAP['WARM_WHITE'], colors.COLOR_MAP['RED'],), 10, 0),
    'MAZELTOV': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups,
        (colors.COLOR_MAP['WARM_WHITE'], colors.COLOR_MAP['BLUE'],), 1, 3),
    'MAZEL TOV': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups,
        (colors.COLOR_MAP['WARM_WHITE'], colors.COLOR_MAP['BLUE'],), 1, 3),
    'CHRISTMAS': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups,
        (colors.COLOR_MAP['WARM_WHITE'], colors.COLOR_MAP['RED'],), 1, 3),
    'CHASING': lambda segment_groups, effect_colors: LedChasing(
        segment_groups, colors),
    'SOLID': lambda segment_groups, effect_colors: SolidColorLightShow(
        segment_groups, colors),
}


class LightActionHandler(object):
    """Root handler, which routes to the correct handler based on the request.

    If the request is "on" or "off", the power handler is invoked.

    If the request is the name of an effect in _EFFECT_MAP, the effect handler
    is invoked.

    Otherwise, the color handler is invoked.
    """
    def __init__(self, ledfx):
        self._color_handler = LightColorAction(ledfx)
        self._effect_handler = LightEffectAction(ledfx)
        self._power_handler = LightPowerAction(ledfx)

    def __call__(self, *args):
        action = (
            request.get_json()["action"].upper().replace(" ", "_"))

        if action in ('ON', 'OFF'):
            _LOGGER.info('Handling power action to %s', action)
            return self._power_handler(action == 'ON')
        elif action in _EFFECT_MAP:
            _LOGGER.info('Handling effect action to %s', action)
            return self._effect_handler(action)
        else:
            _LOGGER.info('Defaulting to color action: %s', action)
            return self._color_handler(action)


class LightEffectAction(object):
    """Changes the current effect of the lights."""
    def __init__(self, ledfx):
        self._ledfx = ledfx

    def __call__(self, effect_name):
        effect_colors = (colors.COLOR_MAP['WARM_WHITE'],)

        if self._ledfx.show is not None:
            self._ledfx.show.deactivate()

            effect_colors = self._ledfx.show.colors

        if effect_name not in _EFFECT_MAP:
            raise RuntimeError(f'effect name {effect_name} is not in effect map')

        effect = _EFFECT_MAP[effect_name]
        self._ledfx.show = effect(self._ledfx.segment_groups, effect_colors)
        self._ledfx.show.activate()

        return Response(status=200, headers={})


class LightColorAction(object):
    """Changes the color of the current effect.

    If there is no current effect, the DEFAULT effect in _EFFECT_MAP is
    activated.

    Raises:
        NotImplementedError: If the active effect does not support color
                             adaptation.
    """
    def __init__(self, ledfx):
        self._ledfx = ledfx

    def __call__(self, color_pattern):
        color_patterns = color_pattern.split('_AND_')

        for color_pattern in color_patterns:
            if color_pattern not in colors.COLOR_MAP:
                return Response(
                    status=400, response=f'invalid color {color_pattern}')
        selected_colors = [
            colors.COLOR_MAP[color_pattern] for color_pattern in color_patterns]

        if self._ledfx.show is None:
            self._ledfx.show = _EFFECT_MAP['DEFAULT'](
                self._ledfx.segment_groups, selected_colors)

        self._ledfx.show.deactivate()
        self._ledfx.show.colors = selected_colors
        self._ledfx.show.activate()

        return Response(status=200, headers={})


class LightPowerAction(object):
    """Turns lights on or off entirely.

    If the lights are already in the requested state, it's a noop.

    If there was previously a lightshow set, reactivates it.

    If requested to turn on, and there was no previous light show, defaults to
    alternating warm white and no light.
    """
    def __init__(self, ledfx):
        self._ledfx = ledfx

    def __call__(self, on: bool):
        if self._ledfx.show is not None:
            if on:
                self._ledfx.show.activate()
            else:
                self._ledfx.show.deactivate()
        elif on:
            self._ledfx.show = _EFFECT_MAP['DEFAULT'](
                self._ledfx.segment_groups, None)
            self._ledfx.show.activate()

        return Response(status=200, headers={})


class FlaskAppWrapper(object):
    def __init__(self, ledfx, name=__name__):
        self.app = Flask(name)
        self.app.add_url_rule(
            '/holiday-lights', 'holiday-lights', LightActionHandler(ledfx),
            methods=['POST'])

    def run(self, host='0.0.0.0', port='4321'):
        self.app.run(host, port)
