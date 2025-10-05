# BloomWatch Modular Architecture

This document outlines the modular architecture implemented for the BloomWatch application.

## Directory Structure

```
innovators_crew_bloomwatch_reflex/
├── api/                 # External API clients
│   ├── __init__.py
│   ├── gibs.py         # NASA GIBS WMS client
│   ├── huggingface.py  # HuggingFace Spaces client
│   └── hls.py          # NASA HLS satellite data client
├── services/            # Business logic services
│   ├── __init__.py
│   └── maps.py         # Folium map generation service
├── utils/              # Utility functions
│   ├── __init__.py
│   ├── helpers.py      # General helper functions
│   └── file_utils.py   # File handling utilities
├── state/              # Application state management
│   ├── __init__.py
│   └── app_state.py    # Main Reflex State class
├── components/         # UI components
│   ├── __init__.py
│   └── ui_components.py # Reusable UI components
├── main.py            # New modular main file
└── innovators_crew_bloomwatch_reflex.py  # Original monolithic file
```

## Module Descriptions

### API Clients (`api/`)
- **gibs.py**: NASA GIBS WMS service client for satellite layer discovery and metadata
- **huggingface.py**: HuggingFace Spaces client for crop classification ML inference
- **hls.py**: NASA HLS satellite data client via CMR STAC API

### Services (`services/`)
- **maps.py**: MapService class for creating Folium maps with GIBS layers and custom styling

### Utilities (`utils/`)
- **helpers.py**: Common utility functions (safe_float, slug, clamp, etc.)
- **file_utils.py**: File handling utilities for uploads, downloads, and validation

### State Management (`state/`)
- **app_state.py**: Main Reflex State class with all application state and event handlers

### UI Components (`components/`)
- **ui_components.py**: Reusable UI components for different sections of the application

### Main Application (`main.py`)
- New modular main file that imports and uses all the separated modules
- Clean separation between UI and logic
- Easy to maintain and extend

## Benefits of Modular Architecture

1. **Separation of Concerns**: Each module has a specific responsibility
2. **Reusability**: Components and services can be easily reused
3. **Maintainability**: Easier to find, fix, and update specific functionality
4. **Testability**: Individual modules can be tested in isolation
5. **Scalability**: New features can be added as new modules
6. **Code Organization**: Logical grouping of related functionality

## Migration Strategy

The original monolithic file (`innovators_crew_bloomwatch_reflex.py`) is preserved for reference. To use the modular version:

1. Update your main import to use `main.py` instead
2. All functionality remains the same - just better organized
3. The Docker setup and dependencies remain unchanged

## Usage

To run the modular application:
```bash
cd innovators_crew_bloomwatch_reflex
reflex run --backend-host 0.0.0.0 --frontend-host 0.0.0.0
```

The application will function identically to the original monolithic version, but with much better code organization.