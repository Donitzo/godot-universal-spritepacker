# Godot Universal SpritePacker

![Example](https://github.com/Donitzo/godot-universal-spritepacker/blob/main/example.png)

## Description

**Godot Universal SpritePacker** is a Python tool that splits, packs, and converts individual sprites, tilesets, and SVG layers into spritesheets and Godot-ready `.tres` resources (AtlasTextures for single sprites and SpriteFrames for animations).  
It intelligently packs images or SVG layers into one or more texture atlases (spritesheets) and generates either a [PixiJS-compatible](https://github.com/pixijs/pixijs/blob/main/packages/spritesheet/src/Spritesheet.ts) `.json` metadata file or native Godot `.tres` resource files.

The relative folder structure of your source files is preserved in sprite names for easier categorization.

This tool was originally created as a lightweight alternative to TexturePacker for my retro game projects. As I started using **Godot** more, I added support for exporting directly into Godot’s native `.tres` format for both AtlasTextures and SpriteFrames.

> **Note:** Frame trimming (transparent border removal) is **not** currently supported.

---

## How It Works

The tool follows these steps:

1. Scans the specified `source_directory` (and subdirectories) for images and vector files.
2. Parses filenames to detect optional suffixes indicating tile size, frame rate, padding, etc.
3. Splits images into individual sprites based on the specified tile size.
   - If the file is an SVG, each **layer** is exported as a separate sprite.
4. Optionally saves individual sprite images to `image_directory`.
5. Packs sprites into one or more optimized spritesheets (texture atlases).
6. Generates metadata files:
   - (a) [PixiJS-compatible](https://github.com/pixijs/pixijs/blob/main/packages/spritesheet/src/Spritesheet.ts) `.json`
   - (b) Godot 4 AtlasTexture `.tres` files
   - (c) Godot 4 SpriteFrames `.tres` files (for animations)

---

## Requirements

- **Python 3**
- Install the required Python packages:

```bash
pip install pillow rectpack
```

- **Inkscape** (optional, for SVG layer processing)  
  If Inkscape is not installed at the default path, set it manually using `--inkscape_path`.

---

## File Naming Convention

Files should be named according to this pattern:

```
name__WxH[pN][fpsN][loop]
```

### Examples:
- `hero__32x32.png` - A static 32×32 sprite
- `walk__64x64p2fps12loop.png` - 64×64 sprite with 2px padding, 12 FPS animation, looping

| Field | Description |
|:------|:------------|
| `name` | Sprite or animation name |
| `W x H` | Tile width × height in pixels |
| `pN` | (optional) Padding between tiles (e.g., `p2` = 2px) |
| `fpsN` | (optional) Frame rate in frames per second (e.g., `fps12`) |
| `loop` | (optional) If present, marks the animation as looping |

If the source file is located inside a subfolder, the relative path is included in the sprite's name (e.g., `enemies/boss__64x64.png`).

---

## Animation Metadata (CSV)

You can define complex animations using a `.csv` file with the same base name as the image.

### Example: `hero.csv`
```
name;start_x;start_y;count_x;count_y;fps;loop
Walk;0;0;4;2;12;true
```

| Field | Meaning |
|:------|:--------|
| `name` | Animation name |
| `start_x` | Starting tile column (0-based) |
| `start_y` | Starting tile row (0-based) |
| `count_x` | Number of columns (tiles) in the animation |
| `count_y` | Number of rows (tiles) in the animation |
| `fps` | Playback speed (frames per second) |
| `loop` | Whether the animation should loop (`true`/`false`) |

---

## Command-Line Interface

Run the tool with:

```bash
python spritepacker.py --source_directory <source_dir> --spritesheet_path <output_path> [options]
```

### Required Arguments
| Argument | Description |
|:---|:---|
| `--source_directory` | Directory containing source images, SVGs, or tilesets. |
| `--spritesheet_path` | Output path (without extension) for the spritesheet(s). |

### Optional Arguments
| Argument | Description |
|:---|:---|
| `--image_directory` | Directory to save individual sprite images before packing. |
| `--godot_sprites_directory` | Directory to output Godot `.tres` files (AtlasTextures and SpriteFrames). |
| `--godot_resource_directory` | Internal Godot resource path for spritesheets (default: `res://textures/`). |
| `--inkscape_path` | Custom path to the Inkscape executable for SVG processing. |
| `--max_spritesheet_size` | Maximum width/height for each spritesheet (default: `4096`). |

---

## Issues

Please report any bugs, feature requests, or questions in the [Issues section](https://github.com/Donitzo/godot-universal-spritepacker/issues).