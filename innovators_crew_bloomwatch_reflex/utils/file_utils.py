"""
File handling utilities
"""
import os
import shutil
import requests
from urllib.parse import urlsplit
from typing import Optional, Dict, Any


def save_uploaded_file(file_obj: Dict[str, Any], assets_dir: str, prefix: str = "upload") -> Optional[str]:
    """
    Save uploaded file to assets directory
    
    Args:
        file_obj: File object from Reflex upload
        assets_dir: Target directory
        prefix: Filename prefix
        
    Returns:
        Local file path or None if failed
    """
    try:
        os.makedirs(assets_dir, exist_ok=True)
        
        # Best-effort: prefer a provided local path; else try a url; else a name+bytes
        local_path = None
        
        if file_obj.get("path"):
            # Already a temp file path on disk
            src_path = file_obj["path"]
            ext = os.path.splitext(src_path)[1] or ".bin"
            out_path = os.path.join(assets_dir, f"{prefix}{ext}")
            
            try:
                with open(src_path, "rb") as r, open(out_path, "wb") as w:
                    w.write(r.read())
                local_path = out_path
            except Exception:
                local_path = src_path
                
        elif file_obj.get("url"):
            # Download from a provided URL
            url = file_obj["url"]
            ext = os.path.splitext(urlsplit(url).path)[1] or ".bin"
            out_path = os.path.join(assets_dir, f"{prefix}{ext}")
            
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                with open(out_path, "wb") as w:
                    w.write(resp.content)
                local_path = out_path
            except Exception as e:
                print(f"[File save] download error: {e}")
                
        elif file_obj.get("name") and file_obj.get("data"):
            # Some environments pass inline bytes (rare). Try to persist.
            ext = os.path.splitext(file_obj["name"])[1] or ".bin"
            out_path = os.path.join(assets_dir, f"{prefix}{ext}")
            
            try:
                with open(out_path, "wb") as w:
                    w.write(file_obj["data"])  # may already be bytes
                local_path = out_path
            except Exception as e:
                print(f"[File save] write bytes error: {e}")
                
        return local_path
        
    except Exception as e:
        print(f"[File save] error: {e}")
        return None


def fetch_to_assets(src_path: str, assets_dir: str, out_name: str) -> str:
    """
    Fetch file (local or URL) to assets directory
    
    Args:
        src_path: Source file path or URL
        assets_dir: Target directory
        out_name: Output filename
        
    Returns:
        Relative path for web access (with leading /)
    """
    try:
        os.makedirs(assets_dir, exist_ok=True)
        out_path = os.path.join(assets_dir, out_name)
        
        if src_path.startswith("http://") or src_path.startswith("https://"):
            r = requests.get(src_path, timeout=60)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(r.content)
        else:
            with open(src_path, "rb") as r, open(out_path, "wb") as w:
                w.write(r.read())
                
        return "/" + os.path.basename(out_path)
        
    except Exception as e:
        print(f"[Fetch to assets] error: {e}")
        return ""


def validate_file_type(file_path: str, allowed_extensions: list) -> bool:
    """
    Validate file type by extension
    
    Args:
        file_path: Path to file
        allowed_extensions: List of allowed extensions (with or without dots)
        
    Returns:
        True if file type is allowed
    """
    if not file_path or not os.path.exists(file_path):
        return False
        
    ext = os.path.splitext(file_path)[1].lower()
    
    # Normalize extensions (ensure they start with .)
    normalized_exts = []
    for allowed_ext in allowed_extensions:
        if not allowed_ext.startswith('.'):
            allowed_ext = '.' + allowed_ext
        normalized_exts.append(allowed_ext.lower())
        
    return ext in normalized_exts


def validate_file_size(file_path: str, max_size_mb: float = 100) -> bool:
    """
    Validate file size
    
    Args:
        file_path: Path to file
        max_size_mb: Maximum allowed size in MB
        
    Returns:
        True if file size is within limits
    """
    if not file_path or not os.path.exists(file_path):
        return False
        
    try:
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        return size_mb <= max_size_mb
    except Exception:
        return False


def get_file_extension(file_path: str) -> str:
    """
    Get file extension from path
    
    Args:
        file_path: Path to file
        
    Returns:
        File extension (with dot) or empty string
    """
    if not file_path:
        return ""
    return os.path.splitext(file_path)[1].lower()


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/(1024**2):.1f} MB"
    else:
        return f"{size_bytes/(1024**3):.1f} GB"