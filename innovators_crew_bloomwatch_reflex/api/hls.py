"""
NASA HLS (Harmonized Landsat Sentinel) API Client
Handles communication with NASA CMR STAC API for satellite data

⚡ Code generated with AI assistance (GitHub Copilot) for modular refactoring
"""
import math
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple


class HLSClient:
    """Client for NASA HLS data via CMR STAC API"""
    
    def __init__(self):
        self.cmr_stac_root = "https://cmr.earthdata.nasa.gov/stac/LPCLOUD"
        self.geocode_url = "https://nominatim.openstreetmap.org/search"
        
    def geocode_address(self, query: str) -> Optional[Tuple[float, float]]:
        """Convert address to lat/lon coordinates"""
        try:
            params = {
                "q": query,
                "format": "json",
                "addressdetails": "1",
                "limit": "1",
            }
            headers = {"User-Agent": "CropWatch/1.0"}
            
            r = requests.get(self.geocode_url, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            
            if data and len(data) > 0:
                item = data[0]
                lat = float(item["lat"])
                lon = float(item["lon"])
                return (lat, lon)
            return None
        except Exception as e:
            print(f"[Geocoding] Failed: {e}")
            return None
            
    def deg_buffer(self, lat: float, meters: float) -> Tuple[float, float]:
        """Convert meter buffer to degree buffer (rough approximation)"""
        lat_deg_per_m = 1.0 / 111320.0
        lon_deg_per_m = 1.0 / (111320.0 * abs(math.cos(math.radians(lat))))
        lat_buf = meters * lat_deg_per_m
        lon_buf = meters * lon_deg_per_m
        return (lat_buf, lon_buf)
        
    def search_hls_items(self, lat: float, lon: float, dt: str, limit: int = 10) -> List[Dict]:
        """Search for HLS items near a point and date"""
        try:
            # Use a small buffer around the point
            import math
            lat_buf, lon_buf = self.deg_buffer(lat, 10000)  # 10km buffer
            bbox = [lon - lon_buf, lat - lat_buf, lon + lon_buf, lat + lat_buf]
            
            # Parse the date and create a range
            try:
                target_dt = datetime.fromisoformat(dt).replace(tzinfo=timezone.utc)
            except:
                target_dt = datetime.now(timezone.utc)
                
            start_dt = target_dt - timedelta(days=30)
            end_dt = target_dt + timedelta(days=30)
            
            collections = ["HLSL30.v2.0", "HLSS30.v2.0"]
            all_items = []
            
            for coll in collections:
                params = {
                    "limit": limit,
                    "bbox": ",".join(map(str, bbox)),
                    "datetime": f"{start_dt.isoformat()}/{end_dt.isoformat()}",
                }
                headers = {"Accept": "application/geo+json"}
                
                url = f"{self.cmr_stac_root}/collections/{coll}/items"
                r = requests.get(url, params=params, headers=headers, timeout=30)
                r.raise_for_status()
                
                data = r.json()
                items = data.get("features", [])
                
                for item in items:
                    props = item.get("properties", {})
                    dt_str = props.get("datetime", "")
                    if dt_str:
                        try:
                            item_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            time_delta = abs((item_dt - target_dt).total_seconds())
                            item["_time_delta"] = time_delta
                            all_items.append(item)
                        except:
                            pass
                            
            # Sort by time delta and return the closest ones
            all_items.sort(key=lambda x: x.get("_time_delta", float("inf")))
            return all_items[:limit]
            
        except Exception as e:
            print(f"[HLS Search] Failed: {e}")
            return []
            
    def bands_for_collection(self, collection_id: str) -> List[str]:
        """Get available bands for a collection"""
        if "HLSL30" in collection_id:
            return ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B10", "B11"]
        elif "HLSS30" in collection_id:
            return ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12"]
        return []
        
    def fetch_hls_tile(self, lat: float, lon: float, date_str: str) -> Dict:
        """
        Fetch HLS satellite data for a location and date.
        
        Args:
            lat: Latitude
            lon: Longitude 
            date_str: Date string (YYYY-MM-DD)
            
        Returns:
            Dict with tile_path, preview_png, or error
        """
        try:
            # This is a simplified implementation - the full version would need
            # rasterio and numpy for actual data processing
            items = self.search_hls_items(lat, lon, date_str, limit=3)
            
            if not items:
                return {"error": "No HLS items found near that point/date. Try adjusting date."}
                
            # For now, return a mock successful response
            # In the real implementation, this would download and process the satellite data
            return {
                "tile_path": f"/hls_tile_{lat:.5f}_{lon:.5f}_{date_str}.tif",
                "preview_png": f"/hls_tile_{lat:.5f}_{lon:.5f}_{date_str}.png",
                "items_found": len(items)
            }
            
        except Exception as e:
            return {"error": f"Failed to fetch HLS tile: {str(e)}"}


# Global instance
hls_client = HLSClient()