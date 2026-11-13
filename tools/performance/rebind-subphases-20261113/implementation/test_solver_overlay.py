"""Static source-byte/metadata checks. No GHC, subprocess, locks or runner."""
import ast
import hashlib
import json
import os
from pathlib import Path
import unittest
import fine_profile as F
import mirror

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
SOURCE = Path(os.environ.get('ASTRA_FROZEN_SOURCE', str(PACKAGE.parent / 'source')))
PREVIEW = PACKAGE / 'preview-mirror'
SPEC = F.load_fine_spec()
COARSE = json.loads((PACKAGE / 'coarse-insertion-map.json').read_text())


def sha(raw): return hashlib.sha256(raw).hexdigest()


def transform(text, edits, reverse=False):
    for edit in (reversed(edits) if reverse else edits):
        a, b = (edit['after'], edit['before']) if reverse else (edit['before'], edit['after'])
        if text.count(a) != 1: raise ValueError('anchor count differs')
        text = text.replace(a, b)
    return text


class SolverOverlayTests(unittest.TestCase):
    def test_original_code_and_fixtures_are_unchanged(self):
        manifest = json.loads((PACKAGE / 'REUSE-MANIFEST.json').read_text())
        self.assertEqual(len(manifest['reused_unchanged']), 24)
        for rel, digest in manifest['reused_unchanged'].items():
            with self.subTest(rel=rel): self.assertEqual(sha((HERE / rel).read_bytes()), digest)

    def test_all_python_sources_parse_without_execution(self):
        for path in HERE.glob('*.py'):
            with self.subTest(path=path.name): ast.parse(path.read_text(), filename=path.name)

    def test_exact_unchanged_source_closure_and_fine_inventory(self):
        for key in ['source_commit', 'union', 'emlf_modules', 'generator_modules', 'pins']:
            self.assertEqual(SPEC[key], COARSE[key])
        self.assertEqual([len(SPEC[k]) for k in ['pins', 'union', 'emlf_modules', 'generator_modules']], [97, 95, 94, 60])
        self.assertEqual(sum(map(len, COARSE['edits'].values())), 27)
        self.assertEqual(sum(map(len, SPEC['edits'].values())), 41)
        self.assertEqual(len(SPEC['r16_fine']['sites']), 14)
        self.assertEqual(len(SPEC['r16_fine']['labels']), 13)
        self.assertEqual(len(F.LOCAL_UNIFY_FAMILY), 8)
        self.assertEqual(len(F.REBIND_FAMILY), 4)
        self.assertEqual(len(F.COARSE.LABELS), 24)
        self.assertFalse(F.FINE_LABELS & F.COARSE.LABELS)
        self.assertEqual(sha((PACKAGE / 'coarse-insertion-map.json').read_bytes()), SPEC['r16_fine']['coarse_map_sha256'])

    def test_full_original_mirror_verifier_accepts_static_preview(self):
        verified = mirror.verify_mirror(SOURCE, PREVIEW)
        self.assertEqual(sum(r['occurrences'] for r in verified['files'].values()), 41)

    def test_fine_then_coarse_inverse_restores_every_original_source_byte(self):
        for rel, original_sha in SPEC['pins'].items():
            with self.subTest(rel=rel):
                original = (SOURCE / rel).read_bytes(); self.assertEqual(sha(original), original_sha)
                coarse = transform(original.decode(), COARSE['edits'].get(rel, []))
                fine = (PREVIEW / rel).read_text()
                sites = [s for s in SPEC['r16_fine']['sites'] if s['path'] == rel]
                edits = [dict(before=s['anchor_before'], after=s['anchor_after']) for s in sites]
                self.assertEqual(transform(fine, edits, reverse=True), coarse)
                self.assertEqual(transform(coarse, COARSE['edits'].get(rel, []), reverse=True).encode(), original)
                pins = SPEC['r16_fine']['files'][rel]
                self.assertEqual(sha(coarse.encode()), pins['coarse_sha256'])
                self.assertEqual(sha(fine.encode()), pins['fine_sha256'])
                self.assertEqual(mirror.inverse_bytes(rel, fine.encode()), original)

    def test_unique_anchors_and_exact_source_spans(self):
        for site in SPEC['r16_fine']['sites']:
            with self.subTest(site=site['site_id']):
                rel = site['path']; original = (SOURCE / rel).read_text()
                coarse = transform(original, COARSE['edits'].get(rel, []))
                fine = (PREVIEW / rel).read_text()
                self.assertEqual(coarse.count(site['anchor_before']), 1)
                # A reviewed child prefix can sit inside its parent's anchor.
                # Strip only other fine tokens, retaining this exact own token.
                own = fine
                for other in SPEC['r16_fine']['sites']:
                    if other['label'] != site['label']:
                        own = own.replace(other['inserted_token'], '')
                self.assertEqual(own.count(site['anchor_after']), 1)
                self.assertEqual(site['anchor_after'].replace(site['inserted_token'], '', 1), site['anchor_before'])
                self.assertEqual(site['inserted_token'], '{-# SCC "' + site['label'] + '" #-} ')
                self.assertNotIn('\n', site['inserted_token'])
                slices = []
                for text, span_key in [(coarse, 'coarse_rhs_span'), (fine, 'fine_rhs_span')]:
                    raw = text.encode(); span = site[span_key]
                    for byte_key, position in [('start_byte', 'start'), ('end_byte_exclusive', 'end_exclusive')]:
                        prefix = raw[:span[byte_key]].decode()
                        self.assertEqual([prefix.count('\n') + 1, len(prefix.rsplit('\n', 1)[-1]) + 1], span[position])
                    slices.append(raw[span['start_byte']:span['end_byte_exclusive']])
                    self.assertTrue(raw[span['end_byte_exclusive']:].startswith(site['end_marker'].encode()))
                # Parent RHS slices can contain nested fine SCC prefixes.
                stripped = slices[1]
                for child in SPEC['r16_fine']['sites']:
                    stripped = stripped.replace(child['inserted_token'].encode(), b'')
                self.assertEqual(slices[0], stripped)

    def test_r17_four_token_inverse_restores_exact_r16(self):
        previous = json.loads((PACKAGE / 'r16-insertion-map.json').read_text())
        self.assertEqual(sha((PACKAGE / 'r16-insertion-map.json').read_bytes()),
                         SPEC['r16_fine']['parent_r16_map_sha256'])
        parent = json.loads((PACKAGE / 'r17-insertion-map.json').read_text())
        added = [s for s in parent['r16_fine']['sites'] if s['site_id'].startswith('unify-')]
        self.assertEqual(len(added), 4)
        for rel in SPEC['pins']:
            with self.subTest(rel=rel):
                original = (SOURCE / rel).read_text()
                old = transform(original, previous['edits'].get(rel, []))
                edits = [dict(before=s['anchor_before'], after=s['anchor_after']) for s in added if s['path'] == rel]
                r17 = transform(original, parent['edits'].get(rel, []))
                self.assertEqual(transform(r17, edits, reverse=True), old)

    def test_r21_three_token_inverse_restores_exact_r17_and_preserves_edits(self):
        parent = json.loads((PACKAGE / 'r17-insertion-map.json').read_text())
        self.assertEqual(sha((PACKAGE / 'r17-insertion-map.json').read_bytes()),
                         SPEC['r16_fine']['parent_r17_map_sha256'])
        ids = {'unify-canonicalize', 'unify-rebind-sparse', 'unify-rebind-dense'}
        added = [s for s in SPEC['r16_fine']['sites'] if s['site_id'] in ids]
        self.assertEqual(len(added), 3)
        self.assertEqual(sum(map(len, parent['edits'].values())), 38)
        self.assertEqual(len(parent['r16_fine']['sites']), 11)
        self.assertEqual(len(parent['r16_fine']['labels']), 10)
        for rel in SPEC['pins']:
            with self.subTest(rel=rel):
                original = (SOURCE / rel).read_text()
                old_edits = parent['edits'].get(rel, [])
                self.assertEqual(SPEC['edits'].get(rel, [])[:len(old_edits)], old_edits)
                r17 = transform(original, old_edits)
                edits = [dict(before=s['anchor_before'], after=s['anchor_after']) for s in added if s['path'] == rel]
                self.assertEqual(transform((PREVIEW / rel).read_text(), edits, reverse=True), r17)

    def test_new_sites_match_fixed_plan_and_remain_prefix_only(self):
        plan = json.loads((PACKAGE / 'planned-sites.json').read_text())
        sites = {s['site_id']: s for s in SPEC['r16_fine']['sites']}
        for item in plan['sites']:
            site = sites[item['site_id']]
            self.assertEqual(site['anchor_before'], item['before'])
            self.assertEqual(site['anchor_after'], item['after'])
            self.assertEqual(site['inserted_token'], item['inserted_token'])
            self.assertEqual(site['coarse_rhs_span']['start'][0], item['f9_line'])
            self.assertEqual(site['coarse_rhs_span']['end_exclusive'][0], item['f9_line'])

    def test_source_and_annotation_corruption_rejected(self):
        site = SPEC['r16_fine']['sites'][0]; rel = site['path']
        with self.assertRaises(mirror.MirrorError): mirror.transform(rel, (SOURCE / rel).read_bytes() + b' ')
        broken = (PREVIEW / rel).read_bytes().replace(site['inserted_token'].encode(), b'', 1)
        with self.assertRaises(mirror.MirrorError): mirror.inverse_bytes(rel, broken)

    def test_fine_reader_snapshot_verifies_all_97_source_pins(self):
        manifest = PREVIEW / 'mirror-manifest.json'
        verified = F.verify_mirror_snapshot(PREVIEW, sha(manifest.read_bytes()), SPEC)
        self.assertEqual(len(verified['files']), 97)


if __name__ == '__main__': unittest.main()
