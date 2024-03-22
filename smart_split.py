__version__ = '0.5.1'
__author__  = 'Donitz'
__license__ = 'MIT'
__repository__ = 'https://github.com/Donitzo/smart_splitter'

# Requires the "pillow" and "rectpack" packages
# "pip install pillow rectpack"

# sprite frame csv format:
# name; start_x; start_y; count_x; count_y; fps; loop

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

MIN_VERSION, VERSION_LESS_THAN = (3, 5), (4, 0)
if sys.version_info < MIN_VERSION or sys.version_info >= VERSION_LESS_THAN:
    raise UnsupportedVersion('requires Python %s,<%s' % ('.'.join(map(str, MIN_VERSION)), '.'.join(map(str, VERSION_LESS_THAN))))

parser = argparse.ArgumentParser()
parser.add_argument('source_directory')
parser.add_argument('spritesheet_path')
parser.add_argument('--image_directory')
parser.add_argument('--godot_sprites_directory')
parser.add_argument('--inkscape_path', default='C:/Program Files/Inkscape/bin/inkscape')
parser.add_argument('--max_spritesheet_size', type=int, default=4096)
args = parser.parse_args()

print('Smart Sprite Splitter %s\n' % __version__)

os.makedirs(os.path.dirname(spritesheet_path)), exist_ok=True)

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

                image_path = os.path.join(tempfile.gettempdir(), 'smart_splitter_%s.png' % os.urandom(12).hex())

                result = subprocess.run([args.inkscape_path, source_path, '--export-area-drawing', '--export-type=png',
                    '--export-id-only', '--export-id=%s' % layer_id, '--export-filename=%s' % image_path])

                if result.returncode != 0:
                    sys.exit('Error exporting layer')

                for attempt in range(10):
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as f:
                            sprites.append({
                                'name': '%s/%s' % (name, re.sub('[^a-zA-Z0-9_ -]+', '', label)),
                                'image': Image.open(f).copy(),
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

            with open(source_path, 'rb') as f:
                sprites.append({
                    'name': name,
                    'image': Image.open(f).copy(),
                })

            continue

        print('Splitting tileset "%s"' % source_path)

        groups = match.groups()

        tile_width = int(groups[1])
        tile_height = int(groups[2])

        padding = 0 if groups[3] is None else int(groups[3])

        im = Image.open(source_path)

        full_width, full_height = im.size

        start_x = list(range(0, full_width, tile_width + padding))
        start_y = list(range(0, full_height, tile_height + padding))

        tileset_sprites = []
        tileset_grid = [[] for _ in start_x]

        for x_i, x in enumerate(start_x):
            x_s = str(x_i).zfill(len(str(len(start_x))))

            for y_i, y in enumerate(start_y):
                y_s = str(y_i).zfill(len(str(len(start_y))))

                sprite = {
                    'name': '%s__%sx%s' % (groups[0], y_s, x_s),
                    'image': im.crop((x, y, x + tile_width, y + tile_height)),
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

                for x_i in range(int(line[1]), int(line[3])):
                    for y_i in range(int(line[2]), int(line[4])):
                        sprite = tileset_grid[x_i][y_i]
                        sprite['remove'] = False

                        animation_sprites.append(sprite)

                sprite_frame['animations'].append({
                    'name': line[0],
                    'sprites': animation_sprites,
                    'framerate': args.default_framerate if line[5] is None else int(line[5]),
                    'loop': line[6].lower().strip() != 'false',
                })
        elif not groups[4] is None:
            sprite_frame['animations'].append({
                'name': 'default',
                'sprites': tileset_sprites,
                'framerate': int(groups[4]),
                'loop': groups[5] is not None,
            })
        else:
            continue

        sprite_frames.append(sprite_frame)

sprites = list(filter(lambda sprite: not 'remove' in sprite or not sprite['remove'], sprites))

if len(sprites) == 0:
    sys.exit('No sprites found')

if not args.image_directory is None:
    print('\nSaving images in "%s"' % args.image_directory)

    for sprite in sprites:
        image_path = os.path.join(args.image_directory, '%s.png' % sprite['name'])
        image_directory = os.path.dirname(image_path)

        if not os.path.exists(image_directory):
            os.makedirs(image_directory)

        sprite['image'].save(image_path)

print('\nPacking %i sprites' % len(sprites))

bin_size = 16
bin_count = 1

while True:
    if bin_size >= args.max_spritesheet_size:
        bin_count += 1
    else:
        bin_size *= 2

    packer = newPacker(rotation=False)

    for _ in range(bin_count):
        packer.add_bin(bin_size, bin_size)

    for i, sprite in enumerate(sprites):
        size = sprite['image'].size

        if size[0] + 2 > args.max_spritesheet_size or\
            size[1] + 2 > args.max_spritesheet_size:
            sys.exit('Sprite is too large')

        packer.add_rect(size[0] + 2, size[1] + 2, i)

    packer.pack()

    if len(packer) > 0 and len(packer.rect_list()) == len(sprites):
        break

print('Sprites packed into %i spritesheets of size %ix%i\n' % (bin_count, bin_size, bin_size))

for b_i in range(bin_count):
    path_prefix = '%s%s' % (args.spritesheet_path, '' if bin_count == 1 else '_%i' % b_i)

    png_path = '%s.png' % path_prefix

    spritesheet = Image.new('RGBA', (bin_size, bin_size), (0, 0, 0, 0))

    json_data = { 'frames': [],
        'meta': {
            'app': 'https://github.com/Donitzo/smart_splitter',
            'version': '1.0',
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

        json_data['frames'].append({
            'filename': sprite['name'],
            'frame': { 'x': x + 1, 'y': y + 1, 'w': size[0], 'h': size[1] },
            'rotated': False,
            'trimmed': False,
            'spriteSourceSize': { 'x': 0, 'y': 0, 'w': size[0], 'h': size[1] },
            'sourceSize': { 'w': size[0], 'h': size[1] },
        })

        if not args.godot_sprites_directory is None:
            tres_path = os.path.join(args.godot_sprites_directory, '%s.tres' % sprite['name'])
            tres_directory = os.path.dirname(tres_path)

            os.makedirs(os.path.dirname(tres_directory)), exist_ok=True)

            with open(tres_path, 'w') as f:
                f.write('''[gd_resource type="AtlasTexture" load_steps=2 format=2]

[ext_resource path="res://textures/%s" type="Texture" id=1]

[resource]
atlas = ExtResource( 1 )
region = Rect2( %i, %i, %i, %i )''' % (os.path.basename(png_path), x + 1, y + 1, size[0], size[1]))

    spritesheet.save(png_path)

    with open('%s.json' % path_prefix, 'w') as f:
        json.dump(json_data, f, indent=4, sort_keys=True)

    print('Spritesheet created at "%s.png + .json"' % path_prefix)

if not args.godot_sprites_directory is None:
    print('Creating Godot sprites in "%s"' % args.godot_sprites_directory)

    for sprite_frame in sprite_frames:
        resource_string = ''
        resource_index = 1

        animation_string = '[ {'

        for i, animation in enumerate(sprite_frame['animations']):
            resource_indices = []

            for sprite in animation['sprites']:
                resource_string += '[ext_resource path="./%s.tres" type="Texture" id=%i]\n' % (
                    os.path.basename(sprite['name']), resource_index)
                resource_indices.append(resource_index)
                resource_index += 1

            animation_string += '''
    "frames": [ %s ],
    "loop": %s,
    "name": "%s",
    "speed": %i.0
%s''' % (', '.join(['ExtResource( %i )' % i for i in resource_indices]),
            str(animation['loop']).lower(),
            re.sub('[\W -]', '', animation['name']), animation['framerate'],
            '} ]' if i == len(sprite_frame['animations']) - 1 else '}, {')

        tres_path = os.path.join(args.godot_sprites_directory, '%s.tres' % sprite_frame['name'])
        tres_directory = os.path.dirname(tres_path)

        if not os.path.exists(tres_directory):
            os.makedirs(tres_directory)

        with open(tres_path, 'w') as f:
            f.write('''[gd_resource type="SpriteFrames" load_steps=%i format=2]

%s
[resource]
animations = %s''' % (resource_index, resource_string, animation_string))

print('\nCompleted\n')
