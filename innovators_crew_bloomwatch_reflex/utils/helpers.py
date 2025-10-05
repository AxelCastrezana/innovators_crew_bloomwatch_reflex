"""
Utility helper functions
"""
import re
from typing import Optional


def safe_float(s: Optional[str]) -> Optional[float]:
    """Safely convert string to float"""
    if not s or not s.strip():
        return None
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return None


def slug(s: str) -> str:
    """Convert string to URL-safe slug"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', s.strip())


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max"""
    return max(min_val, min(max_val, value))


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to max length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."