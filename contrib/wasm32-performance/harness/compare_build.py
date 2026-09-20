#!/usr/bin/env python3
"""Build the same-host Silesia comparison: LZ4, Zstd, and optionally zlib."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emcc', help='Emscripten compiler path')
    parser.add_argument('--without-zlib', action='store_true')
    args = parser.parse_args()
    config_path = ROOT / 'local/config.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    emcc = args.emcc or config.get('emcc') or 'emcc'
    env = dict(os.environ)
    for key, name in [('EM_CONFIG', 'emconfig.py'), ('EM_CACHE', 'em-cache')]:
        path = ROOT / 'local' / name
        if path.exists():
            env[key] = str(path)
    subprocess.run([sys.executable, str(ROOT / 'harness/silesia.py'), '--emcc', emcc], env=env, check=True)
    lz4 = json.loads((ROOT / 'results/silesia-build.json').read_text())
    metadata = dict(compiler=lz4['compiler'], variants=[])
    for variant in ['stock', 'patched']:
        metadata['variants'].append(dict(id='lz4-' + variant, family='lz4', variant=variant,
            version='1.10.0-dev', base=lz4['base'], wasm=f'local/build/silesia-{variant}.wasm',
            levels=[dict(id='default', operation=1), dict(id='hc9', operation=2)], **lz4['variants'][variant]))

    build = ROOT / 'local/build'
    # Vanilla upstream release only. Never read the sibling experimental Zstd checkout.
    version = '1.5.7'
    url = f'https://github.com/facebook/zstd/releases/download/v{version}/zstd-{version}.tar.gz'
    expected = 'eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3'
    archive = build / ('zstd-' + version + '.tar.gz')
    if archive.exists():
        data = archive.read_bytes()
    else:
        with urlopen(url, timeout=60) as response:
            data = response.read()
    if sha256(data) != expected:
        raise ValueError('Zstd official release checksum mismatch')
    archive.write_bytes(data)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(build, filter='data')
    source = build / ('zstd-' + version)
    assert not (source / 'lib/common/sequence_bitstream.h').exists()
    amalgamation = build / 'compare-zstd-vanilla.c'
    single = source / 'build/single_file_libs'
    subprocess.run([sys.executable, str(single / 'combine.py'), '-r', str(source / 'lib'),
                    '-x', 'legacy/zstd_legacy.h', '-o', str(amalgamation), str(single / 'zstd-in.c')],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = build / 'compare-zstd-vanilla.wasm'
    cmd = [emcc, '-O3', '-DNDEBUG', '-std=c90', '-DCODEC=2', str(ROOT / 'harness/compare.c'),
           '-I' + str(source / 'lib'), str(amalgamation), *link_flags(), '-o', str(output)]
    subprocess.run(cmd, env=env, check=True)
    metadata['variants'].append(dict(id='zstd', family='zstd', variant='stock', vanilla=True, version=version,
        archiveURL=url, archiveSHA256=expected, wasm=str(output.relative_to(ROOT)), command=cmd,
        amalgamationSHA256=sha256(amalgamation.read_bytes()), wasmSHA256=sha256(output.read_bytes()),
        sourceSHA256={str(p.relative_to(source)): sha256(p.read_bytes())
            for p in sorted((source / 'lib').rglob('*')) if p.is_file() and p.suffix in ('.c', '.h')},
        levels=[dict(id='1', operation=1), dict(id='3', operation=2), dict(id='6', operation=4)]))
    print('Built', output.name, flush=True)

    if not args.without_zlib:
        # Same pinned release and upstream archive checksum as Emscripten 4.0.6's zlib port.
        version = '1.3.1'
        expected = '8c9642495bafd6fad4ab9fb67f09b268c69ff9af0f4f20cf15dfc18852ff1f312bd8ca41de761b3f8d8e90e77d79f2ccacd3d4c5b19e475ecf09d021fdfe9088'
        url = f'https://github.com/madler/zlib/archive/refs/tags/v{version}.tar.gz'
        archive = build / ('zlib-' + version + '.tar.gz')
        if archive.exists():
            data = archive.read_bytes()
        else:
            with urlopen(url, timeout=60) as response:
                data = response.read()
        if hashlib.sha512(data).hexdigest() != expected:
            raise ValueError('zlib archive checksum mismatch')
        archive.write_bytes(data)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(build, filter='data')
        source = build / ('zlib-' + version)
        names = 'adler32 compress crc32 deflate infback inffast inflate inftrees trees uncompr zutil'.split()
        output = build / 'compare-zlib.wasm'
        cmd = [emcc, '-O3', '-DNDEBUG', '-std=c90', '-DCODEC=3', str(ROOT / 'harness/compare.c'),
               '-I' + str(source), *[str(source / (name + '.c')) for name in names],
               *link_flags(), '-o', str(output)]
        subprocess.run(cmd, env=env, check=True)
        metadata['variants'].append(dict(id='zlib', family='zlib', variant='stock', vanilla=True, version=version,
            wasm=str(output.relative_to(ROOT)), command=cmd, archiveURL=url, archiveSHA512=expected,
            wasmSHA256=sha256(output.read_bytes()), levels=[dict(id='1', operation=1), dict(id='6', operation=2)]))
        print('Built', output.name, flush=True)
    metadata['harnessSHA256'] = {p.name: sha256(p.read_bytes()) for p in
        [ROOT / 'harness/compare.c', ROOT / 'harness/compare.mjs', ROOT / 'harness/silesia.c']}
    (ROOT / 'results/compare-build.json').write_text(json.dumps(metadata, indent=2) + '\n')


def link_flags():
    return ['--no-entry', '-sSTANDALONE_WASM=1', '-sFILESYSTEM=0', '-sINITIAL_MEMORY=536870912',
            '-sSTACK_SIZE=1048576', '-sEXPORTED_FUNCTIONS=' + json.dumps(['_bench', '_bound', '_malloc', '_free'])]


if __name__ == '__main__':
    main()
