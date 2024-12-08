# RAF Photo Importer

A simple tool inspired by Photo Mechanic to quickly review and select Fujifilm RAF files from your SD card. This is an early development version focused on basic functionality.

## Purpose

The main goal is to provide a quick way to:
- Review RAF files from your camera
- Mark the ones you want to keep (using a star rating system)
- Export selected photos to JPG format
- Continue your workflow (e.g. Lightroom, VSCO, etc.)

## Current Features

- Basic RAF file handling with preview support
- Grid view and single image view
- Simple star rating system (0-5)
- Basic JPG export for selected images
- Dark theme interface

## Requirements

- Python 3.8 or higher
- Required packages (installed via pip):
  - rawpy
  - PyQt6
  - Pillow

## Installation

1. Clone or download this repository
2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```
3. Install requirements:
```bash
pip install -r requirements.txt
```

## Basic Usage

1. Start the tool:
```bash
python raf_importer.py
or
python3 raf_importer.py
```

2. How to use:
   - Select a folder containing RAF files
   - Browse through images in grid or single view (Space to toggle)
   - Rate images using number keys 0-5 or buttons
   - Export selected images (rated 1-5 stars) to JPG

## Controls

- **Space**: Switch between grid and single view
- **←/→**: Previous/Next image
- **0-5**: Rate current image
- Filter dropdown: Show images by rating

## Known Limitations

- Early development version
- Basic functionality only
- Limited error handling
- May have performance issues with very large collections
- Some orientation issues might occur with certain RAF files

## Development Status

This is a work in progress. Features and stability improvements will be added over time. Feel free to report issues or suggest improvements.

## Acknowledgments

Inspired by Photo Mechanic's workflow for quick image selection and export. 