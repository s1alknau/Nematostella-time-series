# Device Photos for Documentation

This directory contains photos of the Nematostella timelapse recording hardware setup.

## Required Photos

Add the following photos to this directory to complete the hardware documentation:

### 1. `system_complete.jpg`
**Full system overview**
- Show complete setup including:
  - ESP32 controller
  - LED array (IR + White)
  - Camera
  - Sample chamber
  - Power supplies
  - All cable connections
- **Suggested specs:** 1920x1080 or higher, well-lit, multiple angles if possible

### 2. `esp32_assembly.jpg`
**ESP32 controller assembly detail**
- Close-up of ESP32 DevKit board
- DHT22 sensor connection visible
- LED driver connections visible
- USB cable visible
- Labels/annotations recommended
- **Suggested specs:** High-resolution close-up, clear component identification

### 3. `led_setup.jpg`
**LED illumination system**
- IR LED (850nm) positioning
- White LED positioning
- LED drivers
- Mounting hardware
- Illumination pattern on sample chamber
- **Suggested specs:** Show both LEDs clearly, include IR viewer card if available

### 4. `sample_chamber.jpg`
**Sample chamber detail**
- Nematostella specimen visible (if possible)
- Chamber construction
- LED illumination pattern
- Temperature sensor placement
- **Suggested specs:** Clear view of chamber and organism positioning

### 5. `wiring_overview.jpg`
**Complete wiring diagram**
- All connections visible:
  - ESP32 to LEDs
  - ESP32 to DHT22
  - ESP32 to computer (USB)
  - Power supply connections
- Cable routing
- **Suggested specs:** Overhead or angled view showing all connections

## Photo Guidelines

### Technical Requirements
- **Resolution:** Minimum 1920x1080 (Full HD)
- **Format:** JPG or PNG
- **File size:** Keep under 5MB per image (compress if needed)
- **Lighting:** Well-lit, avoid shadows on critical components

### Content Guidelines
- **Labels:** Add text annotations for key components (Photoshop, GIMP, or similar)
- **Scale:** Include ruler or scale reference when showing component details
- **Angles:** Take multiple shots from different angles, use the best one
- **Focus:** Ensure critical components (connectors, sensors) are in sharp focus
- **Background:** Use clean, uncluttered background where possible

### Annotation Suggestions

Use image editing software to add:
- **Arrows** pointing to key components
- **Text labels** for:
  - GPIO pins (25, 26, 4)
  - Component names (ESP32, DHT22, IR LED, etc.)
  - Power ratings (12V, 3.3V, etc.)
  - Signal types (PWM, Data, GND)
- **Color coding**:
  - Red for power connections
  - Blue for signal connections
  - Black for ground connections

## Alternative: Schematic Diagrams

If photographs are not available or unclear, consider creating:
- **Fritzing diagrams** (free tool: fritzing.org)
- **KiCad schematics** (free EDA tool)
- **Hand-drawn diagrams** (scanned/photographed)

These can supplement or replace photos in some cases.

## How to Add Photos

1. **Capture photos** following guidelines above
2. **Edit/annotate** images for clarity
3. **Save images** to this directory with exact filenames listed above
4. **Verify** images appear in main README.md

The main README.md already references these images, so once you add them here, they will automatically appear in the documentation.

## Current Status

- [ ] system_complete.jpg
- [ ] esp32_assembly.jpg
- [ ] led_setup.jpg
- [ ] sample_chamber.jpg
- [ ] wiring_overview.jpg

Check off items as you add them!
