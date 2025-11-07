import logging
import os

from PIL import Image

from pyscreenshot.plugins.backend import UNKNOWN_VERSION, CBackend

class FreedesktopDBusError(Exception):
    pass

has_jeepney = False
try:
    from jeepney import DBusAddress, new_method_call
    from jeepney.bus_messages import MatchRule, message_bus
    from jeepney.io.blocking import Proxy, open_dbus_connection

    has_jeepney = True
except ImportError:
    pass

if not has_jeepney:
    raise FreedesktopDBusError("jeepney library is missing")


log = logging.getLogger(__name__)


class FreedesktopDBusWrapper(CBackend):
    name = "freedesktop_dbus"
    is_subprocess = True

    def __init__(self) -> None:

        self.portal = DBusAddress(
            object_path="/org/freedesktop/portal/desktop",
            bus_name="org.freedesktop.portal.Desktop",
        )


    def grab(self, bbox=None):
        screenshot = self.portal.with_interface("org.freedesktop.portal.Screenshot")

        token = "pyscreenshot"
        sender_name = self.conn.unique_name[1:].replace(".", "_")
        handle = f"/org/freedesktop/portal/desktop/request/{sender_name}/{token}"

        response_rule = MatchRule(
            type="signal", interface="org.freedesktop.portal.Request", path=handle
        )
        Proxy(message_bus, self.conn).AddMatch(response_rule)

        with self.conn.filter(response_rule) as responses:
            req = new_method_call(
                screenshot,
                "Screenshot",
                "sa{sv}",
                ("", {"handle_token": ("s", token), "interactive": ("b", False)}),
            )
            self.conn.send_and_get_reply(req)
            response_msg = self.conn.recv_until_filtered(responses)

        response, results = response_msg.body

        im = False
        if response == 0:
            filename = results["uri"][1].split("file://", 1)[-1]
            if os.path.isfile(filename):
                im = Image.open(filename)
                os.remove(filename)

        if bbox and im:
            im = im.crop(bbox)
        return im

    def backend_version(self):
        return UNKNOWN_VERSION
    
    def __enter__(self):
        self.conn = open_dbus_connection()

        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.close()
    
    
