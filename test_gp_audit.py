"""Regression tests for bot.py GP legacy parser. Run: python test_gp_legacy_recovery.py"""
import ast, html, json, os, re, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).with_name('bot.py')
FUNCTIONS = {'normalize_name','display_name_for_mention','replace_discord_mentions',
 'clean_score_name','gp_report_player','gp_result_matchup','parse_score_lines',
 'split_gp_score_segments','make_gp_score_match','parse_gp_score_report_messages',
 'gp_review_candidate','gp_review_reason','gp_review_entry','write_gp_rejected_audit',
 'possible_gp_ledger_overlap'}
CONSTANTS = {'ALIASES','VS_MENTION_PATTERN','GP_MATCHUP_PATTERN','GP_CUP_PATTERN',
 'GP_TOTAL_PATTERN','GP_BARE_PAIR_PATTERN','GP_SIMPLE_PAIR_PATTERN',
 'GP_NOTES_PATTERN','GP_ROUND_LABEL_PATTERN','GP_RESULT_PREFIX_PATTERN'}

def load():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if
        (isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS) or
        (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTANTS for t in n.targets))]
    env = {'re':re,'html':html,'os':os,'json':json,'datetime':datetime,'timezone':timezone,
           'GP_MAX_SCORE':160,'GP_REJECTED_AUDIT_LIMIT':10000}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),env)
    return env
E = load()

class GPRecoveryTests(unittest.TestCase):
    def test_old_abbreviations(self):
        s='@FuzzyFugs vs. @Patalus\nMush: 30-27\nFlow: 33-8\nStar: 27-18\nSpec: 33-21\nTOTAL: 123-74'
        self.assertEqual(E['parse_score_lines'](s),{'fuzz':123,'patalus':74})
    def test_full_cup_names(self):
        s='MrPitt vs Wilder\nMushroom: 30-10\nFlower: 33-3\nStar: 36-0\nSpecial: 30-0\nTotal: 129-13'
        self.assertEqual(E['parse_score_lines'](s),{'mrpitt':129,'wilder':13})
    def test_compact_emojis(self):
        s='Ranked\n@Fx64 vs @dip(the4man)\n:mushroomcup: 21-36\n:flowercup: 36-12\n:specialcup: 33-24\n:starcup: 24-27\n:total: 114-99'
        self.assertEqual(E['parse_score_lines'](s),{'fx64':114,'dip':99})
    def test_matchup_separator(self):
        s='@FuzzyFugs - @rbxgg\nMush: 27-24\nFlow: 21-33\nStar: 28-19\nSpec: 18-27\nTOTAL: 94-103'
        self.assertEqual(E['parse_score_lines'](s),{'fuzz':94,'rbxgg':103})
    def test_unlabeled(self):
        s='@ClapDaddy a/k/a Fuzz vs @Baker\n27-25\n33-21\n21-27\n36-15\n=117-88'
        self.assertEqual(E['parse_score_lines'](s),{'fuzz':117,'baker':88})
    def test_casual_and_exhibition(self):
        for word in ('Casual','Exhibition','Unranked'):
            s=f'{word}\n@Fx64 vs @Wilder\nMush: 30-24\nFlow: 30-24\nStar: 30-24\nSpec: 30-24\nTotal: 120-96'
            self.assertEqual(E['parse_score_lines'](s),{})
    def test_total_mismatch(self):
        s='Ranked\n@Fx64 vs @Wilder\nMush: 30-24\nFlow: 30-24\nStar: 30-24\nSpec: 30-24\nTotal: 120-95'
        self.assertEqual(E['parse_score_lines'](s),{})
    def test_commentary_not_match(self):
        self.assertEqual(E['parse_score_lines']('Ranked\n@Fx64 won it on Rainbow Road!\n30-24'),{})
    def test_multiple_matchups_with_own_totals(self):
        s=('Ranked\n@Fx64 vs @Wilder\nMush: 30-24\nFlow: 30-24\nStar: 30-24\nSpec: 30-24\nTotal: 120-96\n'
           '@Fx64 vs @Wilder\nMush: 24-30\nFlow: 24-30\nStar: 24-30\nSpec: 24-30\nTotal: 96-120')
        out=E['parse_gp_score_report_messages'](s)
        self.assertEqual(len(out),2)
        self.assertEqual([m['submatch_index'] for m in out],[1,2])
    def test_numbered_series_inherits_matchup(self):
        s=('Ranked\n@FuzzyFugs vs @blaze up\nRound 1\nMush: 30-24\nFlow: 30-24\nStar: 30-24\nSpec: 30-24\nTotal: 120-96\n'
           'Round 2\nMush: 24-30\nFlow: 24-30\nStar: 24-30\nSpec: 24-30\nTotal: 96-120')
        out=E['parse_gp_score_report_messages'](s)
        self.assertEqual(len(out),2)
        self.assertEqual(out[1]['scores'],{'fuzz':96,'martin':120})
    def test_ledger_overlap_review_without_assuming_duplicate(self):
        from datetime import timedelta
        now = datetime(2023, 4, 25, 12, 26, tzinfo=timezone.utc)
        E['gp_matches'] = [{'source_type':'gp_elo_ledger',
            'players':['gumby','mrpitt'],'winner':'gumby',
            'created_at':(now + timedelta(minutes=2)).isoformat(),
            'message_id':1122}]
        match = {'source_type':'gp_score_report','players':['gumby','mrpitt'],
                 'winner':'gumby','scores':{'gumby':126,'mrpitt':84}}
        msg = SimpleNamespace(created_at=now)
        self.assertEqual(E['possible_gp_ledger_overlap'](match, msg)['message_id'],1122)
        self.assertIsNone(E['possible_gp_ledger_overlap'](
            dict(match, players=['fuzz','mrpitt'],winner='fuzz'),msg))

    def test_audit_file(self):
        s='Ranked\n@Fx64 vs @Wilder\nMush: 30-24\nFlow: 30-24\nStar: 30-24\nSpec: 30-24\nTotal: 120-95'
        m=SimpleNamespace(id=23,channel=SimpleNamespace(id=7),created_at=datetime.now(timezone.utc),jump_url='https://discord.com/channels/1/7/23',author='Fx64')
        with tempfile.TemporaryDirectory() as d:
            E['GP_REJECTED_AUDIT_FILE']=str(Path(d)/'audit.json')
            E['write_gp_rejected_audit']([E['gp_review_entry'](m,s,'gp','test')])
            j=json.loads(Path(E['GP_REJECTED_AUDIT_FILE']).read_text())
            self.assertEqual(j['count'],1)
            self.assertEqual(j['entries'][0]['reason'],'cup_total_mismatch')

if __name__=='__main__':unittest.main()
