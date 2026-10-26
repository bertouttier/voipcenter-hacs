"""Base entities for the VoipCenter integration."""

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.const import CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VoipCenterConfigEntry, VoipCenterCoordinator


def _service_identifier(coordinator: VoipCenterCoordinator) -> tuple[str, str]:
    entry = coordinator.config_entry
    return (DOMAIN, entry.unique_id or entry.entry_id)


class VoipCenterEntity(CoordinatorEntity[VoipCenterCoordinator]):
    """An entity belonging to the VoipCenter service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VoipCenterCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={_service_identifier(coordinator)},
            name=f"VoipCenter {entry.data[CONF_USERNAME]}",
            manufacturer="VoipCenter",
            model="VoipCenter",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://pbxonline.be",
        )


class VoipCenterItemEntity(CoordinatorEntity[VoipCenterCoordinator]):
    """An entity for one item (SIP account, indicator, mailbox) of the PBX."""

    _attr_has_entity_name = True
    # Name of the VoipCenterData attribute holding the items, keyed by ID.
    _collection: str

    def __init__(
        self, coordinator: VoipCenterCoordinator, item_id: int, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.item_id = item_id
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{key}_{item_id}"
        self._attr_translation_key = key

    @property
    def item(self) -> dict[str, Any]:
        """Return the current API data of this item."""
        return getattr(self.coordinator.data, self._collection).get(self.item_id, {})

    @property
    def available(self) -> bool:
        """Return whether the item still exists."""
        return super().available and self.item_id in getattr(
            self.coordinator.data, self._collection
        )


class SipAccountEntity(VoipCenterItemEntity):
    """An entity on the device of a SIP account."""

    _collection = "sip_accounts"

    def __init__(
        self, coordinator: VoipCenterCoordinator, item_id: int, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, item_id, key)
        account = self.item
        name = account.get("logicalName") or account.get("sipUsername") or item_id
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, f"{coordinator.config_entry.unique_id}_sip_{item_id}")
            },
            name=str(name),
            manufacturer="VoipCenter",
            model="SIP account",
            serial_number=account.get("sipUsername"),
            via_device=_service_identifier(coordinator),
        )


class ServiceItemEntity(VoipCenterItemEntity):
    """An item entity on the VoipCenter service device, named after the item."""

    def __init__(
        self, coordinator: VoipCenterCoordinator, item_id: int, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, item_id, key)
        self._attr_device_info = DeviceInfo(
            identifiers={_service_identifier(coordinator)}
        )
        self._attr_translation_placeholders = {
            "name": str(self.item.get("logicalName") or item_id)
        }


@callback
def async_add_item_entities(
    entry: VoipCenterConfigEntry,
    async_add_entities: Callable[[Iterable[Entity]], None],
    collection: str,
    factory: Callable[[VoipCenterCoordinator, int], Iterable[Entity]],
) -> None:
    """Add entities for every item in a collection, now and when new ones appear."""
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new() -> None:
        new_ids = set(getattr(coordinator.data, collection)) - known
        if not new_ids:
            return
        known.update(new_ids)
        async_add_entities(
            [
                entity
                for item_id in sorted(new_ids)
                for entity in factory(coordinator, item_id)
            ]
        )

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
