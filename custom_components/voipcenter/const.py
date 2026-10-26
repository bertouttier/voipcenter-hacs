"""Constants for the VoipCenter integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "voipcenter"

# The version segment changes with PBXonline releases; when it no longer
# exists, the current one is read from the PBXonline web app.
API_BASE_URL: Final = "https://api.pbxonline.be/v2/261001"
WEB_APP_SCRIPT_URL: Final = "https://pbxonline.be/v7/js/app.js"

CONF_WS_URL: Final = "ws_url"
CONF_WS_USERNAME: Final = "ws_username"
CONF_WS_KEY: Final = "ws_key"

DEFAULT_WS_URL: Final = "https://ws1.voipcenter.be:4123"

UPDATE_INTERVAL: Final = timedelta(seconds=30)

# Fired for every realtime "notify" message received over the websocket.
# Same event type as version 1.x of the integration, so automations keep working.
EVENT_CALL: Final = DOMAIN

SERVICE_START_CALL: Final = "start_call"
SERVICE_END_CALL: Final = "end_call"
SERVICE_TRANSFER_CALL: Final = "transfer_call"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_SIP_ACCOUNT_ID: Final = "sip_account_id"
ATTR_DESTINATION: Final = "destination"
ATTR_CONVERSATION_ID: Final = "conversation_id"
