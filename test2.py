import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import uuid

def request_pipewire_stream():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    session_bus = dbus.SessionBus()

    portal_obj = session_bus.get_object(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop"
    )
    portal_iface = dbus.Interface(portal_obj, "org.freedesktop.portal.ScreenCast")

    loop = GLib.MainLoop()
    token = uuid.uuid4().hex
    app_id = "python.capture"

    session_handle = None
    node_id = None

    def on_response(response_id, results):
        nonlocal session_handle
        if response_id != 0:
            print("❌ Portal refused session creation:", results)
            loop.quit()
            return
        session_handle = results["session_handle"]
        print("✅ Session created:", session_handle)
        loop.quit()

    portal_iface.connect_to_signal("Response", on_response)
    portal_iface.CreateSession({"session_handle_token": dbus.String(token)})
    loop.run()

    if not session_handle:
        raise RuntimeError("Nie udało się uzyskać sesji Portal ScreenCast")

    # 🔸 Select monitor
    loop = GLib.MainLoop()

    def on_select_sources(response_id, results):
        if response_id != 0:
            print("❌ SelectSources error:", results)
        else:
            print("✅ Source selected")
        loop.quit()

    portal_iface.connect_to_signal("Response", on_select_sources)
    portal_iface.SelectSources(
        session_handle,
        {"types": dbus.UInt32(1), "multiple": False}
    )
    loop.run()

    # 🔸 Start stream
    loop = GLib.MainLoop()

    def on_start(response_id, results):
        nonlocal node_id
        if response_id != 0:
            print("❌ Start error:", results)
        else:
            streams = results.get("streams")
            if streams and "node_id" in streams[0]:
                node_id = streams[0]["node_id"]
                print("✅ node_id =", node_id)
        loop.quit()

    portal_iface.connect_to_signal("Response", on_start)
    portal_iface.Start(session_handle, app_id, {"handle_token": dbus.String(token)})
    loop.run()

    if not node_id:
        raise RuntimeError("Nie udało się uzyskać node_id z PipeWire")

    return node_id


if __name__ == "__main__":
    node = request_pipewire_stream()
    print("🎥 node_id =", node)
