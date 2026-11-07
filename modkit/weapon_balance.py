"""Build MIGI 3 additive weapon overrides from CS:GO 1.35.4.4 stats."""
from __future__ import annotations
import json
import hashlib
from collections import OrderedDict
from pathlib import Path

from . import kv
from .sources import validate_2016, VERSION, DATE

# CS:GO econ IDs, not engine weapon numbers. Stable through 2016 and legacy.
# These are matched by human name rather than guessed from string order.
IDS = {
    'Desert Eagle':1, 'Dual Berettas':2, 'Five-SeveN':3, 'Glock-18':4,
    'AK-47':7, 'AUG':8, 'AWP':9, 'FAMAS':10, 'G3SG1':11,
    'Galil AR':13, 'M249':14, 'M4A4':16, 'MAC-10':17, 'P90':19,
    'UMP-45':24, 'XM1014':25, 'PP-Bizon':26, 'MAG-7':27, 'Negev':28,
    'Sawed-Off':29, 'Tec-9':30, 'P2000':32, 'MP7':33, 'MP9':34,
    'Nova':35, 'P250':36, 'SCAR-20':38, 'SG 553':39, 'SSG 08':40,
    'M4A1-S':60, 'USP-S':61, 'CZ75-Auto':63, 'R8 Revolver':64,
}

# Source data keys -> Source 1 items_game attributes. Exclude any uncertain
# engine flags and cosmetic paths. MIGI expects raw numeric strings here.
KEYS = {
    'price':'in game price',
    'max_player_speed':'max player speed',
    'max_player_speed_alt':'max player speed alt',
    'flinch_velocity_modifier_large':'flinch velocity modifier large',
    'flinch_velocity_modifier_small':'flinch velocity modifier small',
    'penetration':'penetration', 'damage':'damage', 'range':'range',
    'range_modifier':'range modifier', 'armor_ratio':'armor ratio',
    'clip_size':'primary clip size', 'cycle_time':'cycletime',
    'cycle_time_alt':'cycletime alt', 'bullets':'bullets',
    'spread':'spread', 'spread_alt':'spread alt',
    'recoil_seed':'recoil seed',
    'recovery_time_crouch':'recovery time crouch',
    'recovery_time_stand':'recovery time stand',
    'recoil_angle':'recoil angle',
    'recoil_angle_variance':'recoil angle variance',
    'recoil_angle_alt':'recoil angle alt',
    'recoil_angle_variance_alt':'recoil angle variance alt',
    'recoil_magnitude':'recoil magnitude',
    'recoil_magnitude_variance':'recoil magnitude variance',
    'recoil_magnitude_alt':'recoil magnitude alt',
    'recoil_magnitude_variance_alt':'recoil magnitude variance alt',
    'inaccuracy_crouch':'inaccuracy crouch',
    'inaccuracy_stand':'inaccuracy stand',
    'inaccuracy_jump':'inaccuracy jump',
    'inaccuracy_land':'inaccuracy land',
    'inaccuracy_ladder':'inaccuracy ladder',
    'inaccuracy_fire':'inaccuracy fire',
    'inaccuracy_move':'inaccuracy move',
    'inaccuracy_crouch_alt':'inaccuracy crouch alt',
    'inaccuracy_stand_alt':'inaccuracy stand alt',
    'inaccuracy_jump_alt':'inaccuracy jump alt',
    'inaccuracy_land_alt':'inaccuracy land alt',
    'inaccuracy_ladder_alt':'inaccuracy ladder alt',
    'inaccuracy_fire_alt':'inaccuracy fire alt',
    'inaccuracy_move_alt':'inaccuracy move alt',
}


def _number(value):
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, '.8g')
    return str(value)


def create_2016_addon(old_path: Path, out_dir: Path, current_path: Path | None = None):
    """Create an additive MIGI item patch, plus a readable source audit.

    NOTE: current_path is deliberately not used for a diff. Items_game schemas
    are *not* complete weapon-stat sources, so comparison against them would be
    misleading; all sourced 2016 stat fields are written explicitly.
    """
    source_audit = validate_2016(old_path)
    source = json.loads(Path(old_path).read_text(encoding='utf-8-sig'))
    generated = OrderedDict()
    diagnostics = OrderedDict()
    missing = []
    for weapon in sorted(source['weapons'], key=lambda w: w['name']):
        name = weapon['name']
        item_id = IDS.get(name)
        if item_id is None:
            missing.append(name)
            continue
        attrs = OrderedDict((dest, _number(weapon[key])) for key, dest in KEYS.items()
                            if key in weapon and isinstance(weapon[key], (int, float, bool)))
        if isinstance(weapon.get('full_auto'), bool):
            attrs['is full auto'] = _number(weapon['full_auto'])
        if len(attrs) < 7 or 'damage' not in attrs:
            missing.append(name)
            continue
        generated[str(item_id)] = {'attributes': attrs}
        diagnostics[name] = {'item_id': str(item_id), 'attributes': attrs,
                             'original_stat_fields': len(weapon)}
    if len(generated) < (15 if source.get('scope') == 'verified-subset' else 27):
        raise ValueError(f'Only {len(generated)} mapped weapons in source. Missing mappings: {missing}')
    root = Path(out_dir)
    addon = root / 'm_wubugo_2016'
    scripts = addon / 'scripts' / 'items'
    scripts.mkdir(parents=True, exist_ok=True)
    output = scripts / 'items_game_wubugo_2016.txt'
    output.write_text(kv.dump({'items_game': {'items': generated}}), encoding='utf-8')
    (addon / 'addon.json').write_text(json.dumps({
        'name':'wubuGO — 2016 Weapon Balance', 'author':'wubuGO',
        'replacement':'CS:GO 1.35.4.4 verified source fields (offline/private)',
    }, indent=2), encoding='utf-8')
    (addon / 'README.txt').write_text('MIGI 3 additive item override. In MIGI click Build / Update Build.\nUse -insecure, offline/private only. Fields not present in this source stay at game defaults. Weapon physics depends on server and binaries.\n', encoding='utf-8')
    report = root / 'weapon_report.json'
    report.write_text(json.dumps({
        'source':str(old_path), 'source_sha256': hashlib.sha256(Path(old_path).read_bytes()).hexdigest(), 'source_version':VERSION, 'snapshot_date':DATE, 'source_scope':source.get('scope','complete'),
        'source_provenance_verified': source_audit['provenance_verified'],
        'in_game_verified': False,
        'missing_weapons': sorted(set(IDS) - set(diagnostics)),
        'missing_fields_by_weapon': {name: sorted(set(KEYS) - set(next(w for w in source['weapons'] if w['name'] == name))) for name in diagnostics},
        'weapons':diagnostics, 'unmapped':missing, 'source_weapon_count':len(source['weapons']),
        'limitations':'MIGI can override supported item attributes but cannot restore 2016 binary gameplay code or network server logic.',
    }, indent=2), encoding='utf-8')
    return addon, report, len(generated)


def generate(old_path: Path, current_path: Path, out_dir: Path):
    return create_2016_addon(old_path, out_dir, current_path)
