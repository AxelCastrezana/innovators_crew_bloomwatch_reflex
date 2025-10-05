"""
BloomWatch - Geospatial Data Viewer and Crop Classification App
Main application file using modular architecture

⚡ Code generated with AI assistance (GitHub Copilot) for modular refactoring
"""

import reflex as rx

# Import state from modular structure
from .state import State

# Import UI components
from .components import (
    header_component,
    map_viewer_component,
    layer_selector_component,
    tile_fetcher_component,
    crop_classification_component,
    top_controls
)


def index() -> rx.Component:
    """Main page component."""
    return rx.container(
        top_controls(),
        header_component(),
        rx.spacer(height="20px"),
        map_viewer_component(),
        rx.spacer(height="20px"),
        layer_selector_component(),
        rx.spacer(height="20px"),
        tile_fetcher_component(),
        rx.spacer(height="20px"),
        crop_classification_component(),
    )


# App styling
style = {
    rx.text: {
        "font_family": "Figtree",
    },
    rx.heading: {
        "font_family": "Figtree",
    }
}

# Create and configure the app
app = rx.App(style=style)
app.add_page(index)