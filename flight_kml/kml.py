"""Build a KML flight track from an OpenSky path.

Each path point is [unix_time, lat, lon, baro_alt_m, true_track, on_ground];
any of lat/lon/alt may be None. Output uses a gx:Track (timestamps + 3D
coords, the format Google Earth animates) plus a plain LineString for
viewers without gx support.
"""
import datetime
import xml.etree.ElementTree as ET

KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"

ET.register_namespace("", KML_NS)
ET.register_namespace("gx", GX_NS)


def iso(ts):
    return (
        datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def describe_flight(display_name, date_str, callsign, points, source):
    span = (f"{iso(points[0][0])} to {iso(points[-1][0])} UTC"
            if points else "no usable positions")
    return (
        f"Flight {display_name} on {date_str} (callsign {callsign}). "
        f"{len(points)} ADS-B positions, {span}. Altitude is barometric, "
        f"metres. Track source: {source}."
    )


def _fill_altitudes(points):
    """Replace None altitudes with the nearest known value (forward, then
    backward for any leading run). Ground points at elevated airports
    shouldn't sink to 0 m under absolute altitudeMode."""
    filled = list(points)
    last = None
    for i, (ts, lon, lat, alt) in enumerate(filled):
        if alt is None:
            if last is not None:
                filled[i] = (ts, lon, lat, last)
        else:
            last = alt
    nxt = None
    for i in range(len(filled) - 1, -1, -1):
        ts, lon, lat, alt = filled[i]
        if alt is None:
            if nxt is not None:
                filled[i] = (ts, lon, lat, nxt)
        else:
            nxt = alt
    return [(ts, lon, lat, 0.0 if alt is None else alt)
            for ts, lon, lat, alt in filled]


def build_kml(points, name, description=""):
    """points: cleaned [(ts, lon, lat, alt_m|None), ...]; returns KML text."""
    if not points:
        raise ValueError("track has no usable points")
    points = _fill_altitudes(points)
    kml = ET.Element(f"{{{KML_NS}}}kml")
    doc = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    ET.SubElement(doc, f"{{{KML_NS}}}name").text = name
    if description:
        ET.SubElement(doc, f"{{{KML_NS}}}description").text = description

    style = ET.SubElement(doc, f"{{{KML_NS}}}Style", id="trackStyle")
    line = ET.SubElement(style, f"{{{KML_NS}}}LineStyle")
    ET.SubElement(line, f"{{{KML_NS}}}color").text = "ff00a5ff"  # orange, aabbggrr
    ET.SubElement(line, f"{{{KML_NS}}}width").text = "3"

    placemark = ET.SubElement(doc, f"{{{KML_NS}}}Placemark")
    ET.SubElement(placemark, f"{{{KML_NS}}}name").text = name
    ET.SubElement(placemark, f"{{{KML_NS}}}styleUrl").text = "#trackStyle"

    track = ET.SubElement(placemark, f"{{{GX_NS}}}Track")
    ET.SubElement(track, f"{{{KML_NS}}}altitudeMode").text = "absolute"
    for ts, lon, lat, alt in points:
        ET.SubElement(track, f"{{{KML_NS}}}when").text = iso(ts)
    for ts, lon, lat, alt in points:
        ET.SubElement(track, f"{{{GX_NS}}}coord").text = f"{lon:.6f} {lat:.6f} {alt:.0f}"

    linestring_pm = ET.SubElement(doc, f"{{{KML_NS}}}Placemark")
    ET.SubElement(linestring_pm, f"{{{KML_NS}}}name").text = f"{name} (path)"
    ET.SubElement(linestring_pm, f"{{{KML_NS}}}styleUrl").text = "#trackStyle"
    ls = ET.SubElement(linestring_pm, f"{{{KML_NS}}}LineString")
    ET.SubElement(ls, f"{{{KML_NS}}}altitudeMode").text = "absolute"
    ET.SubElement(ls, f"{{{KML_NS}}}coordinates").text = " ".join(
        f"{lon:.6f},{lat:.6f},{alt:.0f}" for _, lon, lat, alt in points
    )

    return ET.tostring(kml, encoding="unicode", xml_declaration=True)
