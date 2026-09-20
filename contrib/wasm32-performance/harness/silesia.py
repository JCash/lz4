#!/usr/bin/env python3
"""Fetch verified Silesia inputs and build stock/current wasm32 benchmark modules."""
import argparse
import bz2
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = 'https://sun.aei.polsl.pl/~sdeor/'
# Published uncompressed sizes and MD5 digests from the corpus author's page.
FILES = [
    ('dickens', 10192446, '88334708559f6db57d79096bc0aca07e'),
    ('mozilla', 51220480, 'c7789a2097f1ff944b0c737430a339b3'),
    ('mr', 9970564, '38e623e3093b7bf2003ca4b1bbc19927'),
    ('nci', 33553445, '31f85bc8706f3c921104e7c169e2e2e1'),
    ('ooffice', 6152192, '573c4ae915e36631d8f2dcffb9b9b66d'),
    ('osdb', 10085684, 'e734b0c48e6a982adfb5802da3032ecd'),
    ('reymont', 6627202, 'd8f54d78105079775f32d76dc55fc671'),
    ('samba', 21606400, '154eaea7ea70e89f6339ff0abf4112ca'),
    ('sao', 7251944, '79e95a22e18cd82b7e42bf91b380d30b'),
    ('webster', 41458703, '474931ad907ac27bf962c75ded46c069'),
    ('xml', 5345280, '9b09c0c80104adb8aae910b7d7db003e'),
    ('x-ray', 8474240, '9baec32ad14ec3eff487d254382cb91c'),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emcc', help='Emscripten compiler (defaults to local config or PATH)')
    args = parser.parse_args()
    corpus = ROOT / 'local/silesia'
    build = ROOT / 'local/build'
    corpus.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    (ROOT / 'results').mkdir(exist_ok=True)
    manifest = []
    for name, size, md5 in FILES:
        path = corpus / name
        url = SOURCE + 'corpus/' + name + '.bz2'
        if not path.exists():
            print('Fetching', name, flush=True)
            with urlopen(url, timeout=60) as response:
                data = bz2.decompress(response.read())
        else:
            data = path.read_bytes()
        if len(data) != size or hashlib.md5(data).hexdigest() != md5:
            raise ValueError('Corpus verification failed: ' + name)
        if not path.exists():
            path.write_bytes(data)
        manifest.append(dict(name=name, size=size, md5=md5, sha256=digest(data), url=url))
    (ROOT / 'results/silesia-corpus.json').write_text(json.dumps({
        'source': SOURCE + 'index.php?page=silesia', 'files': manifest,
        'bytes': sum(f['size'] for f in manifest),
    }, indent=2) + '\n')

    base = json.loads((ROOT / 'base.json').read_text())['commit']
    stock = build / 'silesia-stock-source'
    if stock.exists():
        shutil.rmtree(stock)
    stock.mkdir()
    archive = subprocess.check_output(['git', 'archive', base, 'lib'], cwd=REPO)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(stock, filter='data')
    config_path = ROOT / 'local/config.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    emcc = args.emcc or config.get('emcc') or shutil.which('emcc')
    if not emcc:
        parser.error('Pass --emcc or activate an Emscripten SDK')
    env = dict(os.environ)
    for key, name in [('EM_CONFIG', 'emconfig.py'), ('EM_CACHE', 'em-cache')]:
        path = ROOT / 'local' / name
        if path.exists():
            env[key] = str(path)
    metadata = dict(base=base, compiler=subprocess.check_output(
        [emcc, '--version'], env=env, text=True).splitlines()[0], variants={})
    for variant, source in [('stock', stock), ('patched', REPO)]:
        output = build / ('silesia-' + variant + '.wasm')
        cmd = [emcc, '-O3', '-DNDEBUG', '-std=c90',
               str(ROOT / 'harness/silesia.c'), '-I' + str(source / 'lib'),
               str(source / 'lib/lz4.c'), str(source / 'lib/lz4hc.c'),
               '--no-entry', '-sSTANDALONE_WASM=1', '-sFILESYSTEM=0',
               '-sINITIAL_MEMORY=268435456', '-sSTACK_SIZE=1048576',
               '-sEXPORTED_FUNCTIONS=' + json.dumps(['_bench', '_bound', '_malloc', '_free']),
               '-o', str(output)]
        subprocess.run(cmd, env=env, check=True)
        metadata['variants'][variant] = dict(command=cmd, wasmSHA256=digest(output.read_bytes()),
            wasmBytes=output.stat().st_size, sourceSHA256={
                name: digest((source / 'lib' / name).read_bytes())
                for name in ['lz4.c', 'lz4.h', 'lz4hc.c', 'lz4hc.h']})
        print('Built', output.name, flush=True)
    (ROOT / 'results/silesia-build.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
