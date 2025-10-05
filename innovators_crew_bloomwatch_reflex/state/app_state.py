"""
BloomWatch Application State Module

This module contains the main Reflex State class for the BloomWatch application,
managing map generation, layer selection, crop classification, and satellite tile fetching.
"""

import os
import re
from datetime import date, datetime, timezone
from time import time
from urllib.parse import urlsplit

import reflex as rx
import requests

# Import utility functions
from ..utils.helpers import safe_float, slug
from ..utils.file_utils import validate_file_size, get_file_extension

# Import services
from ..services.maps import MapService

# Import API clients
from ..api.gibs import GIBSClient
from ..api.huggingface import HuggingFaceClient  
from ..api.hls import HLSClient

# Optional dependencies
try:
    from gradio_client import Client, handle_file
except ImportError:
    Client = None
    handle_file = None

try:
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.warp import transform_bounds
    import numpy as np
    from PIL import Image
except ImportError:
    rasterio = None
    np = None
    Image = None

# Initialize service clients
map_service = MapService()
gibs_client = GIBSClient()
hf_client = HuggingFaceClient()
hls_client = HLSClient()

# Initialize available layers from GIBS
AVAILABLE_LAYERS = gibs_client.list_wms_layers()
print(f"GIBS WMS: found {len(AVAILABLE_LAYERS)} layers")

if AVAILABLE_LAYERS:
    print("First 5 layers:")
    for one in sorted(AVAILABLE_LAYERS)[:5]:
        print("  " + one)
    print("Last 5 layers:")
    for one in sorted(AVAILABLE_LAYERS)[-5:]:
        print("  " + one)
else:
    print("No layers found - check WMS capabilities URL")


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

    # Live filter for layer list and dropdown
    layer_filter: str = ""
    filtered_layers: list[str] = AVAILABLE_LAYERS
    filter_mode: str = "contains"  # one of: contains, prefix, regex
    regex_error: str = ""
    match_count: int = len(AVAILABLE_LAYERS)

    def build_map(self):
        """Build and generate the Folium map with current settings."""
        try:
            bbox = None
            minx = safe_float(self.bbox_minx)
            miny = safe_float(self.bbox_miny)
            maxx = safe_float(self.bbox_maxx)
            maxy = safe_float(self.bbox_maxy)
            if None not in (minx, miny, maxx, maxy):
                bbox = (minx, miny, maxx, maxy)

            map_service.write_folium_map_to_assets(self.selected_layer, self.date_str, bbox)
            if self.selected_layer:
                self.map_src = f"/folium_map_{slug(self.selected_layer)}_{self.date_str}.html?t={int(time())}"
        except Exception as e:
            print(f"[build_map] error: {e}")
        self.map_ready = True

    def set_selected_layer(self, value: str):
        """Set the selected WMS layer and regenerate the map."""
        self.selected_layer = value
        try:
            bbox = None
            minx = safe_float(self.bbox_minx)
            miny = safe_float(self.bbox_miny)
            maxx = safe_float(self.bbox_maxx)
            maxy = safe_float(self.bbox_maxy)
            if None not in (minx, miny, maxx, maxy):
                bbox = (minx, miny, maxx, maxy)

            map_service.write_folium_map_to_assets(value, self.date_str, bbox)
            if value:
                self.map_src = f"/folium_map_{slug(value)}_{self.date_str}.html?t={int(time())}"
        except Exception as e:
            print(f"[set_selected_layer] error: {e}")
        if self.details_visible:
            self.load_details()

    def toggle_details(self):
        """Toggle the layer details panel visibility."""
        self.details_visible = not self.details_visible

    def load_details(self):
        """(Re)load service + layer details for current selection and open the panel."""
        svc = gibs_client.get_service_info()
        self.svc_version = svc.get("version", "") or ""
        self.svc_name = svc.get("service", "") or ""
        self.svc_formats = svc.get("formats", []) or []
        self.svc_url = svc.get("url", "") or ""
        
        attrs = gibs_client.get_layer_attrs(self.selected_layer) if self.selected_layer else {}
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
        """Set the date string for time-enabled layers."""
        # Expect value from <input type="date"> as YYYY-MM-DD
        self.date_str = value or date.today().isoformat()

    def set_bbox_minx(self, value: str):
        """Set the minimum X coordinate of the bounding box."""
        self.bbox_minx = value

    def set_bbox_miny(self, value: str):
        """Set the minimum Y coordinate of the bounding box."""
        self.bbox_miny = value

    def set_bbox_maxx(self, value: str):
        """Set the maximum X coordinate of the bounding box."""
        self.bbox_maxx = value

    def set_bbox_maxy(self, value: str):
        """Set the maximum Y coordinate of the bounding box."""
        self.bbox_maxy = value

    def set_layer_filter(self, value: str):
        """Filter available layers based on search criteria."""
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
        """Set the layer filter mode (contains, prefix, regex)."""
        self.filter_mode = value or "contains"
        # Re-run filtering with the same query
        self.set_layer_filter(self.layer_filter)

    def set_input_address(self, value: str):
        """Set the input address for geocoding."""
        self.input_address = value

    def set_input_lat(self, value: str):
        """Set the input latitude."""
        self.input_lat = value

    def set_input_lon(self, value: str):
        """Set the input longitude."""
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
        
        try:
            result = hf_client.classify_crop_image(self.crop_file_path)
            print(f"[crop_send] API response: {result}")  # Debug log
            
            if not result or "error" in result:
                self.crop_api_status = result.get("error", "Model call failed") if result else "Model call failed"
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

        # Fetch the result images
        res = result.get("images", [])
        if len(res) >= 4:
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
        else:
            self.crop_api_status = "Unexpected response format from model"

    def fetch_tile(self):
        """Fetch an ~1 km HLS 18-band GeoTIFF for 3 timesteps and generate a PNG preview."""
        self.fetch_status = "Starting tile fetch…"
        lat = safe_float(self.input_lat)
        lon = safe_float(self.input_lon)
        
        if (lat is None or lon is None) and (self.input_address or "").strip():
            self.fetch_status = "Geocoding address…"
            res = hls_client.geocode_address(self.input_address.strip())
            if res is not None:
                lat, lon = res
                self.input_lat = f"{lat:.6f}"
                self.input_lon = f"{lon:.6f}"
                
        if lat is None or lon is None:
            self.fetch_status = "Provide lat/lon or a valid address."
            return

        try:
            result = hls_client.fetch_hls_tile(lat, lon, self.date_str)
            
            if not result or "error" in result:
                self.fetch_status = result.get("error", "Failed to fetch HLS tile") if result else "Failed to fetch HLS tile"
                return
                
            # Update state with successful result
            self.tile_path = result.get("tile_path", "")
            self.preview_png = result.get("preview_png", "")
            self.fetch_status = "Tile ready."
            
        except Exception as e:
            print(f"[fetch_tile] error: {e}")
            self.fetch_status = f"Error fetching tile: {e}"