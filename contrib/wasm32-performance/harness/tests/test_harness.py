#!/usr/bin/env python3
"""CLI regression tests for validator failures and benchmark report metadata.

Run with Python and Node installed; no Wasm SDK or downloaded corpus is needed.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = Path(__file__).resolve().parent
HARNESS = TESTS.parent


class ValidatorTests(unittest.TestCase):
    def run_validator(self, fault):
        with tempfile.TemporaryDirectory(prefix='lz4-validator-test-') as directory:
            root = Path(directory)
            for name in ['harness', 'results', 'local/corpus/data', 'local/build']:
                (root / name).mkdir(parents=True, exist_ok=True)
            script = root / 'harness/validate.mjs'
            shutil.copyfile(HARNESS / 'validate.mjs', script)
            corpus = root / 'local/corpus'
            (corpus / 'manifest.json').write_text(json.dumps([dict(id='one', size=1)]))
            (corpus / 'validation-manifest.json').write_text('[]')
            (corpus / 'data/one.raw').write_bytes(b'Z')
            (corpus / 'data/one.lz4hc9').write_bytes(b'\x10Z')
            # The preload maps these markers to deterministic fake decoder exports.
            (root / 'local/build/stock.wasm').write_bytes(bytes([0]))
            (root / 'local/build/candidate.wasm').write_bytes(bytes([fault]))
            completed = subprocess.run([
                'node', '--require', str(TESTS / 'mock_decoder.cjs'), str(script),
                'stock', 'candidate',
            ], capture_output=True, text=True, timeout=30)
            result_path = root / 'results/validation.json'
            self.assertTrue(result_path.exists(), completed.stderr)
            return completed, json.loads(result_path.read_text())

    def test_matching_decoders_succeed(self):
        completed, result = self.run_validator(0)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual([], result['differences'])
        self.assertEqual(0, result['errorOffsetDifferences'])

    def test_accepting_malformed_input_fails_after_saving_diagnostics(self):
        completed, result = self.run_validator(1)
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertGreater(len(result['differences']), 0)
        self.assertIn('Validation failed', completed.stderr)

    def test_wrong_decoded_bytes_fail_after_saving_diagnostics(self):
        completed, result = self.run_validator(2)
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertGreater(len(result['differences']), 0)

    def test_error_offset_mismatches_fail_after_saving_diagnostics(self):
        completed, result = self.run_validator(3)
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertEqual([], result['differences'])
        self.assertGreater(result['errorOffsetDifferences'], 0)


def benchmark_fixture():
    variants = []
    results = []
    for name, levels in [('lz4-stock', ['default', 'hc9']),
                         ('lz4-patched', ['default', 'hc9']),
                         ('zstd', ['1', '3', '6']), ('zlib', ['1', '6'])]:
        family = name.split('-')[0]
        variants.append(dict(id=name, family=family, vanilla=family != 'lz4',
            variant='patched' if name.endswith('patched') else 'stock',
            levels=[dict(id=level) for level in levels]))
        for level in levels:
            for direction in ['compress', 'decompress']:
                results.append(dict(id=name, level=level, direction=direction, file='fixture',
                    bytes=1000000, compressed=500000, samples=[dict(ms=1, rounds=1)]))
    results.append(dict(id='lz4-patched', level='memcpy', direction='copy', file='fixture',
        bytes=1000000, compressed=1000000, samples=[dict(ms=1, rounds=1)]))
    return dict(completedFiles=1, sampleCount=1, targetMs=250,
        corpus=dict(files=[dict(name='fixture', size=1000000)], bytes=1000000),
        build=dict(variants=variants, compiler='emcc (Emscripten test toolchain) 5.0.0 (fixture)'),
        userAgent='Chrome/153.0.0.0', results=results)


class ReportTests(unittest.TestCase):
    def run_report(self, raw):
        with tempfile.TemporaryDirectory(prefix='lz4-report-test-') as directory:
            root = Path(directory)
            (root / 'harness').mkdir()
            (root / 'results').mkdir()
            script = root / 'harness/compare_report.py'
            shutil.copyfile(HARNESS / 'compare_report.py', script)
            (root / 'results/fixture.json').write_text(json.dumps(raw))
            completed = subprocess.run([sys.executable, str(script), 'fixture', '--host', 'Test host'],
                capture_output=True, text=True, timeout=30)
            report = root / 'results/CODEC-COMPARISON.md'
            return completed, report.read_text() if report.exists() else None

    def test_captured_compiler_and_timing_are_reported(self):
        raw = benchmark_fixture()
        completed, report = self.run_report(raw)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn('Compiler: `' + raw['build']['compiler'] + '`.', report)
        self.assertNotIn('Emscripten 4.0.6', report.split('## Measurement method')[0].split('| Codec')[0])
        self.assertIn('targeting 250 ms each', report)

    def test_nonstandard_compiler_string_is_preserved(self):
        raw = benchmark_fixture()
        raw['build']['compiler'] = 'Vendor SDK snapshot abcdef'
        completed, report = self.run_report(raw)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn('Compiler: `Vendor SDK snapshot abcdef`.', report)

    def test_missing_compiler_does_not_produce_a_guessed_report(self):
        raw = benchmark_fixture()
        del raw['build']['compiler']
        completed, report = self.run_report(raw)
        self.assertNotEqual(0, completed.returncode)
        self.assertIn('Missing captured compiler metadata', completed.stderr)
        self.assertIsNone(report)


if __name__ == '__main__':
    unittest.main()
