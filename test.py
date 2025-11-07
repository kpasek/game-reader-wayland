#!/usr/bin/env python3
import gi
import time
import dbus
import numpy as np
from PIL import Image
gi.require_version("Gst", "1.0")
from gi.repository import Gst

Gst.init(None)

import uuid

def request_pipewire_stream():
    """
    Tworzy sesję screen-capture przez portal KDE i zwraca node_id PipeWire.
    """
    session_bus = dbus.SessionBus()
    proxy = session_bus.get_object("org.freedesktop.portal.Desktop",
                                   "/org/freedesktop/portal/desktop")
    iface = dbus.Interface(proxy, "org.freedesktop.portal.ScreenCast")

    token = uuid.uuid4().hex
    app_id = "python.capture"

    # 1️⃣ Utwórz sesję
    options = {"session_handle_token": dbus.String(token)}
    reply = iface.CreateSession(options)
    session_handle = reply[1]  # "/org/freedesktop/portal/desktop/session/..."

    # 2️⃣ Wybierz źródło (1 = monitor, 2 = okno)
    iface.SelectSources(
        session_handle,
        {"types": dbus.UInt32(1), "multiple": False},
    )

    # 3️⃣ Uruchom sesję
    iface.Start(
        session_handle,
        app_id,
        {"handle_token": dbus.String(token)},
    )

    # 4️⃣ Pobierz wynik
    props_iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    session_props = props_iface.Get(
        "org.freedesktop.portal.ScreenCast",
        session_handle,
    )

    # 5️⃣ Pobierz node_id (PipeWire stream)
    streams = session_props.get("Streams")
    node_id = int(streams[0]["node_id"])
    return node_id

def create_pipeline(node_id, x, y, w, h):
    pipeline_str = (
        f"pipewiresrc path={node_id} do-timestamp=true ! "
        f"videoconvert ! "
        f"videocrop top={y} left={x} right=0 bottom=0 ! "
        f"videoscale ! "
        f"width={w},height={h} ! "
        f"appsink name=sink emit-signals=true max-buffers=1 drop=true"
    )
    print("Pipeline:", pipeline_str)
    pipeline = Gst.parse_launch(pipeline_str)
    return pipeline

def capture_frame(appsink, filename):
    sample = appsink.emit("pull-sample")
    if not sample:
        print("⚠️ Brak klatki")
        return
    buffer = sample.get_buffer()
    caps = sample.get_caps()
    s = caps.get_structure(0)
    w, h = s.get_value("width"), s.get_value("height")
    result, mapinfo = buffer.map(Gst.MapFlags.READ)
    if not result:
        return
    arr = np.frombuffer(mapinfo.data, dtype=np.uint8).reshape(h, w, 3)
    img = Image.fromarray(arr)
    img.save(filename)
    buffer.unmap(mapinfo)
    print(f"✅ Zapisano {filename}")

if __name__ == "__main__":
    x, y, w, h = 100, 200, 400, 300
    node_id = request_pipewire_stream()
    pipeline = create_pipeline(node_id, x, y, w, h)
    appsink = pipeline.get_by_name("sink")

    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(1)  # Daj czas na inicjalizację

    try:
        for i in range(5):
            capture_frame(appsink, f"shot_{i}.png")
            time.sleep(0.5)
    finally:
        pipeline.set_state(Gst.State.NULL)
