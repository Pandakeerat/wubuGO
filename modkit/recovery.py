"""Conservative rollback for manager-owned files; never delete unknown content."""
from pathlib import Path
import shutil
from .retrokit import game_root, _cfg, _addons, PROFILE, protected_target, ensure_game_stopped


def restore_profile(root):
    root = game_root(root)
    ensure_game_stopped()
    cfg = protected_target(root, _cfg(root))
    backup = protected_target(root, cfg.with_suffix('.cfg.wubugo.bak'))
    if not cfg.is_file() or cfg.read_text(encoding='utf-8') != PROFILE:
        raise ValueError('Profile missing or edited; refusing rollback')
    if backup.is_file():
        backup.replace(cfg)
    else:
        cfg.unlink()
    return cfg


def restore_addon(root, name='m_wubugo_2016'):
    if name not in {'m_wubugo_2016', 'p_wubugo_2016menu'}:
        raise ValueError('Only wubuGO addons can be restored')
    root = game_root(root)
    ensure_game_stopped()
    target = protected_target(root, _addons(root) / name)
    backups = list(target.parent.glob(name + '.wubugo.backup*'))
    def generation(path):
        suffix = path.name.removeprefix(name + '.wubugo.backup')
        return 0 if not suffix else int(suffix.removeprefix('.'))
    backups = [p for p in backups if p.is_dir() and
               (p.name == name+'.wubugo.backup' or p.name.removeprefix(name+'.wubugo.backup.').isdigit())]
    if not backups:
        raise FileNotFoundError('No addon backup available')
    backup = protected_target(root, max(backups, key=generation))
    if any(p.is_symlink() for p in backup.rglob('*')):
        raise ValueError('Backup contains linked files; inspect it before rollback')
    recovery = protected_target(root, target.with_name(name + '.wubugo.disabled'))
    if recovery.exists():
        raise FileExistsError('Keep or move the previous recovery folder first: ' + str(recovery))
    if not target.is_dir():
        raise FileNotFoundError('Installed addon missing; refusing rollback')
    target.rename(recovery)
    try:
        backup.rename(target)
    except OSError:
        recovery.rename(target)
        raise
    return target
