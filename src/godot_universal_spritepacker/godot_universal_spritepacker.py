__version__ = '1.1.2'
__author__  = 'Donitz'
__license__ = 'MIT'
__repository__ = 'https://github.com/Donitzo/godot-universal-spritepacker'

# --------------------------------------------------------------------------------------------------
# Imports and type definitions
# --------------------------------------------------------------------------------------------------

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from PIL import Image
from rectpack import newPacker, PackerBFF
from typing import cast, Dict, List, Optional, Tuple, TypedDict

# Minimum and maximum supported Python versions
class UnsupportedVersion(Exception):
    pass

MIN_VERSION, VERSION_LESS_THAN = (3, 9), (4, 0)
if sys.version_info < MIN_VERSION or sys.version_info >= VERSION_LESS_THAN:
    raise UnsupportedVersion('requires Python %s,<%s' %
        ('.'.join(map(str, MIN_VERSION)), '.'.join(map(str, VERSION_LESS_THAN))))

# TypedDict definitions for strong typing
class SizeDict(TypedDict, total=True):
    w: int
    h: int

class RectDict(TypedDict, total=True):
    x: int
    y: int
    w: int
    h: int

class SpriteDict(TypedDict, total=True):
    animated: bool
    duplicate: Optional['SpriteDict']
    frame: RectDict
    image: Image.Image
    name: str
    margin: RectDict
    remove: bool
    resource_path: str
    trimmed: bool

class AnimationDict(TypedDict, total=True):
    framerate: int
    loop: bool
    name: str
    sprites: List[SpriteDict]

class SpriteFrameDict(TypedDict, total=True):
    animations: List[AnimationDict]
    name: str

class FrameEntryDict(TypedDict, total=True):
    frame: RectDict
    rotated: bool
    sourceSize: SizeDict
    spriteSourceSize: RectDict
    trimmed: bool

class AtlasAnimationDict(TypedDict, total=True):
    loop: bool
    framerate: int

class MetaDict(TypedDict, total=True):
    animation_info: Dict[str, AtlasAnimationDict]
    app: str
    format: str
    image: str
    scale: int
    size: SizeDict
    version: str

class AtlasDict(TypedDict, total=True):
    animations: Dict[str, List[str]]
    frames: Dict[str, FrameEntryDict]
    meta: MetaDict

RectTuple = Tuple[int, int, int, int, SpriteDict]

# --------------------------------------------------------------------------------------------------
# Command-line argument parsing
# --------------------------------------------------------------------------------------------------

def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=
            'Godot Universal SpritePacker — split, pack, and convert spritesheets' +
            ' or SVGs into optimized atlases and SpriteFrames for Godot or other engines.'
    )
    parser.add_argument('--source_directory', required=True,
        help='Directory containing source images, SVGs or tilesets to be split and packed.')
    parser.add_argument('--spritesheet_path', required=True,
        help='Path (without extension) where the final packed spritesheet will be saved.')
    parser.add_argument('--save_json', action='store_true',
        help='Whether to create metadata .json files together with the spritesheet.')
    parser.add_argument('--image_directory',
        help='Optional directory in which to export individual sprite images before packing.')
    parser.add_argument('--godot_sprites_directory',
        help='If set, outputs Godot 4 AtlasTextures and SpriteFrames to this directory.')
    parser.add_argument('--godot_resource_directory', default='res://textures/',
        help='Godot resource directory containing spritesheet images. Default is "res://textures/"')
    parser.add_argument('--inkscape_path', default='C:/Program Files/Inkscape/bin/inkscape',
        help='Path to the Inkscape executable. Used for extracting layers from SVG files.')
    parser.add_argument('--max_spritesheet_size', type=int, default=4096,
        help='Maximum width or height (in pixels) for the generated spritesheet. Default is 4096.')
    parser.add_argument('--sprite_padding', type=int, default=1,
        help='Number of transparent pixels to pad around each sprite. Default is 1 = 2 px gap.')
    parser.add_argument('--disable_trimming', action='store_true',
        help='If set, disables transparency trimming.')
    parser.add_argument('--disable_duplicate_removal', action='store_true',
        help='If set, disables duplicate frame detection and removal.')
    parser.add_argument('--default_framerate', type=int,
        help='If set, treats all regular sprites as animations with this framerate.')

    args: argparse.Namespace = parser.parse_args()

    print('Godot Universal SpritePacker %s\n' % __version__)

    # ----------------------------------------------------------------------------------------------
    # Prepare output directory
    # ----------------------------------------------------------------------------------------------

    spritesheet_dir: str = os.path.dirname(args.spritesheet_path)
    if spritesheet_dir != '':
        os.makedirs(spritesheet_dir, exist_ok=True)

    # ----------------------------------------------------------------------------------------------
    # Create all individual sprites
    # ----------------------------------------------------------------------------------------------

    sprites: List[SpriteDict] = []
    sprite_frames: List[SpriteFrameDict] = []

    for root, dirs, filenames in os.walk(args.source_directory):
        for filename in filenames:
            source_path: str = os.path.join(root, filename)
            source_directory: str = os.path.dirname(source_path)
            rel_path: str = os.path.relpath(source_path, args.source_directory)
            prefix: str
            extension: str
            prefix, extension = os.path.splitext(rel_path)

            name: str = prefix.replace('\\', '/')
            if name.startswith('./'):
                name = name[2:]

            # SVG: split into layers via Inkscape
            if extension.lower() == '.svg':
                print('Splitting vector file "%s"' % source_path)

                tree: ET.ElementTree = ET.parse(source_path)
                layers: List[ET.Element] = tree.findall("./{http://www.w3.org/2000/svg}" +
                    "g[@{http://www.inkscape.org/namespaces/inkscape}groupmode='layer']")

                for layer in layers:
                    layer_id: str = layer.attrib['id']
                    label: str = layer.attrib['{http://www.inkscape.org/namespaces/inkscape}label']

                    print('-> Exporting layer "%s"' % label)

                    image_path: str = os.path.join(tempfile.gettempdir(),
                        'gus_%s.png' % os.urandom(12).hex())

                    # call Inkscape to export one layer as PNG
                    try:
                        result: subprocess.CompletedProcess = subprocess.run([
                            args.inkscape_path,
                            source_path,
                            '--export-area-drawing',
                            '--export-type=png',
                            '--export-id-only',
                            '--export-id=%s' % layer_id,
                            '--export-filename=%s' % image_path,
                        ])
                    except FileNotFoundError:
                        print('Unable to find Inkscape. Skipping vector conversion.')
                        continue

                    if result.returncode != 0:
                        sys.exit('Error exporting SVG layer "%s" from "%s"' % (label, source_path))

                    # Wait for output file to appear
                    for attempt in range(10):
                        if os.path.exists(image_path):
                            sprites.append(cast(SpriteDict, {
                                'animated': False,
                                'duplicate': None,
                                'frame': { 'x': 0, 'y': 0, 'w': 0, 'h': 0 },
                                'image': Image.open(image_path).convert('RGBA'),
                                'margin': { 'x': 0, 'y': 0, 'w': 0, 'h': 0 },
                                'name': '%s/%s' % (name, re.sub('[^a-zA-Z0-9_ -]+', '', label)),
                                'remove': False,
                                'resource_path': '',
                                'trimmed': False,
                            }))

                            break

                        if attempt == 9:
                            sys.exit('Error exporting SVG layer "%s" from "%s"'
                                % (label, source_path))
                        else:
                            time.sleep(1)

                    # Clean up temp file
                    while os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                        except OSError:
                            time.sleep(1)

                            print('Failed to delete temporary file')

                continue

            # CSV files are always handled through images
            if extension.lower() == '.csv':
                continue

            if not extension.lower() in ['.png', '.bmp', '.jpg', '.jpeg']:
                print('Ignoring file "%s"' % source_path)

                continue

            # Static image vs tileset detection
            match: Optional[re.Match[str]] = re.search(
                r'^(.*?)__(\d+)x(\d+)(?:p(\d+))?(?:fps(\d+))?(loop)?$', name)

            if not match:
                # Single image sprite

                print('Using single image "%s"' % source_path)

                sprites.append(cast(SpriteDict, {
                    'animated': False,
                    'duplicate': None,
                    'frame': { 'x': 0, 'y': 0, 'w': 0, 'h': 0 },
                    'image': Image.open(source_path).convert('RGBA'),
                    'margin': { 'x': 0, 'y': 0, 'w': 0, 'h': 0 },
                    'name': name,
                    'remove': False,
                    'resource_path': '',
                    'trimmed': False,
                }))

                continue

            # Splitting image into a grid of sprites

            print('Splitting tileset "%s"' % source_path)

            groups: Tuple[Optional[str], ...] = match.groups()

            image_name: str = groups[0] # type: ignore[assignment]

            im: Image.Image = Image.open(source_path).convert('RGBA')

            full_width, full_height = im.size

            tile_width: int = int(groups[1]) # type: ignore[arg-type]
            tile_height: int = int(groups[2]) # type: ignore[arg-type]

            tile_padding: int = 0 if groups[3] is None else int(groups[3])

            start_x: List[int] = list(range(0, full_width, tile_width + tile_padding))
            start_y: List[int] = list(range(0, full_height, tile_height + tile_padding))

            tileset_sprites: List[SpriteDict] = []
            tileset_grid: List[list[SpriteDict]] = [[] for _ in start_x]

            # Crop out each sprite
            for y_i, y in enumerate(start_y):
                y_s: str = str(y_i).zfill(len(str(len(start_y) - 1)))

                for x_i, x in enumerate(start_x):
                    x_s: str = str(x_i).zfill(len(str(len(start_x) - 1)))

                    sprite: SpriteDict = {
                        'animated': False,
                        'duplicate': None,
                        'frame': { 'x': 0, 'y': 0, 'w': 0, 'h': 0 },
                        'image': im.crop((x, y, x + tile_width, y + tile_height)),
                        'margin': { 'x': 0, 'y': 0, 'w': 0, 'h': 0 },
                        'name': '%s__%sx%s' % (image_name, y_s, x_s),
                        'remove': False,
                        'resource_path': '',
                        'trimmed': False,
                    }

                    sprites.append(sprite)
                    tileset_sprites.append(sprite)
                    tileset_grid[x_i].append(sprite)

            sprite_frame: SpriteFrameDict = {
                'animations': [],
                'name': image_name,
            }

            csv_path: str = os.path.join(source_directory, '%s.csv' % os.path.basename(image_name))

            if os.path.exists(csv_path):
                # Collect animation definitions if .csv present

                print('Reading animations from "%s"' % csv_path)

                for sprite in tileset_sprites:
                    sprite['remove'] = True

                with open(csv_path) as f:
                    lines: List[List[str]] = list(csv.reader(f, delimiter=';'))[1:]

                for line in lines:
                    line = [cell.strip() for cell in line]

                    animation_sprites: List[SpriteDict] = []

                    x0: int = int(line[1])
                    y0: int = int(line[2])
                    cx: int = int(line[3])
                    cy: int = int(line[4])

                    for y_i in range(y0, y0 + cy):
                        for x_i in range(x0, x0 + cx):
                            sprite = tileset_grid[x_i][y_i]
                            sprite['remove'] = False

                            animation_sprites.append(sprite)

                    sprite_frame['animations'].append(cast(AnimationDict, {
                        'framerate': int(line[5]),
                        'loop': line[6].lower().strip() != 'false',
                        'name': '%s:%s' % (image_name, line[0]),
                        'sprites': animation_sprites,
                    }))

                    print('-> Found animation "%s"' % line[0])

                    for sprite in animation_sprites:
                        sprite['animated'] = True
            elif not groups[4] is None or not args.default_framerate is None:
                # Default animation from filename

                sprite_frame['animations'].append(cast(AnimationDict, {
                    'framerate': args.default_framerate if groups[4] is None else int(groups[4]),
                    'loop': groups[5] is not None,
                    'name': '%s:default' % image_name,
                    'sprites': tileset_sprites,
                }))

                for sprite in tileset_sprites:
                    sprite['animated'] = True

            else:
                # Not an animation, treat as multiple sprites

                continue

            sprite_frames.append(sprite_frame)

    # ----------------------------------------------------------------------------------------------
    # Filter out any sprites marked for removal (due to .csv animations)
    # ----------------------------------------------------------------------------------------------

    sprites = list(filter(lambda sprite:
        not 'remove' in sprite or not sprite['remove'], sprites))

    if len(sprites) == 0:
        sys.exit('\nNo sprites found')

    # ----------------------------------------------------------------------------------------------
    # Export each sprite as its own image
    # ----------------------------------------------------------------------------------------------

    if not args.image_directory is None:
        print('\nSaving sprite images in "%s"' % args.image_directory)

        for sprite in sprites:
            image_path = os.path.join(args.image_directory, '%s.png' % sprite['name'])
            image_directory: str = os.path.dirname(image_path)

            os.makedirs(image_directory, exist_ok=True)

            sprite['image'].save(image_path)

    # ----------------------------------------------------------------------------------------------
    # Trimming
    # ----------------------------------------------------------------------------------------------

    if not args.disable_trimming:
        print('\nTrimming sprites...')

        trimmed_count: int = 0
        trimmed_pixels: int = 0

        for sprite in sprites:
            w, h = sprite['image'].size

            bbox: Optional[Tuple[int, int, int, int]] = sprite['image'].getbbox()
            if bbox is None:
                bbox = (0, 0, 1, 1)

            if bbox != (0, 0, w, h):
                sprite['trimmed'] = True
                sprite['image'] = sprite['image'].crop(bbox)
                sprite['margin'] = {
                    'x': bbox[0],
                    'y': bbox[1],
                    'w': w - (bbox[2] - bbox[0]),
                    'h': h - (bbox[3] - bbox[1]),
                }
                trimmed_count += 1
                trimmed_pixels += (w * h) - (sprite['image'].size[0] * sprite['image'].size[1])

        print('Trimmed %i sprites for %i pixels' % (trimmed_count, trimmed_pixels))

    # ----------------------------------------------------------------------------------------------
    # Duplicate sprite marking
    # ----------------------------------------------------------------------------------------------

    if not args.disable_duplicate_removal:
        print('\nChecking for duplicate sprites...')

        duplicates: int = 0

        for i, sprite in enumerate(sprites):
            if sprite['duplicate'] is not None:
                continue

            data: List[Tuple[int, int, int, int]] = list(sprite['image'].getdata())

            for other in sprites[i + 1:]:
                if other['duplicate'] is not None:
                    continue

                other_data = list(other['image'].getdata())
                if len(data) == len(other_data) and data == other_data:
                    other['duplicate'] = sprite
                    duplicates += 1

        print('Found %i duplicate sprites' % duplicates)

    # ----------------------------------------------------------------------------------------------
    # Pack all sprites into one or more atlases via rectpack
    # ----------------------------------------------------------------------------------------------

    print('\nPacking %i sprites...' % len(sprites))

    bin_size: int = 32
    bin_count: int = 1
    max_side: int = args.max_spritesheet_size
    padding: int = args.sprite_padding

    while True:
        packer: PackerBFF = newPacker(rotation=False)
        for _ in range(bin_count):
            packer.add_bin(bin_size, bin_size)

        non_duplicate_count: int = 0

        for sprite in sprites:
            if not sprite['duplicate'] is None:
                continue
            non_duplicate_count += 1

            w, h = sprite['image'].size

            if w + padding * 2 > max_side or h + padding * 2 > max_side:
                sys.exit('Sprite "%s" is too large' % sprite["name"])

            packer.add_rect(w + padding * 2, h + padding * 2, sprite)

        packer.pack()

        if len(packer) > 0 and len(packer.rect_list()) == non_duplicate_count:
            break

        if bin_size * 2 <= max_side:
            bin_size *= 2
        else:
            bin_count += 1

    print('Packed %i non-duplicate sprites (out of %i total) into %i spritesheets of size %ix%i\n'
        % (non_duplicate_count, len(sprites), bin_count, bin_size, bin_size))

    # ----------------------------------------------------------------------------------------------
    # Write out each packed atlas: PNG + JSON + Godot .tres files
    # ----------------------------------------------------------------------------------------------

    for b_i in range(bin_count):
        path_prefix: str = '%s%s' % (args.spritesheet_path, '' if bin_count == 1 else '_%i' % b_i)
        png_path: str = '%s.png' % path_prefix

        # Create an animation info and animations dictionary
        animation_info: Dict[str, AtlasAnimationDict] = {}
        animations: Dict[str, List[str]] = {}

        for sprite_frame in sprite_frames:
            for animation in sprite_frame['animations']:
                animations[animation['name']] = [sprite['name'] for sprite in animation['sprites']]
                animation_info[animation['name']] = {
                    'loop': animation['loop'],
                    'framerate': animation['framerate']
                }

        # Create blank atlas image
        atlas_image: Image.Image = Image.new('RGBA', (bin_size, bin_size), (0, 0, 0, 0))
        atlas_data: AtlasDict = {
            'animations': animations,
            'frames': {},
            'meta': {
                'animation_info': animation_info,
                'app': 'Godot Universal SpritePacker',
                'format': 'RGBA8888',
                'image': os.path.basename('%s.png' % path_prefix),
                'scale': 1,
                'size': { 'w': bin_size, 'h': bin_size },
                'version': __version__,
            },
        }

        bin_sprites: List[SpriteDict] = []

        rect: RectTuple
        for rect in packer[b_i].rect_list():
            x, y, w, h, sprite = rect

            bin_sprites.append(sprite)

            sw, sh = sprite['image'].size

            sprite['resource_path'] = \
                args.godot_resource_directory.strip('/') + '/' + os.path.basename(png_path)
            sprite['frame'] = { 'x': x + padding, 'y': y + padding, 'w': sw, 'h': sh }

            atlas_image.paste(sprite['image'], (x + padding, y + padding))

        # Build JSON frame entries
        for sprite in sprites:
            if not sprite in bin_sprites and not sprite['duplicate'] in bin_sprites:
                continue

            if not sprite['duplicate'] is None:
                sprite['resource_path'] = sprite['duplicate']['resource_path']
                sprite['frame'] = sprite['duplicate']['frame']

            sw, sh = sprite['image'].size

            margin: RectDict = sprite['margin']

            ow: int = sw + margin['w']
            oh: int = sh + margin['h']

            atlas_data['frames'][sprite['name']] = {
                'frame': sprite['frame'],
                'rotated': False,
                'sourceSize': { 'w': ow, 'h': oh },
                'spriteSourceSize': { 'x': margin['x'], 'y': margin['y'], 'w': sw, 'h': sh },
                'trimmed': sprite['trimmed'],
            }

            # Save a standalone AtlasTexture for Godot
            if not args.godot_sprites_directory is None and not sprite['animated']:
                tres_path: str = os.path.join(
                    args.godot_sprites_directory,
                    '%s.tres' % sprite['name']
                )
                tres_directory: str = os.path.dirname(tres_path)

                os.makedirs(tres_directory, exist_ok=True)

                resource_path: str = sprite['resource_path']
                frame: RectDict = sprite['frame']

                with open(tres_path, 'w') as f:
                    f.write('''[gd_resource type="AtlasTexture" format=2]

[ext_resource path="%s" type="Texture" id=1]

[resource]
atlas = ExtResource(1)
region = Rect2(%i, %i, %i, %i)
margin = Rect2(%i, %i, %i, %i)''' % (
                        resource_path,
                        frame['x'], frame['y'], frame['w'], frame['h'],
                        margin['x'], margin['y'], margin['w'], margin['h']
                    ))

        atlas_image.save(png_path)

        if args.save_json:
            with open('%s.json' % path_prefix, 'w', encoding='utf-8') as f:
                json.dump(atlas_data, f, indent=4, sort_keys=True)

        print('Spritesheet %i created at "%s.png"' % (b_i, path_prefix))

    # ----------------------------------------------------------------------------------------------
    # Save Godot SpriteFrames resources
    # ----------------------------------------------------------------------------------------------

    if not args.godot_sprites_directory is None:
        print('\nCreating Godot sprite frames in "%s"' % args.godot_sprites_directory)

        for sprite_frame in sprite_frames:
            tres_path = os.path.join(args.godot_sprites_directory, f'{sprite_frame["name"]}.tres')
            tres_directory = os.path.dirname(tres_path)

            os.makedirs(tres_directory, exist_ok=True)

            sprite_frames_string: str = '[gd_resource type="SpriteFrames" format=3]\n\n'

            resource_paths: List[str] = []
            for animation in sprite_frame['animations']:
                for sprite in animation['sprites']:
                    if not sprite['resource_path'] in resource_paths:
                        resource_paths.append(sprite['resource_path'])
                        sprite_frames_string += '[ext_resource path="%s" type="Texture" id=%i]\n' %\
                            (sprite['resource_path'], len(resource_paths))

            sprite_frames_string += '\n'

            sub_id: int = 1

            animation_strings: List[str] = []

            for animation in sprite_frame['animations']:
                frame_strings: List[str] = []

                for sprite in animation['sprites']:
                    frame = sprite['frame']
                    margin = sprite['margin']

                    resource_id = resource_paths.index(sprite['resource_path']) + 1

                    sprite_frames_string += '''[sub_resource type="AtlasTexture" id=%i]
atlas = ExtResource(%i)
region = Rect2(%i, %i, %i, %i)
margin = Rect2(%i, %i, %i, %i)

''' % (sub_id, resource_id, frame['x'], frame['y'], frame['w'], frame['h'],
                        margin['x'], margin['y'], margin['w'], margin['h'])

                    frame_strings.append('{"duration": 1.0, "texture": SubResource(%i)}' % sub_id)

                    sub_id += 1

                animation_strings.append('''{
    "frames": [
        %s
    ],
    "loop": %s,
    "name": &"%s",
    "speed": %.1f
}''' % (',\n        '.join(frame_strings),
                    str(animation['loop']).lower(), animation['name'], animation['framerate']))

            sprite_frames_string += '''[resource]
animations = [%s]
    ''' % ', '.join(animation_strings)

            with open(tres_path, 'w') as f:
                f.write(sprite_frames_string)

    print('\nCompleted\n')

if __name__ == '__main__':
    main()
