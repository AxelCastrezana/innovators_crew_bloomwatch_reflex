#!/usr/bin/env python3
"""
Simple script to fetch a single tile from NASA GIBS (WMTS).

This script:
- Downloads GetCapabilities XML from the GIBS WMTS endpoint.
- Attempts to find a ResourceURL template for the requested layer.
- Builds a tile URL for the given z/x/y (with optional date/time) and downloads it.

Usage:
    python scripts/fetch_gibs_tile.py \
        --layer MODIS_Terra_CorrectedReflectance_TrueColor \
        --z 3 --x 2 --y 1 \
        --date 2020-01-01 \
        --output tile.jpg

Notes:
- Static assets in Reflex are served under /_static/ when running the app, but this script talks directly to GIBS.
- If a ResourceURL template isn't available in GetCapabilities, the script falls back to a common GIBS URL pattern.
"""

import argparse
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import sys

GIBS_WMTS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi"


def get_capabilities(timeout=30):
    params = {"service": "WMTS", "request": "GetCapabilities"}
    r = requests.get(GIBS_WMTS_BASE, params=params, timeout=timeout)
    r.raise_for_status()
    return r.content


def find_layer_resource_template(cap_xml: bytes, layer_name: str):
    # Namespaces used in WMTS GetCapabilities
    ns = {
        'wmts': 'http://www.opengis.net/wmts/1.0',
        'ows': 'http://www.opengis.net/ows/1.1'
    }
    root = ET.fromstring(cap_xml)

    # Iterate layers to find one with matching Identifier
    for layer in root.findall('.//wmts:Layer', ns):
        ident = layer.find('ows:Identifier', ns)
        if ident is not None and ident.text == layer_name:
            # Look for ResourceURL element which often contains a template
            res = layer.find('wmts:ResourceURL', ns)
            if res is not None and 'template' in res.attrib:
                return res.attrib['template']
            # Fallback: some capabilities describe TileMatrixSetLinks; skip complex parsing here
    return None


def build_tile_url_from_template(template: str, z: int, x: int, y: int, time: str = 'default') -> str:
    url = template
    url = url.replace('{TileMatrix}', str(z)).replace('{TileRow}', str(y)).replace('{TileCol}', str(x))
    url = url.replace('{Time}', time)
    # Some templates use {TileMatrix}/{TileRow}/{TileCol} or {z}/{y}/{x}
    url = url.replace('{z}', str(z)).replace('{x}', str(x)).replace('{y}', str(y))
    return url


def build_fallback_tile_url(layer: str, z: int, x: int, y: int, time: str = 'default') -> str:
    # Common GIBS pattern for EPSG:3857 'best' endpoint
    # Use GoogleMapsCompatible_Level{z} as the TileMatrixSet name used by many GIBS layers
    tilematrixset = f'GoogleMapsCompatible_Level{z}'
    # Many layers are served as JPG; some support PNG. Use jpg by default.
    return f'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time}/{tilematrixset}/{z}/{y}/{x}.jpg'


def download_tile(url: str, out_path: str, timeout: int = 30):
    print(f'Downloading: {url}')
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    with open(out_path, 'wb') as fh:
        fh.write(r.content)
    print(f'Saved tile to {out_path}')


def main():
    parser = argparse.ArgumentParser(description='Fetch a single tile from NASA GIBS WMTS')
    parser.add_argument('--layer', required=True, help='GIBS layer identifier (e.g. MODIS_Terra_CorrectedReflectance_TrueColor)')
    parser.add_argument('--z', type=int, required=True, help='Zoom / TileMatrix')
    parser.add_argument('--x', type=int, required=True, help='Tile column')
    parser.add_argument('--y', type=int, required=True, help='Tile row')
    parser.add_argument('--date', dest='date', default='default', help='Date (YYYY-MM-DD) or "default"')
    parser.add_argument('--output', '-o', default='tile.jpg', help='Output filename')
    args = parser.parse_args()

    try:
        cap_xml = get_capabilities()
    except Exception as e:
        print('Error fetching GetCapabilities:', e, file=sys.stderr)
        sys.exit(1)

    template = find_layer_resource_template(cap_xml, args.layer)
    if template:
        tile_url = build_tile_url_from_template(template, args.z, args.x, args.y, args.date)
    else:
        print('No ResourceURL template found in GetCapabilities; using fallback URL pattern')
        tile_url = build_fallback_tile_url(args.layer, args.z, args.x, args.y, args.date)

    try:
        download_tile(tile_url, args.output)
    except Exception as e:
        print('Error downloading tile:', e, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
