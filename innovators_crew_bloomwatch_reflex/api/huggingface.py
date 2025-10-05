"""
HuggingFace API Client
Handles communication with HuggingFace Spaces for crop classification

⚡ Code generated with AI assistance (GitHub Copilot) for modular refactoring
"""
import os
from typing import Optional, List, Tuple

try:
    from gradio_client import Client, handle_file
except Exception:
    Client = None
    def handle_file(x):
        return x


class HuggingFaceClient:
    """Client for HuggingFace Spaces API"""
    
    def __init__(self):
        self.space_name = "ibm-nasa-geospatial/Prithvi-100M-multi-temporal-crop-classification-demo"
        self.api_name = "/partial"
        
    def predict_crop_classification(self, file_path: str) -> Tuple[bool, str, Optional[List[str]]]:
        """
        Send image to HuggingFace model for crop classification
        
        Returns:
            Tuple of (success, message, result_files)
        """
        if Client is None:
            return False, "gradio_client not installed. Run: pip install gradio_client", None
            
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}", None
            
        try:
            # Optional Hugging Face token for private Spaces
            hf_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN") or os.environ.get("HF_TOKEN") or None
            
            print(f"[HF Client] Sending file: {file_path}")
            client = Client(self.space_name, hf_token=hf_token)
            
            result = client.predict(target_image=handle_file(file_path), api_name=self.api_name)
            print(f"[HF Client] API response: {result}")
            
            # Expect a tuple/list of 4 filepaths (T1, T2, T3, prediction)
            if not isinstance(result, (list, tuple)) or len(result) < 4:
                return False, f"Unexpected response from model: {type(result)} with {len(result) if hasattr(result, '__len__') else 'unknown'} items", None
                
            return True, "Prediction successful", list(result)
            
        except Exception as e:
            print(f"[HF Client] API call failed: {e}")
            return False, f"Model call failed: {e}", None

    def classify_crop_image(self, image_path: str):
        """
        Classify crop type from satellite imagery - compatibility method for state module.
        
        Args:
            image_path: Path to the image file to classify
            
        Returns:
            Dict containing classification results and images
        """
        success, message, result_files = self.predict_crop_classification(image_path)
        
        if success and result_files:
            return {
                "images": result_files,
                "success": True
            }
        else:
            return {"error": message}


# Global instance
hf_client = HuggingFaceClient()