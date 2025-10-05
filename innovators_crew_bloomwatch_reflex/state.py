# Reflex State & events
# state.py

import reflex as rx
from services.map_service import ensure_folium_map_written

class State(rx.State):
    map_ready: bool = False

    def build_map(self):
        ensure_folium_map_written()   # writes only if needed
        self.map_ready = True