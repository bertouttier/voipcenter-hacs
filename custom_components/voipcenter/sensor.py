"""Sensors for the VoipCenter integration."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_WS_KEY, CONF_WS_USERNAME
from .coordinator import VoipCenterConfigEntry, VoipCenterCoordinator
from .entity import (
    ServiceItemEntity,
    SipAccountEntity,
    VoipCenterEntity,
    async_add_item_entities,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoipCenterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up VoipCenter sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [OngoingCallsSensor(coordinator, "ongoing_calls")]
    if entry.options.get(CONF_WS_USERNAME) and entry.options.get(CONF_WS_KEY):
        entities.append(LastCallEventSensor(coordinator, "last_call_event"))
    async_add_entities(entities)

    def _sip_factory(
        coordinator: VoipCenterCoordinator, item_id: int
    ) -> list[SensorEntity]:
        return [SipAccountStateSensor(coordinator, item_id, "call_state")]

    def _voicemail_factory(
        coordinator: VoipCenterCoordinator, item_id: int
    ) -> list[SensorEntity]:
        return [VoicemailMessagesSensor(coordinator, item_id, "voicemail_messages")]

    async_add_item_entities(entry, async_add_entities, "sip_accounts", _sip_factory)
    async_add_item_entities(
        entry, async_add_entities, "voicemailboxes", _voicemail_factory
    )


class OngoingCallsSensor(VoipCenterEntity, SensorEntity):
    """Number of ongoing conversations."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Return the number of ongoing conversations."""
        return len(self.coordinator.data.conversations)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the ongoing conversations."""
        return {"conversations": self.coordinator.data.conversations}


class LastCallEventSensor(VoipCenterEntity, SensorEntity):
    """Time and details of the last realtime call notification."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return when the last call notification was received."""
        return self.coordinator.data.last_call_event_time

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the details of the last call notification."""
        return self.coordinator.data.last_call_event


class SipAccountStateSensor(SipAccountEntity, SensorEntity):
    """Call state of a SIP account (idle / calling / ringing)."""

    @property
    def native_value(self) -> str | None:
        """Return the current state of the SIP account."""
        state = self.item.get("currentState")
        return str(state).lower() if state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the SIP account details."""
        account = self.item
        return {
            "id": self.item_id,
            "extension": account.get("extension"),
            "sip_username": account.get("sipUsername"),
            "user_agent": account.get("userAgent"),
            "ip_address": account.get("ipAddress"),
        }


class VoicemailMessagesSensor(ServiceItemEntity, SensorEntity):
    """Number of messages in a voicemail box."""

    _collection = "voicemailboxes"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the number of messages."""
        try:
            return int(self.item["messages"])
        except KeyError, TypeError, ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the voicemail box details."""
        return {"id": self.item_id, "extension": self.item.get("extension")}
