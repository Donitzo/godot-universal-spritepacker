__version__ = '0.2.1'
__author__  = 'Donitz'
__license__ = 'MIT'
__repository__ = 'https://github.com/Donitzo/smart_splitter'

# Requires the "pillow" and "rectpack" packages
# "pip install pillow rectpack"

import argparse
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
parser.add_argument('--inkscape_path', default='C:/Program Files/Inkscape/bin/inkscape')
args = parser.parse_args()

print('Smart Sprite Splitter %s\n' % __version__)

sprites = []

for root, dirs, filenames in os.walk(args.source_directory):
    for filename in filenames:
        source_path = os.path.join(root, filename)
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

        if not extension.lower() in ['.png', '.bmp', '.jpg', '.jpeg']:
            print('Ignoring file "%s"' % source_path)

            continue

        parts = os.path.splitext(filename)[0].split('__')

        if len(parts) > 2:
            sys.exit('Invalid image name "%s"' % filename)
        if len(parts) == 1:
            print('Using single image "%s"' % source_path)

            with open(image_path, 'rb') as f:
                sprites.append({
                    'name': name,
                    'image': Image.open(f).copy(),
                })
        else:
            print('Splitting tileset "%s"' % source_path)

            im = Image.open(source_path)

            full_width, full_height = im.size

            dimensions = list(map(int, re.split(r'[xp]', parts[1])))
            if len(dimensions) == 3:
                tile_width, tile_height, padding = dimensions
            elif len(dimensions) == 2:
                tile_width, tile_height = dimensions
                padding = 0
            else:
                sys.exit('Invalid image name "%s"' % filename)

            start_x = list(range(0, full_width, tile_width + padding))
            start_y = list(range(0, full_height, tile_height + padding))

            for x_i, x in enumerate(start_x):
                x_s = str(x_i).zfill(len(str(len(start_x))))

                for y_i, y in enumerate(start_y):
                    y_s = str(y_i).zfill(len(str(len(start_y))))

                    sprites.append({
                        'name': '%s__%sx%s' % (parts[0], y_s, x_s),
                        'image': im.crop((x, y, x + tile_width, y + tile_height)),
                    })

if len(sprites) == 0:
    sys.exit('No sprites found')

if not args.image_directory is None:
    print('\nSaving images in "%s"' % args.image_directory)

    for sprite in sprites:
        image_path = os.path.join(args.image_directory, '%s.png' % sprite['name'])

        if not os.path.exists(os.path.dirname(image_path)):
            os.makedirs(os.path.dirname(image_path))

            time.sleep(1)

        sprite['image'].save(image_path)

print('\nPacking %i sprites' % len(sprites))

bin_size = 16
while True:
    bin_size *= 2
    if bin_size == 65536:
        sys.exit('Error packing sprites')

    packer = newPacker()
    packer.add_bin(bin_size, bin_size)

    for i, sprite in enumerate(sprites):
        size = sprite['image'].size
        packer.add_rect(size[0] + 2, size[0] + 2, i)

    packer.pack()

    if len(packer) > 0 and len(packer[0]) == len(sprites):
        break

spritesheet = Image.new('RGBA', (bin_size, bin_size), (0, 0, 0, 0))

json_data = { 'frames': [] }

for rect in packer.rect_list():
    b, x, y, w, h, index = rect

    sprite = sprites[index]

    spritesheet.paste(sprite['image'], (x + 1, y + 1))

    size = sprite['image'].size

    json_data['frames'].append({
        'filename': sprite['name'],
        'frame': { 'x': x + 1, 'y': y + 1, 'w': size[0], 'h': size[1]},
        'rotated': False,
        'trimmed': False,
        'spriteSourceSize': { 'x': 0, 'y': 0, 'w': size[0], 'h': size[1]},
        'sourceSize': { 'w': size[0], 'h': size[1] }
    })

spritesheet.save('%s.png' % args.spritesheet_path)

with open('%s.json' % args.spritesheet_path, 'w') as f:
    json.dump(json_data, f, indent=4, sort_keys=True)

print('Spritesheet created at "%s.png + .json"\n' % args.spritesheet_path)
