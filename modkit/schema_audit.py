"""Classify an items_game KeyValues file without claiming it contains weapon tuning."""
from pathlib import Path
from . import kv


def audit(path):
    root = kv.read(Path(path))
    root = root.get('items_game', root)
    if not isinstance(root, dict) or not isinstance(root.get('items'), dict):
        raise ValueError('Missing items_game / items section')
    items = root['items']
    weapons = {entry.get('name'): num for num, entry in items.items()
               if isinstance(entry, dict) and str(entry.get('name','')).startswith('weapon_')}
    text = ' '.join(root.get('prefabs', {})).lower()
    late = [marker for marker in ('paris2023','rio2022','stockh2021','berlin2019','katowice2019') if marker in text]
    return {'filename':str(path), 'total_items':len(items), 'weapon_item_count':len(weapons),
            'post_2016_markers':late,
            'suitable_as_2016_weapon_source':False,
            'notes':['items_game describes item/economy prefabs. It is NOT a complete historic gameplay-stat snapshot.',
                     'A full weapon-1.35.4.4.json download is used for weapon balance instead.']}
