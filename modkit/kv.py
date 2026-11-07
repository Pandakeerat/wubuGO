"""Small, dependency-free Valve KeyValues 1 reader/writer for local items_game files.

Not intended for every extended conditional or Valve binary KeyValues variant.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

# Quoted strings, unquoted tokens, braces, whitespace/comments (ignored).
_TOK = re.compile(r'''\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"/]+|/(?![/*])''')


class KVError(ValueError):
    pass


def _tokenize(content: str):
    for match in _TOK.finditer(content):
        t = match.group()
        if t.isspace() or t.startswith('//') or t.startswith('/*'):
            continue
        if t.startswith('"'):
            t = t[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        yield t


def parse(content: str) -> dict:
    tokens = list(_tokenize(content.lstrip('\ufeff')))
    i = 0

    def block(in_braces: bool = False):
        nonlocal i
        out = OrderedDict()
        while i < len(tokens):
            key = tokens[i]
            i += 1
            if key == '}':
                if not in_braces:
                    raise KVError('Unexpected closing brace')
                return out
            if key == '{':
                raise KVError('Unexpected opening brace')
            if i >= len(tokens):
                raise KVError(f'Missing value for {key}')
            value = tokens[i]
            i += 1
            if value == '{':
                val = block(True)
            elif value == '}':
                raise KVError(f'Expected a value after {key}')
            else:
                val = value
            # items_game uses unique keys for weapon/item and prefab fields.
            out[key] = val
        if in_braces:
            raise KVError('Missing closing brace')
        return out

    result = block()
    return result


def read(path: Path):
    return parse(Path(path).read_text(encoding='utf-8-sig', errors='replace'))


def dump(data: dict, indent: int = 0) -> str:
    result = []
    def write(section, depth):
        for key, val in section.items():
            prefix = '\t' * depth
            escaped = str(key).replace('\\','\\\\').replace('"','\\"')
            if isinstance(val, dict):
                result.append(f'{prefix}"{escaped}"')
                result.append(f'{prefix}{{')
                write(val, depth + 1)
                result.append(f'{prefix}}}')
            else:
                v = str(val).replace('\\','\\\\').replace('"','\\"')
                result.append(f'{prefix}"{escaped}"\t"{v}"')
    write(data, indent)
    return '\n'.join(result) + '\n'
