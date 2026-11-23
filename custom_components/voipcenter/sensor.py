"""Sensors for the VoipCenter integration."""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from aiovoipcenter.types import Record, Voicemail

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .call_stats import CallTotals, MonthTotals, VoipCenterCallStatsCoordinator
from .const import CONF_WS_KEY, CONF_WS_USERNAME
from .coordinator import VoipCenterConfigEntry, VoipCenterCoordinator
from .entity import (
    ServiceItemEntity,
    SipAccountEntity,
    VoipCenterEntity,
    async_add_item_entities,
    service_device_info,
    sip_account_device_info,
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
        return [
            SipAccountStateSensor(coordinator, item_id, "call_state"),
            OutgoingMinutesSensor(coordinator, item_id),
        ]

    def _voicemail_factory(
        coordinator: VoipCenterCoordinator, item_id: int
    ) -> list[SensorEntity]:
        return [VoicemailMessagesSensor(coordinator, item_id, "voicemail_messages")]

    async_add_item_entities(entry, async_add_entities, "sip_accounts", _sip_factory)
    async_add_item_entities(
        entry, async_add_entities, "voicemailboxes", _voicemail_factory
    )

    call_stats = coordinator.call_stats
    known_dialplans: set[int] = set()

    @callback
    def _add_forwarding_dialplans() -> None:
        if call_stats.data is None:
            return
        new_ids = set(call_stats.data.forwarding_dialplans) - known_dialplans
        if not new_ids:
            return
        known_dialplans.update(new_ids)
        async_add_entities(
            ForwardedMinutesSensor(coordinator, dialplan_id)
            for dialplan_id in sorted(new_ids)
        )

    _add_forwarding_dialplans()
    entry.async_on_unload(call_stats.async_add_listener(_add_forwarding_dialplans))


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
        return {
            "conversations": [
                asdict(conversation)
                for conversation in self.coordinator.data.conversations
            ]
        }


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
        state = self.item.currentState
        return str(state).lower() if state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the SIP account details."""
        account = self.item
        return {
            "id": self.item_id,
            "extension": account.extension,
            "sip_username": account.sipUsername,
            "user_agent": account.userAgent,
            "ip_address": account.ipAddress,
        }


class VoicemailMessagesSensor(ServiceItemEntity[Voicemail], SensorEntity):
    """Number of messages in a voicemail box."""

    _collection = "voicemailboxes"
    _model = Voicemail
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the number of messages in the inbox."""
        messages: Any = self.item.messages
        # The API returns the count per folder, e.g. {"inbox": 3, "logging": 0};
        # its documentation describes a plain number.
        if isinstance(messages, Record):
            messages = messages.get("inbox")
        try:
            return int(messages)  # type: ignore[arg-type]
        except TypeError, ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the voicemail box details and the count of the other folders."""
        attributes = {"id": self.item_id, "extension": self.item.extension}
        if isinstance(messages := self.item.messages, Record):
            attributes.update(
                {f"{folder}_messages": messages[folder] for folder in messages}
            )
        return attributes


class CallMinutesSensor(
    CoordinatorEntity[VoipCenterCallStatsCoordinator], SensorEntity
):
    """Talk time this month; resets at the start of every month.

    With ``state_class: total`` and ``last_reset`` at the start of the month,
    the long-term statistics keep the total of every month.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: VoipCenterCoordinator, item_id: int, key: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator.call_stats)
        self.item_id = item_id
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{key}_{item_id}"
        self._attr_translation_key = key

    def _totals(self, month: MonthTotals) -> CallTotals:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Return whether the call records have been read."""
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        """Return the minutes of this month."""
        if self.coordinator.data is None:
            return None
        return self._totals(self.coordinator.data.current).minutes

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of this month."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.month_start

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the calls of this month and the totals of the previous month."""
        if self.coordinator.data is None:
            return None
        current = self._totals(self.coordinator.data.current)
        previous = self._totals(self.coordinator.data.previous)
        return {
            "calls": current.calls,
            "answered_calls": current.answered_calls,
            "previous_month_minutes": previous.minutes,
            "previous_month_calls": previous.calls,
            "previous_month_answered_calls": previous.answered_calls,
        }


class OutgoingMinutesSensor(CallMinutesSensor):
    """Minutes of outgoing calls of a SIP account this month."""

    def __init__(self, coordinator: VoipCenterCoordinator, item_id: int) -> None:
        """Initialize the sensor on the device of the SIP account."""
        super().__init__(coordinator, item_id, "outgoing_minutes")
        self._attr_device_info = sip_account_device_info(coordinator, item_id)

    def _totals(self, month: MonthTotals) -> CallTotals:
        return month.outgoing.get(self.item_id, CallTotals())


class ForwardedMinutesSensor(CallMinutesSensor):
    """Minutes of calls a dialplan forwarded to an external number this month."""

    def __init__(self, coordinator: VoipCenterCoordinator, item_id: int) -> None:
        """Initialize the sensor on the service device, named after the dialplan."""
        super().__init__(coordinator, item_id, "forwarded_minutes")
        self._attr_device_info = service_device_info(coordinator)
        data = coordinator.call_stats.data
        name = data.forwarding_dialplans.get(item_id) if data else None
        self._attr_translation_placeholders = {"name": name or str(item_id)}

    def _totals(self, month: MonthTotals) -> CallTotals:
        return month.forwarded.get(self.item_id, CallTotals())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the call counts, plus the numbers forwarded to this month.

        ``unknown_route_calls`` counts the calls of the month (of all dialplans)
        whose route PBXonline no longer has, so they may be missing here.
        """
        attributes = super().extra_state_attributes
        if attributes is None or self.coordinator.data is None:
            return attributes
        data = self.coordinator.data
        attributes["unknown_route_calls"] = data.current.unknown_route_calls
        attributes["previous_month_unknown_route_calls"] = (
            data.previous.unknown_route_calls
        )
        numbers = data.current.forward_numbers.get(self.item_id)
        return {
            "dialplan_id": self.item_id,
            **attributes,
            "numbers": sorted(numbers or ()),
        }
