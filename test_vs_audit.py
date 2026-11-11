"""Run with python test_vs_legacy_recovery.py beside bot.py."""
import ast
import pathlib
import re
import unittest

SOURCE = pathlib.Path(__file__).with_name('bot.py')
FUNCTIONS = {'normalize_name','replace_discord_mentions','vs_legacy_name',
             'parse_vs_legacy_message','parse_vs_message','parse_vs_message_with_legacy','is_excluded_vs_result'}

def load_parser():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    required = {'parse_vs_legacy_message','parse_vs_message_with_legacy'}
    if not required.issubset({n.name for n in nodes}):
        raise RuntimeError('bot.py does not contain revised VS legacy parser')
    aliases = next(n.value for n in tree.body if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='ALIASES' for t in n.targets))
    legacy = next(n.value for n in tree.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=='VS_LEGACY_NAME_ALIASES' for t in n.targets))
    e={'re':re,'MAX_SCORE':60,'ALIASES':ast.literal_eval(aliases),
       'VS_LEGACY_NAME_ALIASES':ast.literal_eval(legacy),
       'VS_MENTION_PATTERN':re.compile(r'<@!?(\d+)>')}
    noncompetitive = next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VS_NONCOMPETITIVE_PATTERN' for t in n.targets))
    e['VS_NONCOMPETITIVE_PATTERN'] = eval(compile(ast.Expression(noncompetitive),str(SOURCE),'eval'),e)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),e)
    return e['parse_vs_message_with_legacy']

parse=load_parser()

class VSRecoveryTests(unittest.TestCase):
    def test_plaintext(self):
        result=parse('Jessek 28\nMartin 22\nGumby 24\nCheech 22')
        self.assertEqual(result['scores']['spacedcowboy'],28)
    def test_emote_suffix(self):
        result=parse('Fx 15 :yoshihello~1:\nCaptn 17 :toadwins:\nJabon 30 :wario:\nJessek 34 :mario:')
        self.assertEqual(result['scores']['chang'],17)
    def test_alias_and_dash(self):
        r=parse('@dip(the4man) -16\n@Fx64 -22\n@ClapDaddy a/k/a Fuzz -34\n@CptnTryHard(Chang)(LoveYaBen) -24')
        self.assertEqual(r['scores'],{'dip':16,'fx64':22,'fuzz':34,'chang':24})
    def test_no_space_dash(self):
        r=parse('Fx64-22\n@ClapDaddy a/k/a Fuzz -42 🤯\n@Martin -28\n@dip(the4man) -4')
        self.assertEqual(r['scores']['fuzz'],42)
    def test_colon_emote(self):
        r=parse(':Gumby: 38\n@Wilder 1\n@Toonkette 29\n@the.countess 28')
        self.assertEqual(r['scores']['gumby'],38)
    def test_three_player(self):
        r=parse('Martin 32\nGumby 29\nJessek 35')
        self.assertEqual(len(r['scores']),3)
    def test_reject_incomplete(self):
        self.assertIsNone(parse('Jessek 40\nMartin 27\nR2dz 8'))
    def test_reject_bad_total(self):
        self.assertIsNone(parse('Jessek 28\nMartin 22\nGumby 24\nCheech 23'))
    def test_reject_repeated_name(self):
        self.assertIsNone(parse('Jessek 28\nSpacedCowboy 22\nGumby 24\nCheech 22'))
    def test_default_ranked_without_label(self):
        self.assertIsNotNone(parse('Jessek 28\nMartin 22\nGumby 24\nCheech 22'))
    def test_reject_exhibition(self):
        self.assertIsNone(parse('Exhibition\nJessek 28\nMartin 22\nGumby 24\nCheech 22'))
    def test_reject_unranked_with_ranked_word(self):
        self.assertIsNone(parse('Unranked (not Ranked)\nJessek 28\nMartin 22\nGumby 24\nCheech 22'))
    def test_reject_for_fun(self):
        self.assertIsNone(parse('For fun\nJessek 28\nMartin 22\nGumby 24\nCheech 22'))
    def test_reject_casual(self):
        self.assertIsNone(parse('Casual\nJessek 28\nMartin 22\nGumby 24\nCheech 22'))
    def test_reject_3vs1(self):
        self.assertIsNone(parse('3 VS 1\nToonkette 9\nFx64 7'))
    def test_reject_non_multiplayer(self):
        self.assertIsNone(parse('BWG over YoyoYoshi: 3-0 sets (3-1, 3-0, 3-2)'))
    def test_reject_ranking_exclusion(self):
        self.assertIsNone(parse('Not posted on kaillera due to ranking rules\nVena - 21\nYale - 22\nJustase - 21\nUrban - 32'))
    def test_no_gp_cups(self):
        self.assertIsNone(parse('Fuzz vs Patalus\nMush 30 - 24\nFlow 33 - 22\nStar 27 - 27\nSpec 30 - 18\nTotal 120 - 91'))

if __name__=='__main__': unittest.main()
