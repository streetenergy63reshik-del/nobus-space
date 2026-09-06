"""Apply the frozen lexical scorer to a comparator receipt; publish no transcript."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from benchmark import score


def summarize(source):
    data=json.loads(Path(__file__).with_name('dataset.json').read_text(encoding='utf-8'))
    cases={case['id']:case for case in data['cases']}
    result=json.loads(source.read_text(encoding='utf-8'))
    rows=[]
    for item in result['measurements']:
        case=cases[item['id']]
        rows.append({k:v for k,v in item.items() if k!='hypothesis'} |
            score(case['text'],item['hypothesis'],case['critical']) |
            {'rtf':item['seconds']/item['duration']})
    first=[x for x in rows if x['iteration']==0]
    p95=lambda xs: sorted(xs)[math.ceil(.95*len(xs))-1]
    result['measurements']=rows
    result['raw_receipt_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    result['summary']={
        'wer':sum(r['word_errors'] for r in first)/sum(r['words'] for r in first),
        'cer':sum(r['char_errors'] for r in first)/sum(r['chars'] for r in first),
        'critical_errors':sum(r['critical_errors'] for r in first),
        'latency_p50':statistics.median(r['seconds'] for r in rows),
        'latency_p95':p95([r['seconds'] for r in rows]),
        'rtf_p95':p95([r['rtf'] for r in rows]),
        'peak_ram_bytes':max(r['peak_ram_bytes'] for r in rows),
        'semantic_exactness':None,'asr_decision':'BLOCKED'}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=summarize(args.source)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['summary']))
