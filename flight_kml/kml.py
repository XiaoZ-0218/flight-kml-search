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
    return (
        f"Flight {display_name} on {date_str} (callsign {callsign}). "
        f"{len(points)} ADS-B positions, {iso(points[0][0])} to "
        f"{iso(points[-1][0])} UTC. Altitude is barometric, metres. "
        f"Track source: {source}."
    )


def build_kml(points, name, description=""):
    """points: cleaned [(ts, lon, lat, alt_m), ...]; returns KML text."""
    if not points:
        raise ValueError("track has no usable points")
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
