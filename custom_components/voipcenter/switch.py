"""Function indicator switches for the VoipCenter integration."""

from typing import Any

from aiovoipcenter import VoipCenterError
from aiovoipcenter.types import FunctionIndicator

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VoipCenterConfigEntry, VoipCenterCoordinator
from .entity import ServiceItemEntity, async_add_item_entities

PARALLEL_UPDATES = 1

# A function indicator is "activated" when red, like its BLF lamp.
COLOR_ON = "red"
COLOR_OFF = "green"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoipCenterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a switch per function indicator."""

    def _factory(
        coordinator: VoipCenterCoordinator, item_id: int
    ) -> list[SwitchEntity]:
        return [FunctionIndicatorSwitch(coordinator, item_id, "function_indicator")]

    async_add_item_entities(entry, async_add_entities, "function_indicators", _factory)


class FunctionIndicatorSwitch(ServiceItemEntity[FunctionIndicator], SwitchEntity):
    """A function indicator: on is red, off is green."""

    _collection = "function_indicators"
    _model = FunctionIndicator

    @property
    def is_on(self) -> bool | None:
        """Return whether the indicator is red."""
        color = self.item.color
        if color not in (COLOR_ON, COLOR_OFF):
            return None
        return color == COLOR_ON

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the indicator details."""
        return {
            "id": self.item_id,
            "extension": self.item.extension,
            "color": self.item.color,
            "description": self.item.description,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the indicator to red."""
        await self._async_set(COLOR_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the indicator to green."""
        await self._async_set(COLOR_OFF)

    async def _async_set(self, color: str) -> None:
        try:
            await self.coordinator.async_set_function_indicator(self.item_id, color)
        except VoipCenterError as err:
            raise HomeAssistantError(
                f"Could not set function indicator {self.item_id}: {err}"
            ) from err
