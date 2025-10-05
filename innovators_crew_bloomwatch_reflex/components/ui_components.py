"""
UI Components for BloomWatch Application

This module contains reusable UI components for the BloomWatch application.
"""

import reflex as rx
from ..state import State


def header_component() -> rx.Component:
    """Header component with logo and title."""
    return rx.center(
        rx.vstack(
            rx.hstack(
                rx.image(src="/cropwatch_icon.png", alt="Sample Image", width="40px", height="auto"),
                rx.heading("Cropwatch", size="8", weight="regular"),
            ),
            rx.text("GIBS Tile Fetcher and Map Viewer", size="4", weight="light"),
            spacing="4",
            align="center"
        )
    )


def map_viewer_component() -> rx.Component:
    """Interactive map viewer component."""
    return rx.cond(
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
        rx.text("Click 'Build map' to generate.")
    )


def layer_selector_component() -> rx.Component:
    """Layer selection and filtering component."""
    return rx.center(
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
            layer_details_component(),
        ),
        border="3px solid",
        border_radius="12px",
        padding="20px",
    )


def layer_details_component() -> rx.Component:
    """Layer details panel component."""
    return rx.cond(
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
    )


def tile_fetcher_component() -> rx.Component:
    """HLS tile fetcher component."""
    return rx.center(
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
                rx.input(
                    placeholder="Address (e.g., Paris, France)", 
                    value=State.input_address, 
                    on_change=State.set_input_address, 
                    width="360px"
                ),
                rx.text("or", size="1"),
                rx.input(
                    placeholder="lat", 
                    value=State.input_lat, 
                    on_change=State.set_input_lat, 
                    width="140px"
                ),
                rx.input(
                    placeholder="lon", 
                    value=State.input_lon, 
                    on_change=State.set_input_lon, 
                    width="140px"
                ),
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
    )


def thumb_card(title: str, img_src_var) -> rx.Component:
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


def crop_classification_component() -> rx.Component:
    """Crop classification upload and analysis component."""
    return rx.center(
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
                thumb_card("T1", State.crop_t1),
                thumb_card("T2", State.crop_t2),
                thumb_card("T3", State.crop_t3),
                thumb_card("Model prediction", State.crop_pred_img),
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
    )


def top_controls() -> rx.Component:
    """Top navigation controls."""
    return rx.vstack(
        rx.color_mode.button(position="top-right", border_radius="12px"),
        rx.text("Innovators Crew", position="top-left", size="1", color_scheme="orange"),
    )