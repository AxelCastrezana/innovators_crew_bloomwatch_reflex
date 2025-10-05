# services/map_service.py
import os, hashlib

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def ensure_folium_map_written(out_path: str = "assets/folium_map.html") -> str:
    import folium  # lazy import
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Build the map HTML as a string first
    m = folium.Map(location=[41, -70], zoom_start=4, tiles="OpenStreetMap")
    # ... add layers ...
    html = m.get_root().render()
    h = _hash(html)

    # Only write if new/changed
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            if _hash(f.read()) == h:
                return out_path
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path