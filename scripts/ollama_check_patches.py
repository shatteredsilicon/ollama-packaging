#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path

PATCH_DEF_RE = re.compile(r'^Patch(\d+):\s+(\S+)')
PATCH_USE_RE = re.compile(r'^%patch(?:\s+(\d+)|(\d+))(?:\s|$)')
SECTION_RE = re.compile(r'^%(prep|build|install|files|changelog|check|clean|pre|post|preun|postun)\b')


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise argparse.ArgumentTypeError(f'Invalid boolean value: {value}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Apply Ollama RPM patches in spec order for sanity checking.')
    parser.add_argument('--spec-file', '--spec_file', dest='spec_file', type=Path, required=True)
    parser.add_argument('--patch-dir', '--patch_dir', dest='patch_dir', type=Path, required=True)
    parser.add_argument('--source-dir', '--source_dir', dest='source_dir', type=Path, required=True)
    parser.add_argument(
        '--without-avx', '--without_avx',
        dest='without_avx',
        type=parse_bool,
        default=False,
        metavar='BOOL',
        help='Evaluate the %prep conditionals as if --without avx was set.',
    )
    return parser.parse_args()


def eval_condition(expr: str, with_avx: bool) -> bool:
    normalized = re.sub(r'\s+', '', expr)
    if normalized == '%{withavx}':
        return with_avx
    if normalized == '!%{withavx}':
        return not with_avx
    raise ValueError(f'Unsupported spec conditional in %prep: {expr}')


def parse_patch_order(spec_file: Path, with_avx: bool) -> list[str]:
    patch_defs: dict[int, str] = {}
    lines = spec_file.read_text().splitlines()

    for line in lines:
        m = PATCH_DEF_RE.match(line.strip())
        if m:
            patch_defs[int(m.group(1))] = m.group(2)

    in_prep = False
    active_stack = [True]
    order: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not in_prep:
            if line == '%prep':
                in_prep = True
            continue

        if SECTION_RE.match(line) and line != '%prep':
            break

        if line.startswith('%if '):
            cond = eval_condition(line[4:].strip(), with_avx)
            active_stack.append(active_stack[-1] and cond)
            continue

        if line == '%else':
            if len(active_stack) < 2:
                raise ValueError('Found %else without matching %if in %prep')
            parent_active = active_stack[-2]
            previous_branch = active_stack[-1]
            active_stack[-1] = parent_active and not previous_branch
            continue

        if line == '%endif':
            if len(active_stack) < 2:
                raise ValueError('Found %endif without matching %if in %prep')
            active_stack.pop()
            continue

        if not active_stack[-1]:
            continue

        m = PATCH_USE_RE.match(line)
        if not m:
            continue

        patch_index = int(m.group(1) or m.group(2))
        if patch_index not in patch_defs:
            raise ValueError(f'Patch{patch_index} used in %prep but not defined in spec')
        order.append(patch_defs[patch_index])

    if len(active_stack) != 1:
        raise ValueError('Unbalanced %if/%endif in %prep')

    return order


def git_apply(source_dir: Path, patch_file: Path, check_only: bool) -> None:
    source_dir = source_dir.resolve()
    patch_file = patch_file.resolve()

    cmd = ['git', '-C', str(source_dir), 'apply']
    if check_only:
        cmd.append('--check')
    cmd.append(str(patch_file))
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()
    with_avx = not args.without_avx

    order = parse_patch_order(args.spec_file, with_avx=with_avx)
    if not order:
        print('No patches found in %prep', file=sys.stderr)
        return 1

    print('Patch order:')
    for patch_name in order:
        patch_file = args.patch_dir / patch_name
        if not patch_file.is_file():
            raise FileNotFoundError(f'Missing patch file: {patch_file}')
        print(f'  - {patch_name}')
        git_apply(args.source_dir, patch_file, check_only=True)
        git_apply(args.source_dir, patch_file, check_only=False)

    print('All patches applied successfully.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
