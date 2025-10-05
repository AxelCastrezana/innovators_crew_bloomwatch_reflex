"""
Map service for generating Folium maps with GIBS layers
"""
import os
import folium
from folium.plugins import Draw, MousePosition
from typing import Optional, Tuple


class MapService:
    """Service for creating and managing maps"""
    
    def __init__(self):
        self.show_leaflet_layer_control = False
        
    def create_folium_map(
        self, 
        selected_layer: Optional[str] = None, 
        date_str: Optional[str] = None, 
        bbox: Optional[Tuple[float, float, float, float]] = None,
        center_lat: float = 41.0,
        center_lon: float = -70.0,
        zoom: int = 4
    ) -> folium.Map:
        """
        Create a Folium map with GIBS layer
        
        Args:
            selected_layer: GIBS layer name
            date_str: Date string for time-enabled layers
            bbox: Bounding box (minlon, minlat, maxlon, maxlat)
            center_lat: Map center latitude
            center_lon: Map center longitude  
            zoom: Initial zoom level
            
        Returns:
            Folium map object
        """
        # Create base map
        m = folium.Map(
            location=[center_lat, center_lon], 
            zoom_start=zoom, 
            tiles="OpenStreetMap"
        )
        
        # Add GIBS layer if specified
        if selected_layer:
            self._add_gibs_layer(m, selected_layer, date_str)
            
        # Add drawing tools
        draw = Draw(
            export=True,
            position="topleft",
            draw_options={
                "polyline": False,
                "polygon": True,
                "circle": False,
                "rectangle": True,
                "marker": True,
                "circlemarker": False,
            }
        )
        draw.add_to(m)
        
        # Add mouse position
        MousePosition().add_to(m)
        
        # Add layer control if enabled
        if self.show_leaflet_layer_control:
            folium.LayerControl().add_to(m)
            
        return m
        
    def _add_gibs_layer(self, map_obj: folium.Map, layer_name: str, date_str: Optional[str] = None):
        """Add GIBS WMS layer to map"""
        wms_url = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
        
        # Use the provided layer name or default
        actual_layer = layer_name or "Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual"
        
        folium.WmsTileLayer(
            url=wms_url,
            name=actual_layer,
            fmt="image/png",
            layers=actual_layer,
            transparent=True,
            overlay=True,
            control=True,
        ).add_to(map_obj)
        
    def write_folium_map_to_assets(
        self, 
        selected_layer: Optional[str] = None, 
        date_str: Optional[str] = None, 
        bbox: Optional[Tuple[float, float, float, float]] = None
    ) -> str:
        """
        Create Folium map and save to assets directory
        
        Returns:
            Relative path to saved map file
        """
        try:
            assets_dir = os.path.join(os.getcwd(), "assets")
            os.makedirs(assets_dir, exist_ok=True)
            
            # Create the map
            m = self.create_folium_map(selected_layer, date_str, bbox)
            
            # Generate filename
            layer_slug = selected_layer.replace(" ", "_").replace("/", "_") if selected_layer else "default"
            filename = f"folium_map_{layer_slug}_{date_str or 'current'}.html"
            filepath = os.path.join(assets_dir, filename)
            
            # Save map
            m.save(filepath)
            
            return f"/{filename}"
            
        except Exception as e:
            print(f"[Map Service] Failed to write map: {e}")
            return ""


# Global instance
map_service = MapService()