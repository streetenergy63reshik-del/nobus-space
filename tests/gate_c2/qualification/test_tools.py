"""Only stdlib synthetic unit checks. Never invokes TTS, ASR, compiler or network."""
from array import array
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import scorer
import render


class NormalizationTests(unittest.TestCase):
    def test_frozen_positive_pairs(self):
        data=json.loads((HERE/'NORMALIZATION-GOLD.json').read_text(encoding='utf-8'))
        for pair in data['positive']:
            with self.subTest(pair=pair): self.assertEqual(scorer.normalize(pair['a']),scorer.normalize(pair['b']))

    def test_frozen_negative_pairs(self):
        data=json.loads((HERE/'NORMALIZATION-GOLD.json').read_text(encoding='utf-8'))
        for pair in data['negative']:
            with self.subTest(pair=pair): self.assertNotEqual(scorer.normalize(pair['a']),scorer.normalize(pair['b']))

    def test_critical_numeric_span_stays_bound(self):
        ref='В отчете сто двадцать пять строк и три раздела.'
        good=scorer.score(ref,'В отчете 125 строк и 3 раздела.',['сто','двадцать','пять','три'])
        bad=scorer.score(ref,'В отчете 152 строки и 3 раздела.',['сто','двадцать','пять','три'])
        self.assertEqual(good['critical_token_errors'],0)
        self.assertGreater(good['legacy']['critical_mismatches'],0)
        self.assertGreater(bad['critical_token_errors'],0)

    def test_critical_negation_and_counts(self):
        self.assertEqual(scorer.score('Не создавай встречу.','Создавай встречу.',['не'])['critical_token_errors'],1)
        self.assertEqual(scorer.score('Не сохраняй и не отправляй.','Не сохраняй и отправляй.',['не'])['critical_token_errors'],1)
        self.assertEqual(scorer.score('Черновик из трёх пунктов.','Черновик из 3 пунктов.',['трёх'])['critical_token_errors'],0)

    def test_dates_partial_and_invalid(self):
        self.assertEqual(scorer.normalize('8 ноября'),['date:--11-08'])
        self.assertNotIn('date:2026-02-31',scorer.normalize('31.02.2026'))
        self.assertNotEqual(scorer.normalize('23 сентября 2026'),scorer.normalize('23 сентября 2025'))

    def test_numeric_grammar_not_arbitrary_sum(self):
        self.assertIsNone(scorer.integer(['два','три']))
        self.assertIsNone(scorer.integer(['сто','сто']))
        self.assertNotEqual(scorer.normalize('минус пять'),scorer.normalize('пять'))
        self.assertNotEqual(scorer.normalize('-5'),scorer.normalize('5'))
        self.assertNotEqual(scorer.normalize('−5'),scorer.normalize('5'))
        self.assertEqual(scorer.normalize('−5'),scorer.normalize('-5'))
        self.assertNotEqual(scorer.normalize('0.5 процента'),scorer.normalize('0.5'))

    def test_no_brand_repair_in_lexical_function(self):
        self.assertNotEqual(scorer.normalize('Nobus Space'),scorer.normalize('Нобус Спейс'))

    def test_scorer_empty_hypothesis_is_error(self):
        row=scorer.score('Не отправляй письмо.','',['не'])
        self.assertEqual(row['word_errors'],row['words'])
        self.assertEqual(row['critical_token_errors'],1)

    def test_invalid_timing_is_counted(self):
        lexical=scorer.score('Привет.','Привет.',[])
        summary=scorer.summarize([{**lexical,'iteration':0,'seconds':1,'duration':float('inf')}])
        self.assertEqual(summary['missing_or_invalid_timing_rows'],1)
        self.assertIsNone(summary['raw_rtf_p95'])


class AcousticTests(unittest.TestCase):
    def samples(self,amplitude=5000):
        return array('h',(round(amplitude*math.sin(2*math.pi*440*n/render.RATE)) for n in range(render.RATE)))

    def test_recipe_text_boundary_and_scope(self):
        gold=json.loads((HERE/'CORPUS-GOLD.json').read_text(encoding='utf-8'))
        self.assertEqual(len(render.validate_recipes(gold)),16)
        gold['holdout'][0]['id']='../escape'
        with self.assertRaises(ValueError): render.validate_recipes(gold)

    def test_real_pause_exact_samples(self):
        a=array('h',[100,-100]); b=array('h',[500,-500])
        samples,pauses=render.combine_segments([(a,750),(b,1500)])
        self.assertEqual(len(samples),4+12000+24000)
        self.assertEqual(samples[:2],a)
        self.assertEqual(samples[12002:12004],b)
        self.assertTrue(all(value==0 for value in samples[2:12002]))
        self.assertEqual([p['frames'] for p in pauses],[12000,24000])

    def test_noise_deterministic_and_snr(self):
        source=self.samples()
        a,ma=render.with_noise(source,seed=20260904,snr_db=20)
        b,mb=render.with_noise(source,seed=20260904,snr_db=20)
        c,_=render.with_noise(source,seed=20260905,snr_db=20)
        self.assertEqual(a,b); self.assertEqual(ma,mb); self.assertNotEqual(a,c)
        self.assertLess(abs(ma['realized_snr_db']-20),0.01)
        self.assertEqual(render.pcm_stats(a)['clipped_samples'],0)

    def test_clipping_prevented_by_shared_gain(self):
        samples,meta=render.with_noise(self.samples(32767),seed=20260904,snr_db=20)
        self.assertLess(meta['common_gain'],1)
        self.assertEqual(render.pcm_stats(samples)['clipped_samples'],0)
        self.assertLess(abs(meta['realized_snr_db']-20),0.01)

    def test_noise_rejects_silence_or_unfrozen_recipe(self):
        with self.assertRaises(ValueError): render.with_noise(array('h',[0]*100),seed=1,snr_db=20)
        with self.assertRaises(ValueError): render.with_noise(self.samples(),seed=1,snr_db=10)

    def test_pcm_roundtrip_and_no_overwrite(self):
        # Only these test-owned fixtures are temporary; historical evidence is never touched.
        with tempfile.TemporaryDirectory(prefix='asr-recipe-unit-') as temporary:
            path=Path(temporary)/'unit.wav'; source=self.samples()
            render.write_pcm(path,source)
            self.assertEqual(render.read_pcm(path),source)
            with self.assertRaises(FileExistsError): render.write_pcm(path,source)


if __name__=='__main__':
    unittest.main(verbosity=2)
