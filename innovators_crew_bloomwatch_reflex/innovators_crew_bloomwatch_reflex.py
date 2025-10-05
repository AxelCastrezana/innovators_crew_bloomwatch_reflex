import os
from io import BytesIO
import reflex as rx
import requests
import math
from urllib.parse import urlparse, quote
from urllib.parse import urlsplit
import json as _json  # keep a lightweight alias if needed elsewhere
import folium
from folium.plugins import Draw, MousePosition
from datetime import date, datetime, timedelta, timezone
from time import time
import xml.etree.ElementTree as ET

# Gradio client for the crop classification Space
try:
    from gradio_client import Client, handle_file
except Exception:
    Client = None
    def handle_file(x):
        return x

# Rasterio/numpy for tile fetch
try:
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.transform import Affine
    import numpy as np
except Exception:
    rasterio = None
    np = None

import re

# Toggle to show/hide the Leaflet (Folium) layer control inside the map iframe.
# Keep this False to rely on the Reflex dropdown instead of Leaflet's UI.
SHOW_LEAFLET_LAYER_CONTROL = False

WMS_CAP_URL = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?SERVICE=WMS&REQUEST=GetCapabilities"
WMS_BASE_URL = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"

# Stores per-layer time metadata
LAYER_TIME_DEFAULT = {}
LAYER_TIME_VALUES = {}

def list_wms_layers(cap_url: str) -> list[str]:
    try:
        r = requests.get(cap_url, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"wms": "http://www.opengis.net/wms", "xlink": "http://www.w3.org/1999/xlink"}
        layers = []
        # Find any nested Layer elements under the top-level Capability/Layer
        for lyr in root.findall(".//wms:Capability/wms:Layer//wms:Layer", ns):
            name_el = lyr.find("wms:Name", ns)
            if name_el is None or not name_el.text:
                continue
            lid = name_el.text.strip()
            if lid:
                layers.append(lid)
            # Time dimension (WMS 1.3.0 uses wms:Dimension name="time")
            time_dim = None
            for dim in lyr.findall("wms:Dimension", ns):
                if dim.get("name", "").lower() == "time":
                    time_dim = dim
                    break
            if time_dim is not None and (time_dim.text or "").strip():
                raw = time_dim.text.strip()
                vals = [v.strip() for v in raw.split(",") if v.strip()]
                if vals:
                    LAYER_TIME_VALUES[lid] = vals
                    LAYER_TIME_DEFAULT[lid] = vals[-1]
        return sorted(set(layers))
    except Exception as e:
        print(f"[WMS caps] Failed to fetch/parse capabilities: {e}")
        return []

AVAILABLE_LAYERS = list_wms_layers(WMS_CAP_URL)
print(f"GIBS WMS: found {len(AVAILABLE_LAYERS)} layers")
try:
    if AVAILABLE_LAYERS:
        print("First 5:")
        for one in sorted(AVAILABLE_LAYERS)[:5]:
            print("  ", one)
        print("...")
        print("Last 5:")
        for one in sorted(AVAILABLE_LAYERS)[-5:]:
            print("  ", one)
except Exception as _e:
    pass


# --- WMS time helper ---
def _choose_time(layer_id: str, desired_date: str | None) -> str:
    allowed = LAYER_TIME_VALUES.get(layer_id)
    if allowed:
        if desired_date and desired_date.strip() in allowed:
            return desired_date.strip()
        return LAYER_TIME_DEFAULT.get(layer_id, allowed[-1])
    return (desired_date or date.today().isoformat())

def _safe_float(s: str | None) -> float | None:
    try:
        return float(s) if s is not None and s != "" else None
    except Exception:
        return None

# --- Layer filename helper ---
def _slug(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in s)[:80]

# ---- HLS Tile Fetch: Geocoder, helpers ----
CMR_STAC_ROOT = "https://cmr.earthdata.nasa.gov/stac/LPCLOUD"
HLS_COLLECTIONS = ["HLSS30.v2.0", "HLSL30.v2.0"]  # Sentinel-2 & Landsat-8/9 (v2)

def _geocode_address(q: str) -> tuple[float, float] | None:
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 0}, headers={"User-Agent": "bloomwatch/1.0"}, timeout=15)
        r.raise_for_status()
        js = r.json()
        if js:
            return (float(js[0]["lat"]), float(js[0]["lon"]))
    except Exception as e:
        print("[geocode]", e)
    return None

def _deg_buffer(lat: float, meters: float) -> tuple[float, float]:
    # approximate conversion meters -> degrees
    dlat = meters / 111_320.0
    dlon = meters / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return dlat, dlon

def _search_hls_items(lat: float, lon: float, dt: str, limit: int = 10):
    # Search within +/- 15 days around requested date, clamp end to today, RFC3339 interval
    t0 = datetime.fromisoformat(dt)
    start_date = (t0 - timedelta(days=15)).date()
    end_date = (t0 + timedelta(days=15)).date()
    today = date.today()
    if end_date > today:
        end_date = today
    # RFC3339 closed interval covering full days
    start = f"{start_date.isoformat()}T00:00:00Z"
    end = f"{end_date.isoformat()}T23:59:59Z"
    if start_date > end_date:
        return []

    headers = {
        "Accept": "application/geo+json",
        "Content-Type": "application/json",
    }

    # 1) Preferred: POST with intersects (no sortby; we'll sort client-side)
    body = {
        "collections": HLS_COLLECTIONS,
        "limit": limit,
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{start}/{end}",
    }
    try:
        r = requests.post(f"{CMR_STAC_ROOT}/search", json=body, headers=headers, timeout=30)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if feats:
            return feats
    except Exception as e:
        print("[stac search POST intersects]", e)

    # 2) Fallback: POST with a tiny bbox around point
    try:
        dlat, dlon = _deg_buffer(lat, 200.0)
        south, north = lat - dlat, lat + dlat
        west, east = lon - dlon, lon + dlon
        body_bbox = {
            "collections": HLS_COLLECTIONS,
            "limit": limit,
            "bbox": [west, south, east, north],
            "datetime": f"{start}/{end}",
        }
        r2 = requests.post(f"{CMR_STAC_ROOT}/search", json=body_bbox, headers=headers, timeout=30)
        r2.raise_for_status()
        feats = r2.json().get("features", [])
        if feats:
            return feats
    except Exception as e2:
        print("[stac search POST bbox]", e2)

    # 3) Last fallback: per-collection items GET (some servers prefer this)
    feats_all = []
    try:
        dlat, dlon = _deg_buffer(lat, 200.0)
        south, north = lat - dlat, lat + dlat
        west, east = lon - dlon, lon + dlon
        for coll in HLS_COLLECTIONS:
            params = {
                "limit": str(limit),
                "bbox": f"{west},{south},{east},{north}",
                "datetime": f"{start}/{end}",
            }
            r3 = requests.get(f"{CMR_STAC_ROOT}/collections/{coll}/items", params=params, headers={"Accept": "application/geo+json"}, timeout=30)
            r3.raise_for_status()
            feats = r3.json().get("features", [])
            feats_all.extend(feats)
        return feats_all
    except Exception as e3:
        print("[stac search per-collection GET]", e3)
        # 4) Granule search fallback (metadata only) – returns [] on failure
        try:
            params = {
                "short_name": ["HLSS30", "HLSL30"],
                "temporal": f"{start}/{end}",
                "page_size": 10,
                "provider": "LPDAAC_ECS",
                "bounding_box": f"{west},{south},{east},{north}",
            }
            r4 = requests.get("https://cmr.earthdata.nasa.gov/search/granules.json", params=params, timeout=30)
            r4.raise_for_status()
            js = r4.json()
            hits = js.get("feed", {}).get("entry", [])
            # We don't transform to STAC here; use as a signal to the caller
            if hits:
                # fabricate minimal STAC-like features list with collection + datetime only
                feats = []
                for g in hits[:limit]:
                    dt = (g.get("time_start") or "")
                    coll = g.get("dataset_id", "")
                    feats.append({"collection": "HLSS30.v2.0" if "HLSS30" in coll else "HLSL30.v2.0", "properties": {"datetime": dt}})
                return feats
        except Exception as e4:
            print("[cmr granule fallback]", e4)
        return []

# Map each collection to the bands we will pull in this order:
# Blue, Green, Red, Narrow NIR, SWIR1, SWIR2
S30_BANDS = ["B02", "B03", "B04", "B8A", "B11", "B12"]
L30_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07"]


def _bands_for_collection(coll_id: str) -> list[str]:
    return S30_BANDS if coll_id.startswith("HLSS30") else L30_BANDS

# --- WMS service & layer attributes helpers ---

def get_wms_service_info() -> dict:
    try:
        r = requests.get(WMS_CAP_URL, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"wms": "http://www.opengis.net/wms", "xlink": "http://www.w3.org/1999/xlink"}
        info = {"version": "", "service": "", "formats": [], "url": ""}
        # Version
        if root.tag.endswith("WMS_Capabilities"):
            info["version"] = root.get("version", "")
        # Service name
        svc = root.find(".//wms:Service", ns)
        if svc is not None:
            name_el = svc.find("wms:Name", ns)
            if name_el is not None and name_el.text:
                info["service"] = name_el.text
        # Request formats
        fmts = root.findall(".//wms:Request//wms:Format", ns)
        info["formats"] = [f.text for f in fmts if f is not None and f.text]
        # OnlineResource URL
        olr = root.find(".//wms:Request//wms:OnlineResource", ns)
        if olr is not None:
            info["url"] = olr.get("{http://www.w3.org/1999/xlink}href", "")
        return info
    except Exception as e:
        print("[get_wms_service_info]", e)
        return {"version": "", "service": "", "formats": [], "url": ""}


def get_wms_layer_attrs(layer_id: str) -> dict:
    """Return dict of attributes for a given WMS layer from capabilities."""
    try:
        r = requests.get(WMS_CAP_URL, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"wms": "http://www.opengis.net/wms"}
        layer_node = None
        for lyr in root.findall(".//wms:Capability/wms:Layer//wms:Layer", ns):
            name_el = lyr.find("wms:Name", ns)
            if name_el is not None and (name_el.text or "").strip() == layer_id:
                layer_node = lyr
                break
        if layer_node is None:
            return {}
        crs = [e.text.strip() for e in layer_node.findall("wms:CRS", ns) if e is not None and e.text]
        ex = layer_node.find("wms:EX_GeographicBoundingBox", ns)
        bbox = None
        if ex is not None:
            bbox = {
                "lon_min": ex.findtext("wms:westBoundLongitude", default="", namespaces=ns),
                "lon_max": ex.findtext("wms:eastBoundLongitude", default="", namespaces=ns),
                "lat_min": ex.findtext("wms:southBoundLatitude", default="", namespaces=ns),
                "lat_max": ex.findtext("wms:northBoundLatitude", default="", namespaces=ns),
            }
        dim = layer_node.find("wms:Dimension", ns)
        time_extent = dim.text.strip() if (dim is not None and dim.text) else ""
        style_el = layer_node.find("wms:Style/wms:Name", ns)
        style = style_el.text.strip() if style_el is not None and style_el.text else ""
        return {"crs": crs, "bbox": bbox, "time_extent": time_extent, "style": style}
    except Exception as e:
        print("[get_wms_layer_attrs]", e)
        return {}

class State(rx.State):
    """Minimal app state to control map generation and visibility."""
    map_ready: bool = True
    selected_layer: str = AVAILABLE_LAYERS[0] if len(AVAILABLE_LAYERS) > 0 else ""
    map_src: str = "/folium_map.html"

    # Date (YYYY-MM-DD) used for time-enabled WMTS layers
    date_str: str = date.today().isoformat()

    # Bounding box fields for region jump (minx, miny, maxx, maxy)
    bbox_minx: str = ""
    bbox_miny: str = ""
    bbox_maxx: str = ""
    bbox_maxy: str = ""

    # Tile fetch inputs/outputs
    input_lat: str = ""
    input_lon: str = ""
    input_address: str = ""  # optional address lookup
    fetch_status: str = ""    # user-facing status/progress
    tile_path: str = ""       # assets path to the produced GeoTIFF
    preview_png: str = ""     # assets path to RGB preview

    # Crop Classification upload state
    crop_status: str = ""

    # Crop Classification upload + inference
    crop_file_path: str = ""
    crop_file_name: str = ""
    crop_api_status: str = ""
    crop_t1: str = ""
    crop_t2: str = ""
    crop_t3: str = ""
    crop_pred_img: str = ""

    # Layer details panel
    details_visible: bool = False
    svc_version: str = ""
    svc_name: str = ""
    svc_formats: list[str] = []
    svc_url: str = ""
    layer_crs: list[str] = []
    layer_bbox_lon_min: str = ""
    layer_bbox_lon_max: str = ""
    layer_bbox_lat_min: str = ""
    layer_bbox_lat_max: str = ""
    layer_time_extent: str = ""
    layer_style: str = ""

    def build_map(self):
        try:
            bbox = None
            minx = _safe_float(self.bbox_minx)
            miny = _safe_float(self.bbox_miny)
            maxx = _safe_float(self.bbox_maxx)
            maxy = _safe_float(self.bbox_maxy)
            if None not in (minx, miny, maxx, maxy):
                bbox = (minx, miny, maxx, maxy)

            _write_folium_map_to_assets(self.selected_layer, self.date_str, bbox)
            if self.selected_layer:
                self.map_src = f"/folium_map_{_slug(self.selected_layer)}_{self.date_str}.html?t={int(time())}"
        except Exception as e:
            print(f"[build_map] error: {e}")
        self.map_ready = True

    def set_selected_layer(self, value: str):
        self.selected_layer = value
        try:
            bbox = None
            minx = _safe_float(self.bbox_minx)
            miny = _safe_float(self.bbox_miny)
            maxx = _safe_float(self.bbox_maxx)
            maxy = _safe_float(self.bbox_maxy)
            if None not in (minx, miny, maxx, maxy):
                bbox = (minx, miny, maxx, maxy)

            _write_folium_map_to_assets(value, self.date_str, bbox)
            if value:
                self.map_src = f"/folium_map_{_slug(value)}_{self.date_str}.html?t={int(time())}"
        except Exception as e:
            print(f"[set_selected_layer] error: {e}")
        if self.details_visible:
            self.load_details()
    def toggle_details(self):
        self.details_visible = not self.details_visible

    def load_details(self):
        """(Re)load service + layer details for current selection and open the panel."""
        svc = get_wms_service_info()
        self.svc_version = svc.get("version", "") or ""
        self.svc_name = svc.get("service", "") or ""
        self.svc_formats = svc.get("formats", []) or []
        self.svc_url = svc.get("url", "") or ""
        attrs = get_wms_layer_attrs(self.selected_layer) if self.selected_layer else {}
        self.layer_crs = attrs.get("crs", []) or []
        bbox = attrs.get("bbox") or {}
        self.layer_bbox_lon_min = bbox.get("lon_min", "")
        self.layer_bbox_lon_max = bbox.get("lon_max", "")
        self.layer_bbox_lat_min = bbox.get("lat_min", "")
        self.layer_bbox_lat_max = bbox.get("lat_max", "")
        self.layer_time_extent = attrs.get("time_extent", "") or ""
        self.layer_style = attrs.get("style", "") or ""
        self.details_visible = True

    def set_date_str(self, value: str):
        # Expect value from <input type="date"> as YYYY-MM-DD
        self.date_str = value or date.today().isoformat()

    def set_bbox_minx(self, value: str):
        self.bbox_minx = value

    def set_bbox_miny(self, value: str):
        self.bbox_miny = value

    def set_bbox_maxx(self, value: str):
        self.bbox_maxx = value

    def set_bbox_maxy(self, value: str):
        self.bbox_maxy = value

    # Live filter for layer list and dropdown
    layer_filter: str = ""
    filtered_layers: list[str] = AVAILABLE_LAYERS
    filter_mode: str = "contains"  # one of: contains, prefix, regex
    regex_error: str = ""
    match_count: int = len(AVAILABLE_LAYERS)

    def set_layer_filter(self, value: str):
        self.layer_filter = value
        q = (value or "")
        q_lower = q.strip().lower()
        mode = (self.filter_mode or "contains").lower()
        self.regex_error = ""
        if not q_lower:
            self.filtered_layers = AVAILABLE_LAYERS
            self.match_count = len(self.filtered_layers)
            if self.selected_layer not in self.filtered_layers and self.filtered_layers:
                self.selected_layer = self.filtered_layers[0]
            return
        try:
            if mode == "prefix":
                self.filtered_layers = [lid for lid in AVAILABLE_LAYERS if lid.lower().startswith(q_lower)]
            elif mode == "regex":
                pattern = re.compile(q, flags=re.IGNORECASE)
                self.filtered_layers = [lid for lid in AVAILABLE_LAYERS if pattern.search(lid) is not None]
            else:  # contains
                self.filtered_layers = [lid for lid in AVAILABLE_LAYERS if q_lower in lid.lower()]
        except re.error as e:
            self.filtered_layers = []
            self.regex_error = f"Invalid regex: {e}"  # surfaced in UI
        self.match_count = len(self.filtered_layers)
        if self.selected_layer not in self.filtered_layers:
            if self.filtered_layers:
                self.selected_layer = self.filtered_layers[0]

    def set_filter_mode(self, value: str):
        self.filter_mode = value or "contains"
        # Re-run filtering with the same query
        self.set_layer_filter(self.layer_filter)

    def set_input_address(self, value: str):
        self.input_address = value

    def set_input_lat(self, value: str):
        self.input_lat = value

    def set_input_lon(self, value: str):
        self.input_lon = value

    def crop_on_drop(self, files=None):
        """Handle upload; persist first file into assets and keep its local path."""
        try:
            lst = files or []
            n = len(lst)
            print(f"[crop_on_drop] Received {n} files: {lst}")  # Debug log
            self.crop_status = f"Selected {n} file(s)."
            if n == 0:
                self.crop_file_path = ""
                self.crop_file_name = ""
                return

            f0 = lst[0] if lst and isinstance(lst[0], dict) else None
            print(f"[crop_on_drop] First file object: {f0}")  # Debug log
            assets_dir = os.path.join(os.getcwd(), "assets")
            os.makedirs(assets_dir, exist_ok=True)

            # Best-effort: prefer a provided local path; else try a url; else a name+bytes (not always provided by Reflex)
            local_path = None
            if f0 and f0.get("path"):
                # Already a temp file path on disk
                src_path = f0["path"]
                ext = os.path.splitext(src_path)[1] or ".bin"
                out_path = os.path.join(assets_dir, f"crop_upload{ext}")
                try:
                    with open(src_path, "rb") as r, open(out_path, "wb") as w:
                        w.write(r.read())
                    local_path = out_path
                except Exception:
                    local_path = src_path
            elif f0 and f0.get("url"):
                # Download from a provided URL
                url = f0["url"]
                ext = os.path.splitext(urlsplit(url).path)[1] or ".bin"
                out_path = os.path.join(assets_dir, f"crop_upload{ext}")
                try:
                    resp = requests.get(url, timeout=60)
                    resp.raise_for_status()
                    with open(out_path, "wb") as w:
                        w.write(resp.content)
                    local_path = out_path
                except Exception as e:
                    print("[crop_on_drop] download error", e)
            elif f0 and f0.get("name") and f0.get("data"):
                # Some environments pass inline bytes (rare). Try to persist.
                ext = os.path.splitext(f0["name"])[1] or ".bin"
                out_path = os.path.join(assets_dir, f"crop_upload{ext}")
                try:
                    with open(out_path, "wb") as w:
                        w.write(f0["data"])  # may already be bytes
                    local_path = out_path
                except Exception as e:
                    print("[crop_on_drop] write bytes error", e)

            if local_path and os.path.exists(local_path):
                # Validate file extension for TIF files
                ext = os.path.splitext(local_path)[1].lower()
                if ext in ['.tif', '.tiff']:
                    print(f"[crop_on_drop] Successfully saved TIF file: {local_path}")
                elif ext in ['.png', '.jpg', '.jpeg']:
                    print(f"[crop_on_drop] Successfully saved image file: {local_path}")
                else:
                    print(f"[crop_on_drop] Unsupported file type: {ext}")
                
                self.crop_file_path = local_path
                self.crop_file_name = os.path.basename(local_path)
                self.crop_status = f"Ready: {os.path.basename(local_path)} ({ext})"
            else:
                self.crop_file_path = ""
                self.crop_file_name = ""
                self.crop_status = "Could not persist uploaded file; please try again."
                print(f"[crop_on_drop] Failed to save file. local_path: {local_path}")
        except Exception as e:
            print("[crop_on_drop]", e)
            self.crop_status = "Upload failed."
            self.crop_file_path = ""
            self.crop_file_name = ""

    def crop_send(self):
        """Send the uploaded image to the HF Space and display T1/T2/T3 and prediction images."""
        if not self.crop_file_path:
            self.crop_status = "Please select an image first."
            return
        if not os.path.exists(self.crop_file_path):
            self.crop_status = f"File not found: {self.crop_file_path}"
            return
        if Client is None:
            self.crop_status = "gradio_client not installed. Run: pip install gradio_client"
            return

        print(f"[crop_send] Sending file: {self.crop_file_path}")  # Debug log
        self.crop_api_status = "Calling model…"
        self.crop_status = ""
        # Optional Hugging Face token for private Spaces
        hf_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN") or os.environ.get("HF_TOKEN") or None
        try:
            client = Client("ibm-nasa-geospatial/Prithvi-100M-multi-temporal-crop-classification-demo", hf_token=hf_token)
            print(f"[crop_send] Client created, calling predict with file: {self.crop_file_path}")
            res = client.predict(target_image=handle_file(self.crop_file_path), api_name="/partial")
            print(f"[crop_send] API response: {res}")  # Debug log
            # Expect a tuple/list of 4 filepaths (T1, T2, T3, prediction)
            if not isinstance(res, (list, tuple)) or len(res) < 4:
                self.crop_api_status = f"Unexpected response from model: {type(res)} with {len(res) if hasattr(res, '__len__') else 'unknown'} items"
                return
        except Exception as e:
            print(f"[crop_send] API call failed: {e}")  # Debug log
            self.crop_api_status = f"Model call failed: {e}"
            return

        def _fetch_to_assets(src_path: str, out_name: str) -> str:
            assets_dir = os.path.join(os.getcwd(), "assets")
            os.makedirs(assets_dir, exist_ok=True)
            out_path = os.path.join(assets_dir, out_name)
            try:
                if src_path.startswith("http://") or src_path.startswith("https://"):
                    r = requests.get(src_path, timeout=60)
                    r.raise_for_status()
                    with open(out_path, "wb") as f:
                        f.write(r.content)
                else:
                    with open(src_path, "rb") as r, open(out_path, "wb") as w:
                        w.write(r.read())
                return "/" + os.path.basename(out_path)
            except Exception as e:
                print("[crop_send fetch]", e)
                return ""

        t1_fp = _fetch_to_assets(str(res[0]), "crop_t1.png")
        t2_fp = _fetch_to_assets(str(res[1]), "crop_t2.png")
        t3_fp = _fetch_to_assets(str(res[2]), "crop_t3.png")
        pred_fp = _fetch_to_assets(str(res[3]), "crop_pred.png")

        self.crop_t1 = t1_fp
        self.crop_t2 = t2_fp
        self.crop_t3 = t3_fp
        self.crop_pred_img = pred_fp
        if pred_fp:
            self.crop_api_status = "Prediction ready."
        else:
            self.crop_api_status = "Prediction returned but images could not be fetched."

    def fetch_tile(self):
        """Fetch an ~1 km HLS 18-band GeoTIFF for 3 timesteps and generate a PNG preview."""
        self.fetch_status = "Starting tile fetch…"
        lat = _safe_float(self.input_lat)
        lon = _safe_float(self.input_lon)
        if (lat is None or lon is None) and (self.input_address or "").strip():
            self.fetch_status = "Geocoding address…"
            res = _geocode_address(self.input_address.strip())
            if res is not None:
                lat, lon = res
                self.input_lat = f"{lat:.6f}"
                self.input_lon = f"{lon:.6f}"
        if lat is None or lon is None:
            self.fetch_status = "Provide lat/lon or a valid address."
            return

        # Find up to ~10 nearby acquisitions and pick 3 closest to requested date
        items = _search_hls_items(lat, lon, self.date_str, limit=20)
        if not items:
            self.fetch_status = "No HLS items found near that point/date. Try adjusting date."
            return
        # Choose top 3 by absolute time delta to requested date
        # Make both sides timezone-aware (UTC) to prevent naive/aware subtraction errors
        target = datetime.fromisoformat(self.date_str)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)

        def _dt_of(feat):
            try:
                dt_str = (feat.get("properties", {}).get("datetime", "") or "").replace("Z", "+00:00")
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return datetime.max.replace(tzinfo=timezone.utc)

        items.sort(key=lambda f: abs((_dt_of(f) - target)))
        items = items[:3]

        if rasterio is None or np is None:
            self.fetch_status = "Raster backend missing. Please `pip install rasterio numpy` in your venv."
            return

        # Build 1 km bbox around point in WGS84
        dlat, dlon = _deg_buffer(lat, 500.0)
        south, north = lat - dlat, lat + dlat
        west, east = lon - dlon, lon + dlon

        arrays = []
        meta_template = None

        token = os.environ.get("EARTHDATA_TOKEN", "").strip()
        # Build both GDAL and requests headers
        req_headers = {"User-Agent": "bloomwatch/1.0"}
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        gdal_env = {}
        if token:
            # Multiple headers supported separated by CRLF
            gdal_env["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {token}\r\nUser-Agent: bloomwatch/1.0"
        else:
            self.fetch_status = "No EARTHDATA_TOKEN in environment — HLS protected assets will 401."
        # Additional robustness for HTTP range/HEAD quirks
        gdal_env.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")
        gdal_env.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
        gdal_env.setdefault("GDAL_HTTP_MULTIRANGE", "YES")

        for it in items:
            coll = it.get("collection", "")
            bands = _bands_for_collection(coll)
            assets = it.get("assets", {})
            # Normalize hrefs: prefer HTTPS if alternate link exists
            # Some STAC catalogs include both `href` and `alternate` links; we try to pick a https URL
            def _pick_href(asset: dict):
                if not asset:
                    return None
                url = asset.get("href")
                if url and url.startswith("https://"):
                    return url
                # Check alternates
                for alt in asset.get("alternates", []) or []:
                    href = alt.get("href")
                    if href and href.startswith("https://"):
                        return href
                return url
            # For each required band, get the COG href
            hrefs = []
            for b in bands:
                a = assets.get(b)
                if not a:
                    self.fetch_status = f"Band {b} missing in item; skipping."
                    hrefs = []
                    break
                hrefs.append(_pick_href(a))
            if not hrefs:
                continue

            # Read/crop each band and append to arrays
            for href in hrefs:
                # Preflight auth check – try a small ranged GET (first 16KB)
                try:
                    probe = requests.get(href, headers={**req_headers, "Range": "bytes=0-16383"}, timeout=30, stream=True)
                    if probe.status_code in (401, 403):
                        self.fetch_status = (
                            "Unauthorized (401/403) reading HLS asset. "
                            "Ensure EARTHDATA_TOKEN is set and valid in the same shell before running `reflex run`."
                        )
                        return
                except Exception as pe:
                    print("[preflight]", pe)
                # Do not append tokens to the URL; rely on Authorization header for cloud-protected assets
                with rasterio.Env(**gdal_env):
                    with rasterio.open(href) as src:
                        # Reproject to WGS84 if needed using WarpedVRT
                        if str(src.crs).upper() != "EPSG:4326":
                            from rasterio.vrt import WarpedVRT
                            vrt = WarpedVRT(src, crs="EPSG:4326", resampling=rasterio.enums.Resampling.bilinear)
                            win = from_bounds(west, south, east, north, transform=vrt.transform)
                            data = vrt.read(1, window=win, out_shape=(int(win.height), int(win.width)))
                            trans = rasterio.windows.transform(win, vrt.transform)
                            height, width = data.shape
                        else:
                            win = from_bounds(west, south, east, north, transform=src.transform)
                            data = src.read(1, window=win, out_shape=(int(win.height), int(win.width)))
                            trans = rasterio.windows.transform(win, src.transform)
                            height, width = data.shape
                arrays.append(data)
                if meta_template is None:
                    meta_template = {
                        "driver": "GTiff",
                        "dtype": str(data.dtype),
                        "count": 18,  # 3 timesteps * 6 bands
                        "height": height,
                        "width": width,
                        "crs": "EPSG:4326",
                        "transform": trans,
                        "compress": "deflate",
                        "predictor": 2,
                    }
        if len(arrays) != 18:
            self.fetch_status = (
                f"Expected 18 band slices, got {len(arrays)}.\n"
                "If you set EARTHDATA_TOKEN, ensure it's valid and restart the app.\n"
                "We now send the token via HTTP Authorization header for ranged reads."
            )
            return

        assets_dir = os.path.join(os.getcwd(), "assets")
        os.makedirs(assets_dir, exist_ok=True)
        out_tif = os.path.join(assets_dir, f"hls_tile_{lat:.5f}_{lon:.5f}_{self.date_str}.tif")
        out_png = os.path.join(assets_dir, f"hls_tile_{lat:.5f}_{lon:.5f}_{self.date_str}.png")

        with rasterio.open(out_tif, "w", **meta_template) as dst:
            for i, arr in enumerate(arrays, start=1):
                dst.write(arr, i)

        # Build preview (use latest timestep RGB = Red,Green,Blue). Arrays order per timestep: [B02,B03,B04,...]
        try:
            arr = np.stack(arrays[-6:-3][::-1], axis=0)  # B04,B03,B02 -> approximate RGB
            # Simple stretch
            def _stretch(x):
                lo, hi = np.percentile(x, (2, 98))
                x = np.clip((x - lo) / max(1e-6, (hi - lo)), 0, 1)
                return (x * 255).astype("uint8")
            rgb = np.stack([_stretch(arr[0]), _stretch(arr[1]), _stretch(arr[2])], axis=-1)
            from PIL import Image
            Image.fromarray(rgb).save(out_png)
            self.preview_png = "/" + os.path.basename(out_png)
        except Exception as e:
            print("[preview]", e)
            self.preview_png = ""

        self.tile_path = "/" + os.path.basename(out_tif)
        self.fetch_status = "Tile ready."

# --- Folium map writer ---
def _write_folium_map_to_assets(selected_layer: str | None = None, date_str: str | None = None, bbox: tuple[float, float, float, float] | None = None):
    """Create a Folium map HTML file under the Reflex static assets directory.

    If `selected_layer` is provided, that layer will be shown by default and the
    file will be written as `/assets/folium_map_{slug}_{date}.html`. Otherwise it writes
    the default `/assets/folium_map.html` once.
    """
    # Fallbacks
    time_str = (date_str or date.today().isoformat())

    # Center map globally; we'll optionally fit to bbox below
    m = folium.Map(location=[20, 0], zoom_start=2, tiles=None)
    map_var = m.get_name()

    folium.map.CustomPane("controls").add_to(m)
    folium.Marker(
        [85, 0],
        icon=folium.DivIcon(
            html='<div style="background:rgba(0,0,0,0.6);color:#fff;padding:6px 10px;border-radius:8px;font-size:12px;">Draw a rectangle to download GeoTIFF</div>'
        ),
        pane="controls",
    ).add_to(m)

    # Add a base map so the view isn’t blank if an overlay fails
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True, show=True).add_to(m)
    # Show coordinates under cursor and a simple click popup (marker handled by custom JS below)
    MousePosition(position='topright', separator=' , ', num_digits=6, prefix='Lat, Lon:').add_to(m)

    # Add available GIBS layers as WMS TileLayers; show only the selected one
    if len(AVAILABLE_LAYERS) == 0:
        # Fallback single layer (True Color) as WMS
        folium.raster_layers.WmsTileLayer(
            url=WMS_BASE_URL,
            name="MODIS_Terra_CorrectedReflectance_TrueColor",
            layers="MODIS_Terra_CorrectedReflectance_TrueColor",
            fmt="image/png",
            transparent=True,
            version="1.3.0",
            styles="",
            attr="NASA GIBS",
            time=_choose_time("MODIS_Terra_CorrectedReflectance_TrueColor", time_str),
            overlay=True,
            show=True,
            control=True,
        ).add_to(m)
    else:
        for lid in AVAILABLE_LAYERS:
            folium.raster_layers.WmsTileLayer(
                url=WMS_BASE_URL,
                name=lid,
                layers=lid,
                fmt="image/png",
                transparent=True,
                version="1.3.0",
                styles="",
                attr="NASA GIBS",
                time=_choose_time(lid, time_str),
                overlay=True,
                show=(selected_layer == lid) if selected_layer else (lid == AVAILABLE_LAYERS[0]),
                control=True,
            ).add_to(m)

    # Add a rectangle draw control to select AOI
    Draw(
        export=False,
        draw_options={"polyline": False, "polygon": False, "circle": False, "circlemarker": False, "marker": False},
        edit_options={"edit": False, "remove": False},
    ).add_to(m)

    # Inject client-side JS to call NASA Worldview Snapshots API and handle clicks
    snap_layer = selected_layer if selected_layer else (AVAILABLE_LAYERS[0] if AVAILABLE_LAYERS else "MODIS_Terra_CorrectedReflectance_TrueColor")
    _time_val = _choose_time(snap_layer, time_str)
    _layer_val = snap_layer
    map_name = map_var  # e.g., "map_123abc"
    js = """
    (function(mapName){
      function openSnapshotFor(bounds) {
        var south = bounds.getSouth();
        var west  = bounds.getWest();
        var north = bounds.getNorth();
        var east  = bounds.getEast();
        var params = new URLSearchParams({
          REQUEST: 'GetSnapshot',
          TIME: '%(time)s',
          LAYERS: '%(layer)s',
          CRS: 'EPSG:4326',
          BBOX: south + ',' + west + ',' + north + ',' + east,
          FORMAT: 'image/geotiff',
          WIDTH: '2048',
          HEIGHT: '2048'
        });
        var url = 'https://wvs.earthdata.nasa.gov/api/v1/snapshot?' + params.toString();
        window.open(url, '_blank');
      }

      function _setParentInput(id, val) {
        try {
          var el = window.parent && window.parent.document ? window.parent.document.getElementById(id) : null;
          if (!el) return;
          el.value = String(val);
          var ev = new Event('input', { bubbles: true });
          el.dispatchEvent(ev);
        } catch (e) {}
      }

      function ready(fn){
        if (document.readyState !== 'loading'){ fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
      }

      function bindWhenMapReady(){
        var tries = 0;
        (function wait(){
          var map = window[mapName];
          if (map && map.on){
            console.log('[GIBS] Map found, binding handlers on', mapName);
            var clickGroup = L.layerGroup().addTo(map);

            // Rectangle draw -> GeoTIFF download
            if (window.L && L.Draw && L.Draw.Event && L.Draw.Event.CREATED){
              map.on(L.Draw.Event.CREATED, function (e) {
                var layer = e.layer;
                map.addLayer(layer);
                if (layer.getBounds) {
                  openSnapshotFor(layer.getBounds());
                }
              });
            }

            // Plain click -> show marker(s) + autofill bbox with point coords
            map.on('click', function (e) {
              console.log('[GIBS] Click at', e.latlng);
              var lat = Number(e.latlng.lat.toFixed(6));
              var lon = Number(e.latlng.lng.toFixed(6));
              try {
                clickGroup.clearLayers();
                var pin = L.marker([lat, lon], {zIndexOffset: 1000}).bindPopup('Lat: ' + lat + '<br>Lon: ' + lon);
                var dot = L.circleMarker([lat, lon], {radius: 6, weight: 2});
                clickGroup.addLayer(dot);
                clickGroup.addLayer(pin);
                pin.addTo(clickGroup).openPopup();
                if (clickGroup.bringToFront) { clickGroup.bringToFront(); }
              } catch (err) { console.warn('[GIBS] Marker error:', err); }
              _setParentInput('bbox_minx', lon);
              _setParentInput('bbox_miny', lat);
              _setParentInput('bbox_maxx', lon);
              _setParentInput('bbox_maxy', lat);
            });
            return; // done
          }
          if (tries++ < 200){ setTimeout(wait, 50); } // wait up to ~10s
          else { console.warn('[GIBS] Map variable not found:', mapName); }
        })();
      }

      ready(bindWhenMapReady);
    })('%(map_name)s');
    """ % {"time": _time_val, "layer": _layer_val, "map_name": map_name}
    folium.Element("<script>\n" + js + "\n</script>").add_to(m)

    # Optional region jump via bounding box
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        try:
            m.fit_bounds([[miny, minx], [maxy, maxx]])
        except Exception:
            pass

    # Add (or deliberately hide) the Leaflet layer control.
    if SHOW_LEAFLET_LAYER_CONTROL:
        folium.LayerControl(collapsed=False).add_to(m)
    else:
        # Keep the control out of sight to avoid duplicate UI (we keep our own dropdown in Reflex).
        # We can either not add it at all (preferred) and also hard-hide in case Folium injects it via plugins.
        # No control added; also inject CSS guard to hide any layer control if a plugin adds one.
        folium.Element("<style>.leaflet-control-layers{display:none !important;}</style>").add_to(m)

    assets_dir = os.path.join(os.getcwd(), "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # Render once to a string to compare with any existing file
    html_str = m.get_root().render()

    if selected_layer:
        out_path = os.path.join(assets_dir, f"folium_map_{_slug(selected_layer)}_{time_str}.html")
        try:
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8") as f:
                    existing = f.read()
                if existing == html_str:
                    return  # no change; avoid touching mtime to prevent rebuild loop
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_str)
        except Exception:
            # Fallback to folium save if direct write fails
            m.save(out_path)
    else:
        out_path = os.path.join(assets_dir, "folium_map.html")
        try:
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8") as f:
                    existing = f.read()
                if existing == html_str:
                    return
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_str)
        except Exception:
            m.save(out_path)
        

# Generate the map once at import time so it's available as a static file
try:
    # Avoid infinite dev-rebuild loops: only generate at import-time if the file doesn't exist
    # or when explicitly running in production (REFLEX_ENV=production).
    first_layer = AVAILABLE_LAYERS[0] if len(AVAILABLE_LAYERS) > 0 else None
    is_prod = os.environ.get("REFLEX_ENV", "development").lower() == "production"
    if first_layer:
        out_path = os.path.join(os.getcwd(), "assets", f"folium_map_{_slug(first_layer)}_{date.today().isoformat()}.html")
        if is_prod or not os.path.exists(out_path):
            _write_folium_map_to_assets(first_layer, date.today().isoformat(), None)
    else:
        out_path = os.path.join(os.getcwd(), "assets", "folium_map.html")
        if is_prod or not os.path.exists(out_path):
            _write_folium_map_to_assets(None, date.today().isoformat(), None)
except Exception as _e:
    print(f"[folium] map generation skipped: {_e}")


def _thumb_card(title: str, img_src_var):
    """A labeled thumbnail card with a top-left badge and centered preview."""
    return rx.box(
        # Floating title badge (top-left)
        rx.badge(
            rx.hstack(rx.text(title)),
            variant="surface",
            high_contrast=False,
            size="1",
            style={"position": "absolute", "top": "8px", "left": "8px"},
        ),
        # Centered image or placeholder
        rx.center(
            rx.cond(
                img_src_var != "",
                rx.image(src=img_src_var, width="100%", height="100%", style={"objectFit": "contain"}),
                rx.text("", color="gray", font_size="44px"),
            ),
            width="100%",
            height="100%",
        ),
        position="relative",
        border="1px solid",
        border_radius="12px",
        padding="10px",
        min_height="200px",
        background_color=rx.cond(rx.color_mode == "light", "#f8f8f8", "#1f242b"),
    )

def index() -> rx.Component:
    return rx.container(
        rx.color_mode.button(position="top-right", border_radius="12px"),
        rx.text("Innovators Crew", position="top-left", size="1", color_scheme="orange"),
        rx.center(
            rx.vstack(
                rx.hstack(
                    rx.image(src="/cropwatch_icon.png", alt="Sample Image", width="40px", height="auto"),
                    rx.heading("Cropwatch", size="8", weight="regular"),
                ),
                rx.text("GIBS Tile Fetcher and Map Viewer", size="4", weight="light"),
                spacing="4",
                align="center"
            )
        ),
        rx.spacer(height="20px"),
        rx.cond(
            State.map_ready,
            rx.box(
                rx.el.iframe(
                    src=State.map_src,
                    width="100%",
                    height="500px",
                    style={"border": "none", "borderRadius": "12px"},
                ),
                border="3px solid",
                border_radius="16px",
                overflow="hidden",
                transition="border-color 0.2s ease-in-out",
                border_color=rx.cond(rx.color_mode == "light", "black", "white"),
            ),
            rx.text("Click \u201cBuild map\u201d to generate.")
        ),
        rx.spacer(height="20px"),
        rx.center(
            rx.vstack(
                rx.center(
                    rx.heading("Layer Selector", size="4", weight="bold", color_scheme="orange"),
                ),
                rx.spacer(height="12px"),
                rx.hstack(
                    rx.text("Dataset:", size="2"),
                    rx.input(
                        placeholder="Search layers...",
                        value=State.layer_filter,
                        on_change=State.set_layer_filter,
                        width="260px",
                    ),
                    rx.select(
                        items=["contains", "prefix", "regex"],
                        value=State.filter_mode,
                        on_change=State.set_filter_mode,
                        width="140px",
                    ),
                    rx.badge(
                        rx.hstack(
                            rx.text(State.match_count),
                            rx.text(" matches"),
                            spacing="1",
                            align="center",
                        ),
                        color_scheme="orange",
                        high_contrast=False,
                    ),
                    spacing="3",
                    align="center",
                ),
                rx.cond(
                    State.regex_error != "",
                    rx.text(State.regex_error, color="red", size="1"),
                    rx.box()
                ),
                rx.hstack(
                    rx.text("Select layer:", size="2"),
                    rx.select(
                        items=State.filtered_layers,
                        value=State.selected_layer,
                        on_change=State.set_selected_layer,
                        width="640px",
                    ),
                    align="center",
                    spacing="2",
                ),
                rx.spacer(height="8px"),
                rx.cond(
                    State.details_visible,
                    rx.box(
                        rx.separator(),
                        rx.spacer(height="8px"),
                        rx.heading("Service", size="2"),
                        rx.hstack(rx.text("Version:"), rx.code(State.svc_version), spacing="2"),
                        rx.hstack(rx.text("Name:"), rx.code(State.svc_name), spacing="2"),
                        rx.hstack(rx.text("URL:"), rx.code(State.svc_url), spacing="2"),
                        rx.spacer(height="6px"),
                        rx.heading("Request Formats", size="2"),
                        rx.vstack(
                            rx.foreach(State.svc_formats, lambda fmt: rx.code(fmt)),
                            spacing="1",
                            align="start",
                        ),
                        rx.spacer(height="6px"),
                        rx.heading("Layer Attributes", size="2"),
                        rx.hstack(rx.text("Style:"), rx.code(State.layer_style), spacing="2"),
                        rx.hstack(rx.text("Time Extent:"), rx.code(State.layer_time_extent), spacing="2"),
                        rx.text("CRS:"),
                        rx.vstack(
                            rx.foreach(State.layer_crs, lambda crs: rx.code(crs)),
                            spacing="1",
                            align="start",
                        ),
                        rx.text("Geographic BBOX (lon/lat):"),
                        rx.hstack(
                            rx.text("Lon min/max:"),
                            rx.code(State.layer_bbox_lon_min),
                            rx.text(" / "),
                            rx.code(State.layer_bbox_lon_max),
                            spacing="1",
                        ),
                        rx.hstack(
                            rx.text("Lat min/max:"),
                            rx.code(State.layer_bbox_lat_min),
                            rx.text(" / "),
                            rx.code(State.layer_bbox_lat_max),
                            spacing="1",
                        ),
                        padding_top="8px",
                    ),
                    rx.box()
                ),
            ),
            border="3px solid",
            border_radius="12px",
            padding="20px",
        ),
        rx.spacer(height="20px"),

        # --- HLS Tile Fetch UI ---
        rx.center(
            rx.vstack(
                rx.center(
                    rx.heading("Tile Fetcher", size="4", weight="bold", color_scheme="orange"),
                ),
                rx.spacer(height="12px"),
                rx.hstack(
                    rx.text("Date:", size="2"),
                    rx.el.input(type="date", value=State.date_str, on_change=State.set_date_str),
                    spacing="3",
                    align="center",
                ),
                rx.spacer(height="12px"),
                rx.text("Tile center (choose one):", size="2"),
                rx.hstack(
                    rx.input(placeholder="Address (e.g., Paris, France)", value=State.input_address, on_change=State.set_input_address, width="360px"),
                    rx.text("or", size="1"),
                    rx.input(placeholder="lat", value=State.input_lat, on_change=State.set_input_lat, width="140px"),
                    rx.input(placeholder="lon", value=State.input_lon, on_change=State.set_input_lon, width="140px"),
                    spacing="3",
                    align="center",
                ),
                rx.spacer(height="8px"),
                rx.hstack(
                    rx.button("Fetch Tile (HLS 18‑band, 1 km)", on_click=State.fetch_tile, color_scheme="green"),
                    rx.text(State.fetch_status, size="1"),
                    spacing="3",
                    align="center",
                ),
                rx.cond(
                    State.tile_path != "",
                    rx.hstack(
                        rx.cond(
                            State.preview_png != "",
                            rx.image(src=State.preview_png, width="320px"),
                            rx.box()
                        ),
                        rx.el.a(
                            rx.button("Download HLS GeoTIFF", color_scheme="blue"),
                            href=State.tile_path,
                            target="_blank",
                            rel="noopener noreferrer",
                        ),
                        spacing="3",
                        align="center",
                    ),
                    rx.box()
                ),
            ),
            border="3px solid",
            border_radius="12px",
            padding="20px",
        ),

        rx.spacer(height="20px"),
        rx.center(
            rx.vstack(
                rx.center(
                    rx.heading("Crop Classification", size="4", weight="bold", color_scheme="orange"),
                ),
                rx.spacer(height="12px"),
                rx.text("Upload image:", size="2"),
        rx.hstack(
            rx.upload(
                # Positional children FIRST
                rx.text("📤", font_size="22px"),
                rx.text("Click or drop image", size="1", color="gray"),
                # Keyword props AFTER children
                id="crop_upload",
                multiple=False,
                accept=[
                    ".png", ".jpg", ".jpeg",
                    ".tif", ".tiff",
                    "image/tiff", "image/geotiff", "application/geotiff",
                    "application/tiff", "application/x-geotiff",
                ],
                title="Click to select or drop a .tif/.tiff GeoTIFF (also accepts .png/.jpg)",
                max_files=1,
                on_drop=State.crop_on_drop,
                # Make the dropzone visually obvious & clickable
                style={
                    "border": "2px dashed",
                    "borderRadius": "12px",
                    "padding": "16px 20px",
                    "minWidth": "220px",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "cursor": "pointer",
                    "gap": "8px",
                },
            ),
            rx.cond(
                State.crop_file_path != "",
                rx.hstack(
                    rx.text("File:", size="1", color="gray"),
                    rx.code(State.crop_file_name),
                    spacing="1",
                    align="center",
                ),
                rx.box()
            ),
            rx.button("Send to API", on_click=State.crop_send, color_scheme="purple"),
            spacing="3",
            align="center",
        ),
                rx.cond(
                    State.crop_status != "",
                    rx.text(State.crop_status, size="1"),
                    rx.box()
                ),
                rx.spacer(height="8px"),
                rx.text(State.crop_api_status, size="1"),
                rx.spacer(height="8px"),
                rx.grid(
                    _thumb_card("T1", State.crop_t1),
                    _thumb_card("T2", State.crop_t2),
                    _thumb_card("T3", State.crop_t3),
                    _thumb_card("Model prediction", State.crop_pred_img),
                    columns="4",
                    gap="3",
                    width="100%",
                    # Collapse to 2 columns on narrower screens
                    style={"gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))"},
                ),
            ),
            border="3px solid",
            border_radius="12px",
            padding="20px",
        ),
    )

style = {
    rx.text:{
        "font_family": "Figtree",
    },
    rx.heading:{
        "font_family": "Figtree",
    }
}

app = rx.App(style=style)
app.add_page(index)