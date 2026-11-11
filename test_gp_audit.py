"""Dependency-light regression tests for GP parsing and the rejected-match audit.
Run with: python test_gp_audit.py
"""
import ast
import html
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).with_name('bot.py')
NAMES = {
    'normalize_name', 'display_name_for_mention', 'replace_discord_mentions',
    'clean_score_name', 'gp_report_player', 'parse_score_lines',
    'split_gp_score_segments', 'parse_gp_score_report_messages',
    'make_gp_score_match', 'gp_review_candidate', 'gp_review_reason',
    'gp_review_entry', 'write_gp_rejected_audit',
}
CONSTANTS = {'ALIASES', 'VS_MENTION_PATTERN', 'GP_MATCHUP_PATTERN', 'GP_CUP_PATTERN',
             'GP_TOTAL_PATTERN', 'GP_BARE_PAIR_PATTERN', 'GP_SIMPLE_PAIR_PATTERN',
             'GP_NOTES_PATTERN', 'GP_ROUND_LABEL_PATTERN'}


def load_gp_functions():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if
             (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES)
             or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTANTS for t in node.targets))]
    env = {'re': re, 'html': html, 'os': os, 'json': json, 'datetime': datetime,
           'timezone': timezone, 'GP_MAX_SCORE': 160, 'GP_REJECTED_AUDIT_LIMIT': 10000}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env


E = load_gp_functions()

def report(cups, total, header='@Fx64 vs @WilderMK64', label='Ranked'):
    return '\n'.join([label, header] + [f':{c}: {a}-{b}' for c, (a,b) in zip(
        ['mushroomcup', 'flowercup', 'specialcup', 'starcup'], cups)] + [f':total: {total[0]}-{total[1]}'])

class GPTests(unittest.TestCase):
    def test_valid_labeled(self):
        s=report([(24,30),(33,13),(27,9),(18,19)],(102,71))
        self.assertEqual(E['parse_score_lines'](s), {'fx64':102,'wilder':71})
        self.assertFalse(E['gp_review_candidate'](s) and not E['parse_score_lines'](s))
    def test_incorrect_total_audited(self):
        s=report([(24,30),(33,13),(27,9),(18,19)],(102,61))
        self.assertEqual(E['parse_score_lines'](s), {})
        self.assertTrue(E['gp_review_candidate'](s))
        self.assertEqual(E['gp_review_reason'](s),'cup_total_mismatch')
    def test_casual_not_audited(self):
        s=report([(24,30),(33,13),(27,9),(18,19)],(102,71), label='Casual')
        self.assertEqual(E['parse_score_lines'](s), {})
        self.assertFalse(E['gp_review_candidate'](s))
    def test_unlabeled_rows(self):
        s='@ClapDaddy a/k/a Fuzz vs @Baker\n27-25\n33-21\n21-27\n36-15\n=117-88'
        self.assertEqual(E['parse_score_lines'](s), {'fuzz':117,'baker':88})
    def test_missing_total(self):
        s=report([(24,30),(33,13),(27,9),(18,19)],(102,71)).replace(':total: 102-71','')
        self.assertEqual(E['parse_score_lines'](s), {})
        self.assertTrue(E['gp_review_candidate'](s))
    def test_conversation_skipped(self):
        self.assertFalse(E['gp_review_candidate']('Ready tomorrow at 8?'))
    def test_audit_record_and_file(self):
        s=report([(24,30),(33,13),(27,9),(18,19)],(102,61))
        msg=SimpleNamespace(id=1234,channel=SimpleNamespace(id=7),created_at=datetime(2026,9,6,tzinfo=timezone.utc),
            jump_url='https://discord.com/channels/1/7/1234',author='Fx64')
        entry=E['gp_review_entry'](msg,s,'gp-scores','primary')
        self.assertEqual(entry['reason'],'cup_total_mismatch')
        with tempfile.TemporaryDirectory() as d:
            E['GP_REJECTED_AUDIT_FILE']=str(Path(d)/'audit.json')
            E['write_gp_rejected_audit']([entry])
            payload=json.loads(Path(E['GP_REJECTED_AUDIT_FILE']).read_text())
            self.assertEqual(payload['count'],1)
            self.assertEqual(payload['entries'][0]['message_id'],'1234')

if __name__ == '__main__':
    unittest.main()
