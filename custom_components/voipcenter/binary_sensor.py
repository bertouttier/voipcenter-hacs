"""Binary sensors for the VoipCenter integration."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_WS_KEY, CONF_WS_USERNAME
from .coordinator import VoipCenterConfigEntry, VoipCenterCoordinator
from .entity import SipAccountEntity, VoipCenterEntity, async_add_item_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoipCenterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up VoipCenter binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [InCallBinarySensor(coordinator, "in_call")]
    if entry.options.get(CONF_WS_USERNAME) and entry.options.get(CONF_WS_KEY):
        entities.append(WebsocketBinarySensor(coordinator, "websocket"))
    async_add_entities(entities)

    def _sip_factory(
        coordinator: VoipCenterCoordinator, item_id: int
    ) -> list[BinarySensorEntity]:
        return [
            SipRegisteredBinarySensor(coordinator, item_id, "registered"),
            SipAvailableBinarySensor(coordinator, item_id, "presence"),
        ]

    async_add_item_entities(entry, async_add_entities, "sip_accounts", _sip_factory)


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


class InCallBinarySensor(VoipCenterEntity, BinarySensorEntity):
    """On while there is at least one ongoing conversation."""

    @property
    def is_on(self) -> bool:
        """Return whether a conversation is ongoing."""
        return bool(self.coordinator.data.conversations)


class WebsocketBinarySensor(VoipCenterEntity, BinarySensorEntity):
    """Connection state of the realtime websocket."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return whether the websocket is connected."""
        return self.coordinator.data.websocket_connected


class SipRegisteredBinarySensor(SipAccountEntity, BinarySensorEntity):
    """Whether a SIP client is registered on the account."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        """Return whether the SIP account is registered."""
        return _as_bool(self.item.get("regStatus"))


class SipAvailableBinarySensor(SipAccountEntity, BinarySensorEntity):
    """Presence (availability) of a SIP account."""

    @property
    def is_on(self) -> bool | None:
        """Return whether the SIP account is available."""
        return _as_bool(self.item.get("availability"))
