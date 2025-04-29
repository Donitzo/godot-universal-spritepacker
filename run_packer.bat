@echo off

python "godot_universal_spritepacker.py"^
    --source_directory "./test_sprites"^
    --spritesheet_path "./godot/textures/spritesheet"^
    --godot_resource_directory "res://textures"^
    --godot_sprites_directory "./godot/sprites"^
    --image_directory "./split_sprites"^
    --max_spritesheet_size 64

pause
