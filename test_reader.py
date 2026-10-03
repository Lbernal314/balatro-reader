import copy
import unittest
import threading
import time
from unittest.mock import patch

from reader import SimulationController, fingerprint
from test_simulator import state, card

class ManualSimulationTests(unittest.TestCase):
    def setUp(self):
        self.data=state([card('A')],[card('2')])
        self.controller=SimulationController(lambda:self.data)

    def test_idle_does_not_start_automatically(self):
        self.assertEqual(self.controller.view()['status'],'idle')
        self.assertIsNone(self.controller.pending)
        self.assertFalse(self.controller.wakeup.is_set())

    def test_submit_captures_input_and_allows_repeat(self):
        first=self.controller.submit(self.data)
        self.assertEqual(self.controller.view()['status'],'running')
        self.assertEqual(self.controller.pending[1]['round']['hands_left'],2)
        self.data['round']['hands_left']=1
        self.assertEqual(self.controller.pending[1]['round']['hands_left'],2)
        second=self.controller.submit(self.data)
        self.assertGreater(second,first)
        self.assertEqual(self.controller.pending[1]['round']['hands_left'],1)

    def test_resource_or_card_change_invalidates_results(self):
        for change in [('hands_left',1),('discards_left',0),('hands_played',2),('chips',50)]:
            self.data=state([card('A')],[card('2')])
            self.controller.submit(self.data)
            self.data['round'][change[0]]=change[1]
            self.assertEqual(self.controller.view()['status'],'stale')
            self.assertNotIn('recommendation',self.controller.view())
        self.controller.submit(self.data)
        self.data['hand']['cards'][0]['value']['rank']='K'
        self.assertEqual(self.controller.view()['status'],'stale')

    def test_highlight_and_recording_do_not_invalidate(self):
        before=fingerprint(self.data)
        self.data['hand']['cards'][0]['state']['highlight']=True
        self.data['registro']={'cambios':23}
        self.assertEqual(before,fingerprint(self.data))

    def test_animated_ui_fields_do_not_interrupt_simulation(self):
        self.data['joker_context']={'round_resets':{'blind_tag':{'tag_sprite':
            {'container':{'collide_check_timer':12}}}},'unused_discards':3}
        self.controller.submit(self.data)
        self.data['joker_context']['round_resets']['blind_tag']['tag_sprite']['container']['collide_check_timer']=13
        self.data['joker_context']['unused_discards']=4
        self.data['hand']['cards'][0]['value']['effect']='Texto actualizado'
        self.assertEqual(self.controller.view()['status'],'running')

    def test_joker_value_and_blind_change_invalidate(self):
        self.data['jokers']['cards']=[{'key':'j_popcorn','ability':{'mult':20}}]
        self.controller.submit(self.data)
        self.data['jokers']['cards'][0]['ability']['mult']=16
        self.assertEqual(self.controller.view()['status'],'stale')
        self.controller.submit(self.data)
        self.data['blinds']['small']['score']=200
        self.assertEqual(self.controller.view()['status'],'stale')

    def test_disconnect_hides_results(self):
        self.controller.submit(self.data)
        self.data=None
        self.assertEqual(self.controller.view()['status'],'waiting')

    def test_interruption_allows_simulating_again_after_recovery(self):
        original=copy.deepcopy(self.data)
        called=threading.Event()
        def interrupted(*args,**kwargs):
            self.data=None
            called.set()
            return {'status':'superseded'}
        with patch('reader.analyze',side_effect=interrupted):
            threading.Thread(target=self.controller.run,daemon=True).start()
            self.controller.submit(original)
            self.assertTrue(called.wait(1))
            deadline=time.monotonic()+1
            while self.controller.result['status']=='running' and time.monotonic()<deadline:
                time.sleep(.01)
        self.data=original
        self.assertEqual(self.controller.view()['status'],'stale')

if __name__=='__main__': unittest.main()
