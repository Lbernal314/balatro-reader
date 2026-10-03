import copy
import itertools
import unittest

import numpy as np

from simulator import Evaluator, analyze

def card(rank, suit='H', **modifier):
    return {'value':{'rank':rank,'suit':suit},'modifier':modifier,'state':{}}

def state(cards, pool=None, jokers=None):
    return {'state':'SELECTING_HAND','hand':{'cards':cards,'highlighted_limit':5},
            'draw_pool':{'cards':pool or []},'jokers':{'cards':jokers or []},
            'round':{'hands_left':2,'discards_left':1,'chips':0},
            'blinds':{'small':{'status':'CURRENT','type':'SMALL','score':100}},
            'money':0}

def score(cards,jokers=None):
    s=state(cards,jokers=jokers)
    ev=Evaluator(s,cards)
    values,kinds,groups=ev.scores(np.arange(len(cards))[None,:],1,0)
    i=groups.index(tuple(range(len(cards))))
    return values[0,i],kinds[0,i]

class ScoringTests(unittest.TestCase):
    def test_poker_categories(self):
        examples=[('A',None,16,0),('AAK',None,64,1),('AA22K',None,92,2),
                  ('AAA2',None,189,3),('23456','HDCHD',200,4),
                  ('23479',None,240,5),('AAA22','HDCHD',308,6),
                  ('AAAA2','HDCHD',728,7),('23456',None,960,8),
                  ('AAAAA','HDCHD',2100,9),('AAA22',None,2478,10),
                  ('AAAAA',None,3440,11)]
        for ranks,suits,expected,category in examples:
            # Prevent incidental flushes in pair/trips examples shorter than 5.
            suits=suits or 'H'*len(ranks)
            if ranks=='AA22K': suits='HDCHD'
            with self.subTest(ranks=ranks,category=category):
                self.assertEqual(score([card(r,s) for r,s in zip(ranks,suits)]),(expected,category))

    def test_wheel_and_wild_flush(self):
        self.assertEqual(score([card(r,s) for r,s in zip('A2345','HDCHD')])[0],220)
        self.assertEqual(score([card(r) for r in '2347']+[card('9','S',enhancement='WILD')])[0],240)

    def test_enhancements_and_retriggers(self):
        self.assertEqual(score([card('A',enhancement='GLASS')])[0],32)
        self.assertEqual(score([card('A',enhancement='MULT')])[0],80)
        self.assertEqual(score([card('A',enhancement='MULT',seal='RED')])[0],243)
        self.assertEqual(score([card('2'),card('A',enhancement='STONE')])[0],57)

    def test_held_steel(self):
        cards=[card('2'),card('A',enhancement='STEEL')]
        ev=Evaluator(state(cards),cards)
        values,_,groups=ev.scores(np.array([[0,1]]),1,0)
        self.assertEqual(values[0,groups.index((0,))],10)

    def test_order_optimization(self):
        cards=[card('A',enhancement='GLASS'),card('A','S',enhancement='MULT')]
        self.assertEqual(score(cards)[0],384)
        self.assertEqual(Evaluator(state(cards),cards).order([0,1]),[1,0])

    def test_fast_path_matches_generic_path(self):
        cards=[card(r,s) for r,s in zip('AA234TJK','HDSCHDSC')]
        ev=Evaluator(state(cards),cards)
        fast=ev.scores(np.arange(8)[None,:],2,33)[0]
        ev.simple=False
        np.testing.assert_array_equal(fast,ev.scores(np.arange(8)[None,:],2,33)[0])

    def test_joker_order_and_editions(self):
        cards=[card('A')]
        joker={'key':'j_joker','ability':{'mult':4}}
        self.assertEqual(score(cards,[joker])[0],80)
        banana={'key':'j_cavendish','ability':{'extra':{'Xmult':3}},'modifier':{'edition':'HOLO'}}
        self.assertEqual(score(cards,[banana])[0],528)

    def test_hologram_uses_live_multiplier_and_joker_order(self):
        cards=[card('A')]
        hologram={'key':'j_hologram','ability':{'x_mult':1.25,'extra':0.25}}
        joker={'key':'j_joker','ability':{'mult':4}}
        self.assertEqual(score(cards,[joker,hologram])[0],100)
        self.assertEqual(score(cards,[hologram,joker])[0],84)

    def test_popcorn_and_ramen_use_current_values(self):
        cards=[card('A')]
        popcorn={'key':'j_popcorn','ability':{'mult':12}}
        ramen={'key':'j_ramen','ability':{'x_mult':1.8,'extra':0.01}}
        self.assertEqual(score(cards,[popcorn,ramen])[0],374)

    def test_ramen_decays_per_discarded_card(self):
        cards=[card('A'),card('2')]
        ramen={'key':'j_ramen','ability':{'x_mult':2,'extra':0.01}}
        ev=Evaluator(state(cards,jokers=[ramen]),cards)
        hands=np.array([[0,1]])
        scores,_,groups=ev.scores(hands,0,0,discarded_cards=5)
        self.assertEqual(scores[0,groups.index((0,))],31)

    def test_hook_discards_reduce_ramen_before_scoring(self):
        cards=[card('A'),card('2'),card('3')]
        ramen={'key':'j_ramen','ability':{'x_mult':2,'extra':0.01},
               'modifier':{'edition':'POLYCHROME'}}
        ev=Evaluator(state(cards,jokers=[ramen]),cards,hook=True)
        scores,_,groups=ev.scores(np.array([[0,1,2]]),0,0)
        self.assertEqual(scores[0,groups.index((0,))],47)
        self.assertEqual(scores[0,groups.index((0,1,2))],48)

    def test_ramen_eaten_after_discard_loses_edition(self):
        cards=[card('A')]
        ramen={'key':'j_ramen','ability':{'x_mult':1.02,'extra':0.01},
               'modifier':{'edition':'POLYCHROME'}}
        ev=Evaluator(state(cards,jokers=[ramen]),cards)
        scores,_,groups=ev.scores(np.array([[0]]),0,0,discarded_cards=3)
        self.assertEqual(scores[0,groups.index((0,))],16)

    def test_greedy_joker_counts_only_scoring_diamonds(self):
        greedy={'key':'j_greedy_joker','ability':{'extra':{'suit':'Diamonds','s_mult':3}}}
        cards=[card('A','D'),card('A','C'),card('2','D')]
        self.assertEqual(score(cards,[greedy])[0],160)
        self.assertEqual(score([card('A','D',seal='RED')],[greedy])[0],189)

    def test_mouth_restricts_hands_after_first_play(self):
        cards=[card('A','D'),card('A','C'),card('2','D')]
        s=state(cards)
        s['blinds']['small'].update(type='BOSS',name='The Mouth')
        self.assertEqual(analyze(s,trials=20)['status'],'ready')
        s['round']['hands_played']=1
        s['hands']={'Pair':{'played_this_round':1}}
        ev=Evaluator(s,cards)
        scores,_,groups=ev.scores(np.array([[0,1,2]]),0,0)
        self.assertEqual(scores[0,groups.index((0,))],0)
        self.assertGreater(scores[0,groups.index((0,1))],0)

    def test_fullhouse_contains_two_pair(self):
        cards=[card(r,s) for r,s in zip('AAA22','HDCHD')]
        self.assertEqual(score(cards,[{'key':'j_mad','ability':{'t_mult':10}}])[0],1078)

    def test_debuff_and_levels(self):
        c=card('A');c['state']['debuff']=True
        self.assertEqual(score([c])[0],5)
        s=state([card('A')]);s['hands']={'High Card':{'chips':15,'mult':2}}
        self.assertEqual(Evaluator(s,s['hand']['cards']).best(np.array([[0]]),1,0)[0][0],52)

class MonteCarloTests(unittest.TestCase):
    def test_all_options_and_reproducibility(self):
        s=state([card('2'),card('A')],[card('3'),card('4'),card('A','S')])
        r=analyze(s,1000)
        self.assertEqual(r['discard_options'],3)
        self.assertTrue(all(c['trials']==1000 for c in r['discards']))
        self.assertEqual(r['recommendation'],analyze(s,1000)['recommendation'])
        # All three ways of drawing two physical cards are legal and equally likely.
        ev=Evaluator(s,s['hand']['cards']+s['draw_pool']['cards'])
        exact=ev.best(np.array(list(itertools.combinations([2,3,4],2))),0,1)[0].mean()
        estimate=next(c for c in r['discards'] if c['indices']==[1,2])['score']
        self.assertLess(abs(exact-estimate),3)

    def test_win_now_preserves_discard(self):
        s=state([card('A')],[card('2')]);s['blinds']['small']['score']=15
        self.assertEqual(analyze(s,1000)['recommendation']['action'],'play')

    def test_no_discards(self):
        s=state([card('A')],[card('2')]);s['round']['discards_left']=0
        self.assertEqual(analyze(s)['discard_options'],0)

    def test_depleted_draw_pool(self):
        s=state([card('2'),card('3'),card('4')],[card('A')])
        self.assertEqual(analyze(s)['discard_options'],7)

    def test_unsupported_rules_block(self):
        s=state([card('A')],jokers=[{'key':'j_blueprint'}])
        self.assertEqual(analyze(s)['status'],'blocked')
        s=state([card('A',enhancement='LUCKY')])
        with self.assertRaisesRegex(ValueError,'Mejora'):
            analyze(s)
        s=state([card('A')]);s['blinds']['small']['type']='BOSS'
        self.assertEqual(analyze(s)['status'],'blocked')

    def test_hook_uses_current_hand_and_target(self):
        s=state([card('A'),card('2')],[card('3')])
        s['blinds']['small'].update(type='BOSS',name='The Hook',score=60)
        s['round']['chips']=20
        result=analyze(s,trials=20)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['target'],40)
        self.assertIn('The Hook descarta 2 cartas',result['scope'])

    def test_hook_blocks_held_steel_uncertainty(self):
        s=state([card('A'),card('2',enhancement='STEEL')])
        s['blinds']['small'].update(type='BOSS',name='The Hook')
        result=analyze(s,trials=20)
        self.assertEqual(result['status'],'blocked')
        self.assertIn('acero',result['reason'])
        s['joker_context']={'blind':{'disabled':True}}
        self.assertEqual(analyze(s,trials=20)['status'],'ready')

    def test_passive_boss_uses_live_resources(self):
        s=state([card('A')])
        s['blinds']['small'].update(type='BOSS',name='The Water',score=200)
        s['round']['discards_left']=0
        result=analyze(s,trials=20)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['discard_options'],0)
        self.assertEqual(result['target'],200)

    def test_no_state_mutation(self):
        s=state([card('A')],[card('2')]);original=copy.deepcopy(s)
        analyze(s)
        self.assertEqual(s,original)

    def test_cancellation(self):
        s=state([card('A')],[card('2')])
        self.assertEqual(analyze(s,cancelled=lambda:True)['status'],'superseded')

    def test_partial_results_before_completion(self):
        s=state([card('2'),card('A')],[card('3'),card('4'),card('A','S')])
        partial=[]
        result=analyze(s,1000,progress=lambda done,total,value:partial.append(value))
        self.assertEqual([p['completed'] for p in partial],[0,1,2,3])
        self.assertTrue(all(p['status']=='running' and p['partial'] for p in partial))
        self.assertTrue(partial[0]['plays'])
        self.assertEqual(partial[-1]['recommendation'],result['recommendation'])
        self.assertFalse(result['partial'])

    def test_second_third_and_last_hand_resources(self):
        for played,left,discards in [(0,4,3),(1,3,2),(2,2,1),(3,1,0)]:
            s=state([card('A')],[card('2')])
            s['round'].update(hands_played=played,hands_left=left,discards_left=discards,chips=40)
            result=analyze(s,1000)
            self.assertEqual(result['hand_number'],played+1)
            self.assertEqual(result['hands_left'],left)
            self.assertEqual(result['hands_after_next_play'],left-1)
            self.assertEqual(result['discards_left'],discards)
            self.assertEqual(result['target'],60)
        s['round']['hands_left']=0
        self.assertEqual(analyze(s)['status'],'waiting')

if __name__=='__main__': unittest.main()
