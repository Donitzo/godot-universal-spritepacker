# smart_splitter

## About

A python script for splitting multiple images and vector files into spritesheets for Godot and other engines which support the [PixiJS Spritesheet format](https://github.com/pixijs/pixijs/blob/main/packages/spritesheet/src/Spritesheet.ts).

Storing numerous sprites individually can be cumbersome and impractical, particularly when dealing with varied sizes. My approach simplifies this by using filenames to denote sprite sizes within various spritesheets. The script scans a source directory, divides the spritesheets into smaller images, and then compiles these into a single, large spritesheet. This consolidated spritesheet is accompanied by a .JSON file detailing each sprite's name and position.

Initially, I used TexturePacker for spritesheet generation post-splitting. I've since integrated this functionality directly into the script via the `rectpack` package.

## usage:
The splitter requires the `rectpack` and `pillow` modules.

```bash
pip install pillow rectpack
```

To run the script, use the following command line interface:

```bash
smart_split.py [-h] [--image_directory IMAGE_DIRECTORY] [--inkscape_path INKSCAPE_PATH] [--godot_sprites_directory GODOT_SPRITES_PATH] source_directory spritesheet_path`
```
The created spritesheet is in the form of a .PNG image and and .JSON file defining the coordinates of the sprites. The .JSON format SHOULD be compatible with the [PixiJS Spritesheet format](https://github.com/pixijs/pixijs/blob/main/packages/spritesheet/src/Spritesheet.ts), although many features are left unused, such as rotation and trimming.

A copy of the sprites are saved in `image_directory` if set. Useful if you just want to export images from a .SVG file.

If you want to split .SVG files you need to set the `--inkscape_path` (defaults to `C:/Program Files/Inkscape/bin/inkscape`). The vector file is split by named layer bounding box.

You can also export Godot sprite resource files (.tres) by specifying the `--godot_sprites_directory`.

The `source_directory` should contain a folder structure of images which you want to split.

## File naming

The image names should have one of the following formats:

`sprite_name__<x>x<y>.png/bmp/jpg/jpeg`: X/Y is the sprite size.

`sprite_name__<x>x<y>p<p>.png/bmp/jpg/jpeg`: P is the padding between sprites.

`sprite_name.png/bmp/jpg/jpeg`: The file is used as-is.

`sprite_name.svg`: The vector file is exported by layer.

## Issues

Please report any bugs you find in [issues](https://github.com/Donitzo/smart_splitter/issues).
