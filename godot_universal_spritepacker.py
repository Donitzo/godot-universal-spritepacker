__version__ = '0.5.0'
__author__  = 'Donitz'
__license__ = 'MIT'
__repository__ = 'https://github.com/Donitzo/godot_universal_spritepacker'

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from PIL import Image
from rectpack import newPacker
from xml.etree import ElementTree as ET

class UnsupportedVersion(Exception):
    pass

MIN_VERSION, VERSION_LESS_THAN = (3, 8), (4, 0)
if sys.version_info < MIN_VERSION or sys.version_info >= VERSION_LESS_THAN:
    raise UnsupportedVersion('requires Python %s,<%s' %
        ('.'.join(map(str, MIN_VERSION)), '.'.join(map(str, VERSION_LESS_THAN))))

parser = argparse.ArgumentParser(description=
    'Godot Universal SpritePacker — split, pack, and convert spritesheets' +
    ' or SVGs into optimized atlases and SpriteFrames for Godot or other engines.')
parser.add_argument('--source_directory', required=True,
    help='Directory containing source images, SVGs, tilesets or nested directories to be split and packed.')
parser.add_argument('--spritesheet_path', required=True,
    help='Path (without extension) where the final packed spritesheet will be saved.')
parser.add_argument('--image_directory',
    help='Optional directory in which to export individual sprite images before packing.')
parser.add_argument('--godot_sprites_directory',
    help='If set, outputs Godot AtlasTextures and SpriteFrames compatible with Godot 4 to this directory.')
parser.add_argument('--godot_resource_directory', default='res://textures/',
    help='Godot resource directory containing spritesheet images. Default is "res://textures/"')
parser.add_argument('--inkscape_path', default='C:/Program Files/Inkscape/bin/inkscape',
    help='Path to the Inkscape executable. Used for extracting layers from SVG files.')
parser.add_argument('--max_spritesheet_size', type=int, default=4096,
    help='Maximum width or height (in pixels) for the generated spritesheet. Default is 4096.')
args = parser.parse_args()

print('Godot Universal SpritePacker %s\n' % __version__)

spritesheet_dir = os.path.dirname(args.spritesheet_path)
if spritesheet_dir != '':
    os.makedirs(spritesheet_dir, exist_ok=True)

sprites = []
sprite_frames = []

for root, dirs, filenames in os.walk(args.source_directory):
    for filename in filenames:
        source_path = os.path.join(root, filename)
        source_directory = os.path.dirname(source_path)
        rel_path = os.path.relpath(source_path, args.source_directory)
        prefix, extension = os.path.splitext(rel_path)

        name = prefix.replace('\\', '/')
        if name.startswith('./'):
            name = name[2:]

        if extension.lower() == '.svg':
            print('Splitting vector file "%s"' % source_path)

            tree = ET.parse(source_path)
            layers = tree.findall("./{http://www.w3.org/2000/svg}g[@{http://www.inkscape.org/namespaces/inkscape}groupmode='layer']")

            for layer in layers:
                layer_id = layer.attrib['id']
                label = layer.attrib['{http://www.inkscape.org/namespaces/inkscape}label']

                print('-> Exporting layer "%s"' % label)

                image_path = os.path.join(tempfile.gettempdir(),
                    'gus_%s.png' % os.urandom(12).hex())

                result = subprocess.run([
                    args.inkscape_path,
                    source_path,
                    '--export-area-drawing',
                    '--export-type=png',
                    '--export-id-only',
                    '--export-id=%s' % layer_id,
                    '--export-filename=%s' % image_path,
                ])

                if result.returncode != 0:
                    print('Error converting sprite using Inkscape. Skipping vector conversion.')
                    continue

                for attempt in range(10):
                    if os.path.exists(image_path):
                        sprites.append({
                            'name': '%s/%s' % (name, re.sub('[^a-zA-Z0-9_ -]+', '', label)),
                            'image': Image.open(image_path).convert('RGBA'),
                            'animated': False,
                        })

                        break

                    if attempt == 9:
                        sys.exit('Error exporting layer')
                    else:
                        time.sleep(1)

                while os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except OSError:
                        time.sleep(1)

                        print('Failed to delete temporary file')

            continue

        if extension.lower() == '.csv':
            continue

        if not extension.lower() in ['.png', '.bmp', '.jpg', '.jpeg']:
            print('Ignoring file "%s"' % source_path)

            continue

        match = re.search(r'^(.*?)__(\d+)x(\d+)(?:p(\d+))?(?:fps(\d+)(loop)?)?$', name)

        if not match:
            if '__' in name:
                sys.exit('Invalid image name "%s"' % filename)

            print('Using single image "%s"' % source_path)

            sprites.append({
                'name': name,
                'image': Image.open(source_path).convert('RGBA'),
                'animated': False,
            })

            continue

        print('Splitting tileset "%s"' % source_path)

        groups = match.groups()

        tile_width = int(groups[1])
        tile_height = int(groups[2])

        padding = 0 if groups[3] is None else int(groups[3])

        im = Image.open(source_path).convert('RGBA')

        full_width, full_height = im.size

        start_x = list(range(0, full_width, tile_width + padding))
        start_y = list(range(0, full_height, tile_height + padding))

        tileset_sprites = []
        tileset_grid = [[] for _ in start_x]

        for x_i, x in enumerate(start_x):
            x_s = str(x_i).zfill(len(str(len(start_x) - 1)))

            for y_i, y in enumerate(start_y):
                y_s = str(y_i).zfill(len(str(len(start_y) - 1)))

                sprite = {
                    'name': '%s__%sx%s' % (groups[0], y_s, x_s),
                    'image': im.crop((x, y, x + tile_width, y + tile_height)),
                    'animated': False,
                }

                sprites.append(sprite)
                tileset_sprites.append(sprite)
                tileset_grid[x_i].append(sprite)

        sprite_frame = {
            'name': groups[0],
            'animations': [],
        }

        csv_path = os.path.join(source_directory, '%s.csv' % os.path.basename(groups[0]))

        if os.path.exists(csv_path):
            print('Reading animations from "%s"' % csv_path)

            for sprite in tileset_sprites:
                sprite['remove'] = True

            with open(csv_path) as f:
                lines = list(csv.reader(f, delimiter=';'))[1:]

            for line in lines:
                animation_sprites = []

                x0 = int(line[1])
                y0 = int(line[2])
                cx = int(line[3])
                cy = int(line[4])
                for x_i in range(x0, x0 + cx):
                    for y_i in range(y0, y0 + cy):
                        sprite = tileset_grid[x_i][y_i]
                        sprite['remove'] = False

                        animation_sprites.append(sprite)

                sprite_frame['animations'].append({
                    'name': line[0],
                    'sprites': animation_sprites,
                    'framerate': int(line[5]),
                    'loop': line[6].lower().strip() != 'false',
                })

                for sprite in animation_sprites:
                    sprite['animated'] = True
        elif not groups[4] is None:
            sprite_frame['animations'].append({
                'name': 'default',
                'sprites': tileset_sprites,
                'framerate': int(groups[4]),
                'loop': groups[5] is not None,
            })

            for sprite in tileset_sprites:
                sprite['animated'] = True
        else:
            continue

        sprite_frames.append(sprite_frame)

sprites = list(filter(lambda sprite: not 'remove' in sprite or not sprite['remove'], sprites))

if len(sprites) == 0:
    sys.exit('No sprites found')

if not args.image_directory is None:
    print('\nSaving sprite images in "%s"' % args.image_directory)

    for sprite in sprites:
        image_path = os.path.join(args.image_directory, '%s.png' % sprite['name'])
        image_directory = os.path.dirname(image_path)

        os.makedirs(image_directory, exist_ok=True)

        sprite['image'].save(image_path)

print('\nPacking %i sprites' % len(sprites))

bin_size = 32
bin_count = 1
max_side = args.max_spritesheet_size

while True:
    packer = newPacker(rotation=False)
    for _ in range(bin_count):
        packer.add_bin(bin_size, bin_size)

    for i, sprite in enumerate(sprites):
        w, h = sprite['image'].size

        if w + 2 > max_side or h + 2 > max_side:
            sys.exit('Sprite "%s" is too large' % sprite["name"])

        packer.add_rect(w + 2, h + 2, i)

    packer.pack()

    if len(packer) > 0 and len(packer.rect_list()) == len(sprites):
        break

    if bin_size * 2 <= max_side:
        bin_size *= 2
    else:
        bin_count += 1

print('Sprites packed into spritesheet of size %ix%i\n' % (bin_size, bin_size))

for b_i in range(bin_count):
    path_prefix = '%s%s' % (args.spritesheet_path, '' if bin_count == 1 else '_%i' % b_i)

    png_path = '%s.png' % path_prefix

    spritesheet = Image.new('RGBA', (bin_size, bin_size), (0, 0, 0, 0))

    json_data = { 'frames': [],
        'meta': {
            'app': 'Godot Universal SpritePacker',
            'version': __version__,
            'image': os.path.basename('%s.png' % path_prefix),
            'format': 'RGBA8888',
            'size': { 'w': bin_size, 'h': bin_size },
            'scale': 1
        }
    }

    for rect in packer[b_i].rect_list():
        x, y, w, h, index = rect

        sprite = sprites[index]

        spritesheet.paste(sprite['image'], (x + 1, y + 1))

        size = sprite['image'].size

        resource_path = args.godot_resource_directory.strip('/') + '/' + os.path.basename(png_path)

        sprite['frame'] = { 'x': x + 1, 'y': y + 1, 'w': size[0], 'h': size[1] }
        sprite['resource_path'] = resource_path

        json_data['frames'].append({
            'filename': sprite['name'],
            'frame': sprite['frame'],
            'rotated': False,
            'trimmed': False,
            'spriteSourceSize': { 'x': 0, 'y': 0, 'w': size[0], 'h': size[1] },
            'sourceSize': { 'w': size[0], 'h': size[1] },
        })

        if not args.godot_sprites_directory is None and not sprite['animated']:
            tres_path = os.path.join(args.godot_sprites_directory, '%s.tres' % sprite['name'])
            tres_directory = os.path.dirname(tres_path)
            os.makedirs(tres_directory, exist_ok=True)

            with open(tres_path, 'w') as f:
                f.write('''[gd_resource type="AtlasTexture" format=2]

[ext_resource path="%s" type="Texture" id=1]

[resource]
atlas = ExtResource(1)
region = Rect2(%i, %i, %i, %i)''' % (resource_path, x + 1, y + 1, size[0], size[1]))

    spritesheet.save(png_path)

    with open('%s.json' % path_prefix, 'w') as f:
        json.dump(json_data, f, indent=4, sort_keys=True)

    print('Spritesheet %i created at "%s.png" + "%s.json"' % (b_i, path_prefix, path_prefix))

if not args.godot_sprites_directory is None:
    print('Creating Godot sprite frames in "%s"' % args.godot_sprites_directory)

    for sprite_frame in sprite_frames:
        tres_path = os.path.join(args.godot_sprites_directory, f'{sprite_frame["name"]}.tres')
        tres_directory = os.path.dirname(tres_path)
        os.makedirs(tres_directory, exist_ok=True)

        sprite_frames_string = '[gd_resource type="SpriteFrames" format=3]\n\n'

        resource_paths = []
        for animation in sprite_frame['animations']:
            for sprite in animation['sprites']:
                if not sprite['resource_path'] in resource_paths:
                    resource_paths.append(sprite['resource_path'])
                    sprite_frames_string += '[ext_resource path="%s" type="Texture" id=%i]\n' %\
                        (sprite['resource_path'], len(resource_paths))

        sprite_frames_string += '\n'

        sub_id = 1

        animation_strings = []

        for animation in sprite_frame['animations']:
            frame_strings = []

            for sprite in animation['sprites']:
                name = sprite['name']
                fx, fy = sprite['frame']['x'], sprite['frame']['y']
                fw, fh = sprite['frame']['w'], sprite['frame']['h']

                resource_id = resource_paths.index(sprite['resource_path']) + 1

                sprite_frames_string += '''[sub_resource type="AtlasTexture" id=%i]
atlas = ExtResource(%i)
region = Rect2(%i, %i, %i, %i)

''' % (sub_id, resource_id, fx, fy, fw, fh)

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
