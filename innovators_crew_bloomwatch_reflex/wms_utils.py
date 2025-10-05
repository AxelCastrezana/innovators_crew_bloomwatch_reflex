import requests
import xml.etree.ElementTree as xmlet

def list_wms_layers(url: str) -> list[str]:
    """Fetch and parse WMS capabilities to return all available layers."""
    response = requests.get(f"{url}?service=WMS&request=GetCapabilities")
    response.raise_for_status()

    WmsTree = xmlet.fromstring(response.content)
    all_layers = []

    for child in WmsTree.iter():
        for layer in child.findall("./{http://www.opengis.net/wms}Capability/{http://www.opengis.net/wms}Layer//*/"):
            if layer.tag == '{http://www.opengis.net/wms}Layer':
                name_tag = layer.find("{http://www.opengis.net/wms}Name")
                if name_tag is not None:
                    all_layers.append(name_tag.text)

    return sorted(all_layers)