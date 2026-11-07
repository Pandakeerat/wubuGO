"""Native regression for the external-child loader boundary; never uses game files."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
from modkit.external_process import (run_external, get_dll_directory, set_dll_directory)


def verify_external_loader():
    if sys.platform == 'win32':
        supplied = os.environ.get('WUBUGO_LOADER_PROBE_DIR')
        if not supplied:
            return {'loader_isolation_verified': False, 'note': 'Native CI fixture not supplied'}
        root = Path(supplied).resolve()
        probe = root/'probe/loader_probe.exe'
        good, bad = root/'good', root/'bad'
        if not all(p.is_file() for p in (probe,good/'external_fixture.dll',bad/'external_fixture.dll')):
            raise ValueError('Native DLL regression fixture is incomplete')
        previous = get_dll_directory()
        try:
            set_dll_directory(str(bad))
            # Control: inherited SetDllDirectory must select the wrong DLL first.
            child_env = dict(os.environ, PATH=str(good) + ';' + os.environ.get('PATH',''))
            control = subprocess.run([str(probe)],cwd=root,env=child_env,capture_output=True,text=True,check=True,timeout=15)
            clean = run_external([str(probe)],cwd=root,env=child_env,capture_output=True,text=True,check=True,timeout=15)
            restored = get_dll_directory() == str(bad)
            if control.stdout.strip() != '13' or clean.stdout.strip() != '42' or not restored:
                raise ValueError('Windows external-DLL isolation regression failed')
        finally:
            set_dll_directory(previous)
        if get_dll_directory() != previous:
            raise ValueError('The manager DLL search directory was not restored')
        return {'loader_isolation_verified': True, 'control_value':13,'external_value':42,
                'parent_directory_restored':True,'game_files_used':False}
    original = os.environ.get('LD_LIBRARY_PATH')
    expected = os.environ.get('LD_LIBRARY_PATH_ORIG','') if getattr(sys,'frozen',False) else (original or '')
    child = run_external(['/bin/sh','-c','printf "%s" "${LD_LIBRARY_PATH-}"'],
                         capture_output=True,text=True,check=True,timeout=15)
    if child.stdout != expected or os.environ.get('LD_LIBRARY_PATH') != original:
        raise ValueError('External library-path isolation regression failed')
    return {'loader_isolation_verified':True,'library_path_restored':True,
            'parent_environment_unchanged':True,'game_files_used':False}
