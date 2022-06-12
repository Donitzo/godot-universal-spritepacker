# smart_splitter
A python script for splitting images and vector files into spritesheets.

# usage: 
`smart_split.py [-h] [--image_directory IMAGE_DIRECTORY] [--inkscape_path INKSCAPE_PATH] source_directory spritesheet_path`

The created spritesheet is in the form of a .PNG image and and .JSON file defining the coordinates of the sprites. The .JSON format SHOULD be compatible with the [PixiJS Spritesheet format](https://github.com/pixijs/pixijs/blob/main/packages/spritesheet/src/Spritesheet.ts), although many features are left unused, such as rotation and trimming.

A copy of the sprites are saved in `image_directory` if set. Useful if you just want to export images from a .SVG file.

If you want to split .SVG files you need to set the --inkscape_path (defaults to `C:/Program Files/Inkscape/bin/inkscape`)

The `source_directory` should contain a folder structure of images which you want to split.

The image names should have one of the following formats:

`sprite_name__<x>x<y>.png/bmp/jpg/jpeg`: X/Y is the sprite size
`sprite_name__<x>x<y>p<p>.png/bmp/jpg/jpeg`: P is the padding between sprites
`sprite_name.png/bmp/jpg/jpeg`: The file is copied as-is.
`sprite_name.svg`: The vector file is exported by layer.
