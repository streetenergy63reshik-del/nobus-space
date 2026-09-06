"""Recompute confirmed-protocol aggregates from immutable local synthetic receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import scorer

read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main(args):
    root=args.repo; folder=args.evidence; review=read(folder/'holdout-review/adjudication.json')
    cases=scorer.load_cases(root/'tests/gate_c2/qualification/CORPUS-GOLD.json',root/'tests/gate_c2/dataset.json')
    protocol=sha(root/'tests/gate_c2/qualification/PROTOCOL.json')
    assert review['protocol_sha256']==protocol
    adjudicated={(t['engine_blind_id'],t['id'],t['hypothesis_sha256']):t for t in review['tasks']}
    expected_files={'small-dev-2.json'}; reports={}; inputs={}; all_raw=[]
    for engine,blind in [('current','R2'),('small','Z9')]:
        rows=[]; runs=[]
        for iteration in range(3):
            for split in ['dev','holdout']:
                suffix='-recovery1' if (engine,split,iteration)==('small','dev',2) else ''
                name=f'{engine}-{split}-{iteration}{suffix}.json';expected_files.add(name)
                path=folder/'runs'/name;data=read(path);inputs[name]=sha(path)
                assert data['complete'] and data['supervisor']['child_exit_code']==0
                assert data['bounds']['job_memory_bytes']==4294967296 and data['bounds']['cpu_affinity']==15
                assert data['bounds']['serial_native_slots']==1 and not data['supervisor']['job_final_stats']['active_processes']
                assert {r['id'] for r in data['measurements']}=={k for k,c in cases.items() if c['split']==split}
                assert len(data['measurements'])==16
                for raw in data['measurements']+data['concurrency_measurements']+[data['cold_first']]:
                    assert not raw.get('error') and not raw.get('truncated')
                    hh=hashlib.sha256(raw['hypothesis'].encode()).hexdigest()
                    verdict=adjudicated[blind,raw['id'],hh]
                    assert verdict['reference_sha256']==hashlib.sha256(cases[raw['id']]['text'].encode()).hexdigest()
                    assert set(verdict['dimensions'].values()) <= {True,False,'N/A'}
                    assert verdict['semantic_correction_required']==any(v is False for v in verdict['dimensions'].values())
                    assert verdict['semantic_exact_raw']==(not verdict['semantic_correction_required'])
                for raw in data['measurements']:
                    assert raw['iteration']==iteration and raw['split']==split
                    c=cases[raw['id']];hh=hashlib.sha256(raw['hypothesis'].encode()).hexdigest();v=adjudicated[blind,raw['id'],hh]
                    lexical=scorer.score(c['text'],raw['hypothesis'],c['critical'])
                    rows.append({**{k:x for k,x in raw.items() if k!='hypothesis'},**{k:x for k,x in lexical.items() if k!='critical_mismatches'},
                        'hypothesis_sha256':hh,'reference_sha256':v['reference_sha256'],
                        'semantic_exact_raw':v['semantic_exact_raw'],'semantic_correction_required':v['semantic_correction_required'],
                        'dimensions':v['dimensions'],'error_types':v['error_types']})
                runs.append({'file':name,'sha256':inputs[name],'cold_seconds':data['supervisor']['process_cold_seconds'],
                    'elapsed_seconds':data['supervisor']['elapsed_seconds'],'resources':data['supervisor']['job_final_stats'],
                    'concurrency':[{k:v for k,v in r.items() if k!='hypothesis'} for r in data['concurrency_measurements']],
                    'runner_sha256':data['runner_sha256'],'configuration':data['configuration']})
                all_raw.append(data)
        def summary(selected):
            result=scorer.summarize(selected);first=[r for r in selected if r['iteration']==0]
            result.update(semantic_exact_raw=sum(r['semantic_exact_raw'] for r in first)/len(first),
                semantic_exact_count=sum(r['semantic_exact_raw'] for r in first),
                semantic_correction_required=sum(r['semantic_correction_required'] for r in first),
                error_types=dict(Counter(t for r in first for t in r['error_types'])),
                correction_by_iteration={str(i):sum(r['semantic_correction_required'] for r in selected if r['iteration']==i) for i in range(3)},
                semantic_status='INDEPENDENT_SAME_BYTES_ALL_REPEATS_COLD_CONCURRENCY_COVERED',
                legacy_wer=sum(r['legacy']['word_errors'] for r in first)/sum(r['legacy']['words'] for r in first),
                legacy_cer=sum(r['legacy']['char_errors'] for r in first)/sum(r['legacy']['chars'] for r in first))
            return result
        reports[engine]={'all':summary(rows),'by_split':{s:summary([r for r in rows if r['split']==s]) for s in ['dev','holdout']},
            'rows':rows,'runs':runs,'cold_max_seconds':max(r['cold_seconds'] for r in runs),
            'peak_job_memory_bytes':max(r['resources']['peak_job_memory_bytes'] for r in runs)}
    assert {p.name for p in (folder/'runs').glob('*.json')}==expected_files,'unexpected campaign observations'
    failed=read(folder/'runs/small-dev-2.json')
    assert not failed['complete'] and failed['supervisor']['error']=='PermissionError'
    current,small=reports['current'],reports['small']
    lexical=all(s['wer']<=.15 and s['cer']<=.08 for s in [small['all'],small['by_split']['holdout']])
    burden=all(small['by_split'][s]['correction_by_iteration'][str(i)]<=current['by_split'][s]['correction_by_iteration'][str(i)] for s in ['dev','holdout'] for i in range(3))
    gain=small['all']['semantic_exact_raw']-current['all']['semantic_exact_raw']
    resources=small['cold_max_seconds']<=120 and small['peak_job_memory_bytes']<=4294967296 and small['all']['per_file_budget_exceeded']==0
    result={'version':'c2-confirmed-qualification-3.0.0','scope':'32 independent synthetic language cases, three warm repetitions; one installed TTS voice, no claim of human/acoustic generalization',
        'protocol_sha256':protocol,'normalizer_changed':False,'inputs':inputs,'review_sha256':sha(folder/'holdout-review/adjudication.json'),
        'dev_selection_sha256':sha(folder/'selection.json'),'pre_holdout_freeze_sha256':sha(folder/'qualification-freeze.json'),
        'verifier_repair_freeze_sha256':sha(folder/'qualification-recovery-freeze.json'),'reports':reports,
        'criteria':{'lexical':lexical,'correction_non_regression_all_matched_passes':burden,'resources_and_per_file_time':resources,
            'raw_semantic_gain_percentage_points':100*gain,'wer_regression_percentage_points':100*(small['all']['wer']-current['all']['wer']),
            'cer_regression_percentage_points':100*(small['all']['cer']-current['all']['cer']),
            'substantial_gain':gain>=.02,'completed_series_measurement_errors':0,'completed_series_observations_per_engine':96},
        'qualification_verdict':'PASS' if lexical and burden and resources and gain>=.02 else 'FAIL',
        'product_gate_verdict':'BLOCKED: actual B02 ready answers and final independent candidate acceptance pending',
        'historical_failed_attempt':{'file':'small-dev-2.json','sha256':sha(folder/'runs/small-dev-2.json'),
            'supervisor':failed['supervisor'],'completed':2,'not_completed':14,
            'classification':'VERIFIER_DEFECT / environment; exact original WinError not recorded. Windows CRT read exclusion independently reproduced and bounded retry tested. Original attempt remains FAIL, fully charged; replacement is not a new independent language corpus.'},
        'raw_vs_confirmed':'Raw semantics is independent of compiler. Correction counts remain errors; confirmation does not turn them into correct ASR. Accepted product parity requires actual B02 evidence.'}
    assert not args.output.exists()
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in result.items() if k in ['qualification_verdict','criteria']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
