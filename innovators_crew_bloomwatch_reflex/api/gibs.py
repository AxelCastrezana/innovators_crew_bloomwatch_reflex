"""
NASA GIBS WMS API Client
Handles communication with NASA GIBS Web Map Service
"""
import requests
import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional, List, Dict, Tuple


class GIBSClient:
    """Client for NASA GIBS WMS services"""
    
    def __init__(self):
        self.wms_cap_url = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?SERVICE=WMS&REQUEST=GetCapabilities"
        self.wms_base_url = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"
        self.layer_time_default = {}
        self.layer_time_values = {}
        
    def list_wms_layers(self) -> List[str]:
        """Fetch and parse WMS capabilities to get available layers"""
        try:
            r = requests.get(self.wms_cap_url, timeout=20)
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
                        self.layer_time_values[lid] = vals
                        self.layer_time_default[lid] = vals[-1]
                        
            return sorted(set(layers))
        except Exception as e:
            print(f"[WMS caps] Failed to fetch/parse capabilities: {e}")
            return []
    
    def choose_time(self, layer_id: str, desired_date: Optional[str] = None) -> str:
        """Choose appropriate time for a layer"""
        allowed = self.layer_time_values.get(layer_id)
        if allowed:
            if desired_date and desired_date.strip() in allowed:
                return desired_date.strip()
            return self.layer_time_default.get(layer_id, allowed[-1])
        return (desired_date or date.today().isoformat())
    
    def get_wms_service_info(self) -> Dict:
        """Get WMS service information and capabilities"""
        try:
            r = requests.get(self.wms_cap_url, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            ns = {"wms": "http://www.opengis.net/wms"}
            
            service_el = root.find("wms:Service", ns)
            if service_el is None:
                return {"error": "No Service element found"}
                
            title_el = service_el.find("wms:Title", ns)
            abstract_el = service_el.find("wms:Abstract", ns)
            
            return {
                "title": title_el.text if title_el is not None else "Unknown",
                "abstract": abstract_el.text if abstract_el is not None else "No description",
                "url": self.wms_base_url,
            }
        except Exception as e:
            return {"error": f"Failed to get service info: {e}"}
    
    def get_wms_layer_attrs(self, layer_id: str) -> Dict:
        """Get detailed attributes for a specific WMS layer"""
        try:
            r = requests.get(self.wms_cap_url, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            ns = {"wms": "http://www.opengis.net/wms"}
            
            # Find the specific layer
            for lyr in root.findall(".//wms:Capability/wms:Layer//wms:Layer", ns):
                name_el = lyr.find("wms:Name", ns)
                if name_el is not None and name_el.text and name_el.text.strip() == layer_id:
                    title_el = lyr.find("wms:Title", ns)
                    abstract_el = lyr.find("wms:Abstract", ns)
                    
                    # Time values
                    time_vals = self.layer_time_values.get(layer_id, [])
                    time_default = self.layer_time_default.get(layer_id, "")
                    
                    return {
                        "name": layer_id,
                        "title": title_el.text if title_el is not None else layer_id,
                        "abstract": abstract_el.text if abstract_el is not None else "No description",
                        "time_values": time_vals,
                        "time_default": time_default,
                        "time_count": len(time_vals),
                    }
                    
            return {"error": f"Layer '{layer_id}' not found"}
        except Exception as e:
            return {"error": f"Failed to get layer attributes: {e}"}
            
    def get_available_layers(self) -> List[str]:
        """Get list of available WMS layers"""
        return self.list_wms_layers()
        
    def get_service_info(self) -> Dict:
        """Get WMS service information - alias for compatibility"""
        return self.get_wms_service_info()
        
    def get_layer_attrs(self, layer_id: str) -> Dict:
        """Get layer attributes - alias for compatibility"""
        return self.get_wms_layer_attrs(layer_id)


# Global instance
gibs_client = GIBSClient()