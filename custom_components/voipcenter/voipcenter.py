import logging
import hmac
import hashlib
from datetime import datetime
import requests
import json

from socketio import AsyncClient

from .const import (
    DOMAIN,
    VOIPCENTER_API_ENDPOINT,
    VOIPCENTER_WS_ENDPOINT
)

_LOGGER = logging.getLogger(__name__)


class VoipcenterApi:
    """
    Simple class to implement the Voipcenter API.
    Currently only supports getting and updating function indicators.

    This should become a more extensive python library uploaded to pypi.
    """

    def __init__(self, hass, apiid, key, klantnummer, password, ws_username=None):
        self._hass = hass
        self._apiid = apiid
        self._apikey = key
        self._klantnummer = klantnummer
        self._hashedpassword = hashlib.sha256(hashlib.md5(password.encode('utf-8')).hexdigest().encode('utf-8')).hexdigest()
        self._session = hass.helpers.aiohttp_client.async_get_clientsession()
        self._ws_username = ws_username
        self._sio = AsyncClient(logger=_LOGGER, engineio_logger=_LOGGER, ssl_verify=False)

    async def connect_ws(self):
        """
        Connect the websocket and generate events
        """
        if self._ws_username is None:
            _LOGGER.warning("No websocket username configured, cannot connect")
            return

        try:
            credentials = await self.get_ws_pass(self._ws_username)
        except:
            _LOGGER.error("No credentials!")
            return

        if ("username" not in credentials) or ("wskey" not in credentials):
            _LOGGER.error(credentials)
            return

        # connect event callback
        async def _async_on_connect():
            _LOGGER.info("Websocket connected with sid %s", self._sio.sid)

        self._sio.on("connect", _async_on_connect)

        # disconnect event callback
        async def _async_on_disconnect():
            _LOGGER.info("disconnect")

        self._sio.on("disconnect", _async_on_disconnect)

        # serveroutput event callback
        async def _async_on_serveroutput(data):
            _LOGGER.debug(data)
            _LOGGER.info("Trying to register...")
            await self._sio.emit("register", { "username": credentials["username"], "wskey": credentials["wskey"] })

        self._sio.on("serveroutput", _async_on_serveroutput)

        # Notify event callback
        async def _async_on_notify(data):
            _LOGGER.debug("Notify received")
            _LOGGER.debug(data)
            self._hass.bus.fire(DOMAIN, data)

        self._sio.on("notify", _async_on_notify)

        await self._sio.connect(VOIPCENTER_WS_ENDPOINT)

    async def disconnect_ws(self):
        """
        Disconnect the websocket
        """
        if self._ws_username is None:
            _LOGGER.debug("No websocket client")
            return
        await self._sio.disconnect()

    def generate_dig(self, values):
        """
        Generate the pass value.
        Here we assume that we are using python 3.6 and that the
        values of the dictionary are keeping their order.
        """
        passtobehashed = ''
        for key, value in values.items():
            passtobehashed = passtobehashed + key + value

        return hmac.new(self._apikey.encode('utf-8'), msg=passtobehashed.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()

    async def get_fi(self, id):
        url = VOIPCENTER_API_ENDPOINT + 'get.php'

        values = {
            'apiID' : self._apiid,
            'knummer' : self._klantnummer,
            'pwd' : self._hashedpassword,
            'm' : 'indicator',
            'id' : id,
            'f' : 'json',
            'ts': datetime.now().strftime('%s')
        }

        values['pass'] = self.generate_dig(values)

        r = await self._session.get(url, params=values)
        return await r.json(content_type='text/json charset=utf-8')

    async def activate_fi(self, id, activate):
        url = VOIPCENTER_API_ENDPOINT + 'update.php'

        values = {
            'apiID' : self._apiid,
            'knummer' : self._klantnummer,
            'pwd' : self._hashedpassword,
            'm' : 'indicator',
            'id' : id,
            'p' : '1' if activate else '0',
            'f' : 'json',
            'ts': datetime.now().strftime('%s')
        }

        values['pass'] = self.generate_dig(values)

        r = await self._session.get(url, params=values)
        d = await r.json(content_type='text/json charset=utf-8')
        return d['body']['status'] == '1'

    async def get_ws_pass(self, ws_username):
        url = VOIPCENTER_API_ENDPOINT + 'get.php'

        values = {
            'apiID' : self._apiid,
            'knummer' : self._klantnummer,
            'pwd' : self._hashedpassword,
            'm' : 'wskey',
            'id' : ws_username,
            'f' : 'json',
            'ts': datetime.now().strftime('%s')
        }

        values['pass'] = self.generate_dig(values)

        r = await self._session.post(url, data=values)
        return await r.json(content_type='text/json charset=utf-8')

    def get_device_info(self):
        return {
            "identifiers": {(DOMAIN, self._klantnummer)},
            "name": self._klantnummer,
            "model": "unknown",
            "sw_version": "1.0.0",
            "manufacturer": "voipcenter"
        }