"""Offline lexical scorer and blind semantic-review worksheet; no ASR/compiler imports."""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

HERE = Path(__file__).resolve().parent
MONTHS = dict(zip(('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'),range(1,13)))
UNITS = {'ноль':0,'нуль':0,'один':1,'одна':1,'одно':1,'два':2,'две':2,'три':3,'четыре':4,'пять':5,'шесть':6,'семь':7,'восемь':8,'девять':9}
UNITS.update({'одного':1,'одной':1,'двух':2,'трех':3,'четырех':4,'пяти':5,'шести':6,'семи':7,'восьми':8,'девяти':9})
TEENS = dict(zip(('десять','одиннадцать','двенадцать','тринадцать','четырнадцать','пятнадцать','шестнадцать','семнадцать','восемнадцать','девятнадцать'),range(10,20)))
TENS = dict(zip(('двадцать','тридцать','сорок','пятьдесят','шестьдесят','семьдесят','восемьдесят','девяносто'),range(20,100,10)))
HUNDREDS = dict(zip(('сто','двести','триста','четыреста','пятьсот','шестьсот','семьсот','восемьсот','девятьсот'),range(100,1000,100)))
ORDINAL = {}
for forms,value in [
    ('первое первого первый',1),('второе второго второй',2),('третье третьего третий',3),
    ('четвертое четвертого четвертый',4),('пятое пятого пятый',5),('шестое шестого шестой',6),
    ('седьмое седьмого седьмой',7),('восьмое восьмого восьмой',8),('девятое девятого девятый',9),
    ('десятое десятого десятый',10),('одиннадцатое одиннадцатого одиннадцатый',11),
    ('двенадцатое двенадцатого двенадцатый',12),('тринадцатое тринадцатого тринадцатый',13),
    ('четырнадцатое четырнадцатого четырнадцатый',14),('пятнадцатое пятнадцатого пятнадцатый',15),
    ('шестнадцатое шестнадцатого шестнадцатый',16),('семнадцатое семнадцатого семнадцатый',17),
    ('восемнадцатое восемнадцатого восемнадцатый',18),('девятнадцатое девятнадцатого девятнадцатый',19),
    ('двадцатое двадцатого двадцатый',20),('тридцатое тридцатого тридцатый',30),
]:
    ORDINAL.update({form:value for form in forms.split()})
PERCENT = {'процент','процента','процентов','%'}
OPAQUE = {'код','идентификатор','артикул'}
TOKEN = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4}|[+-]?[0-9]+(?:[.,][0-9]+)?|[^\W\d]+|[%]|[_0-9]+',re.UNICODE)


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def raw_words(text: str) -> list[str]:
    return re.findall(r'\w+',text.casefold().replace('ё','е'))


def integer(tokens: list[str], *, ordinal: bool=False) -> int | None:
    """Closed Russian 0..9999 grammar. Never sums arbitrary adjacent number words."""
    if not tokens:
        return None
    if len(tokens)==1 and re.fullmatch(r'0|[1-9][0-9]{0,3}',tokens[0]):
        return int(tokens[0])
    original=tokens
    tokens=list(tokens)
    tail=None
    if ordinal and tokens[-1] in ORDINAL:
        tail=ORDINAL[tokens.pop()]
        if not tokens:
            return tail
    total=0
    if tokens and tokens[0]=='тысяча':
        total=1000; tokens=tokens[1:]
    elif len(tokens)>=2 and tokens[0] in UNITS and 1<=UNITS[tokens[0]]<=9 and tokens[1] in {'тысяча','тысячи','тысяч'}:
        total=UNITS[tokens[0]]*1000; tokens=tokens[2:]
    if tokens and tokens[0] in HUNDREDS:
        total+=HUNDREDS[tokens[0]]; tokens=tokens[1:]
    if tokens and tokens[0] in TENS:
        total+=TENS[tokens[0]]; tokens=tokens[1:]
        if tokens and tokens[0] in UNITS and UNITS[tokens[0]]>0:
            total+=UNITS[tokens[0]]; tokens=tokens[1:]
            if tail is not None: return None
        if tail is not None and not 1<=tail<=9: return None
    elif tokens and tokens[0] in TEENS:
        total+=TEENS[tokens[0]]; tokens=tokens[1:]
        if tail is not None: return None
    elif tokens and tokens[0] in UNITS:
        total+=UNITS[tokens[0]]; tokens=tokens[1:]
        if tail is not None: return None
    if tokens or (total==0 and original!=['ноль'] and original!=['нуль']):
        return None
    return total+(tail or 0)


def decimal_text(number: Decimal) -> str:
    return format(number.normalize(),'f') if number else '0'


def canonical_date(day: int, month: int, year: int | None) -> str | None:
    try:
        date(year if year is not None else 2000,month,day)
    except ValueError:
        return None
    return f'date:{year:04d}-{month:02d}-{day:02d}' if year is not None else f'date:--{month:02d}-{day:02d}'


def atoms(text: str) -> list[tuple[str,list[str]]]:
    """Return (normalized token, its original tokens), preserving critical-span provenance."""
    tokens=TOKEN.findall(text.casefold().replace('ё','е').replace('−','-'))
    result=[]; i=0
    while i<len(tokens):
        start=i; t=tokens[i]
        opaque=i>0 and tokens[i-1] in OPAQUE
        m=re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})',t)
        n=re.fullmatch(r'([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})',t)
        if not opaque and (m or n):
            y,mo,d=map(int,m.groups()) if m else tuple(reversed(tuple(map(int,n.groups()))))
            value=canonical_date(d,mo,y)
            if value:
                i+=1
                if i<len(tokens) and tokens[i] in {'год','года','году'}: i+=1
                result.append((value,tokens[start:i])); continue
        matched=False
        if not opaque:
            for day_end in range(min(i+3,len(tokens)-1),i,-1):
                if tokens[day_end] not in MONTHS: continue
                day=integer(tokens[i:day_end],ordinal=True)
                if day is None or not 1<=day<=31: continue
                month=MONTHS[tokens[day_end]]; end=day_end+1; year=None
                for year_end in range(min(end+6,len(tokens)),end,-1):
                    possible=integer(tokens[end:year_end],ordinal=True)
                    if possible is not None and 1000<=possible<=9999:
                        year=possible; end=year_end
                        if end<len(tokens) and tokens[end] in {'год','года','году'}: end+=1
                        break
                value=canonical_date(day,month,year)
                if value:
                    i=end; result.append((value,tokens[start:i])); matched=True; break
        if matched: continue
        # Decimal word form is explicit and bounded: N целых K десятых.
        if not opaque:
            for dot in range(i+1,min(i+6,len(tokens))):
                if tokens[dot] not in {'целых','целая','целое'}: continue
                whole=integer(tokens[i:dot])
                if whole is None: continue
                for frac_end in range(dot+2,min(dot+5,len(tokens))):
                    if tokens[frac_end] not in {'десятых','десятая'}: continue
                    numerator=integer(tokens[dot+1:frac_end])
                    if numerator is None or not 0<=numerator<=9: continue
                    value=Decimal(whole)+Decimal(numerator)/10; i=frac_end+1
                    kind='num'
                    if i<len(tokens) and tokens[i] in PERCENT: kind='percent'; i+=1
                    result.append((kind+':'+decimal_text(value),tokens[start:i])); matched=True; break
                if matched: break
        if matched: continue
        if not opaque and re.fullmatch(r'[+-]?(?:0|[1-9][0-9]*)(?:[.,][0-9]+)?',t):
            value=Decimal(t.replace(',','.')); i+=1; kind='num'
            if i<len(tokens) and tokens[i] in PERCENT: kind='percent'; i+=1
            result.append((kind+':'+decimal_text(value),tokens[start:i])); continue
        if not opaque:
            for end in range(min(i+6,len(tokens)),i,-1):
                number=integer(tokens[i:end])
                if number is None: continue
                i=end; kind='num'
                if i<len(tokens) and tokens[i] in PERCENT: kind='percent'; i+=1
                result.append((f'{kind}:{number}',tokens[start:i])); matched=True; break
        if matched: continue
        result.append((t,[t])); i+=1
    return result


def normalize(text: str) -> list[str]:
    return [value for value,_ in atoms(text)]


def distance(a,b) -> int:
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def score(reference: str,hypothesis: str,critical: list[str]) -> dict:
    ra,ha=atoms(reference),atoms(hypothesis); r=[x for x,_ in ra]; h=[x for x,_ in ha]
    markers={word for marker in critical for word in raw_words(marker)}
    critical_atoms={value for value,source in ra if markers.intersection(source)}
    # This is a lexical diagnostic, never authority. Semantic roles/values need independent review.
    mismatches=[{'atom':a,'reference_count':r.count(a),'hypothesis_count':h.count(a)} for a in sorted(critical_atoms) if r.count(a)!=h.count(a)]
    oldr,oldh=raw_words(reference),raw_words(hypothesis)
    return {'word_errors':distance(r,h),'words':len(r),'char_errors':distance(' '.join(r),' '.join(h)),'chars':len(' '.join(r)),
        'critical_token_errors':len(mismatches),'critical_mismatches':mismatches,'lexical_exact':r==h,
        'legacy':{'word_errors':distance(oldr,oldh),'words':len(oldr),'char_errors':distance(' '.join(oldr),' '.join(oldh)),
          'chars':len(' '.join(oldr)),'critical_mismatches':sum(oldr.count(x)!=oldh.count(x) for x in critical)}}


DIMENSIONS=('goal_deliverable','roles_scope','capability_intent','negation_cancel_correction','condition','values_entities_terms','constraints_order')


def load_cases(corpus: Path,dev: Path) -> dict:
    gold=json.loads(corpus.read_text(encoding='utf-8-sig')); old=json.loads(dev.read_text(encoding='utf-8-sig'))
    if sha_bytes(dev.read_bytes())!=gold['previous_dataset_sha256']: raise ValueError('development source digest mismatch')
    originals={x['id']:x for x in old['cases']}; cases={}
    for item in gold['development']:
        source=originals[item['id']]; cases[item['id']]={**source,'gold':item['gold'],'split':'dev'}
    for item in gold['holdout']: cases[item['id']]={**item,'split':'holdout'}
    if len(cases)!=32: raise ValueError('expected 32 unique cases')
    return cases


def percentile95(values):
    return sorted(values)[math.ceil(.95*len(values))-1] if values else None


def summarize(rows):
    first=[r for r in rows if r['iteration']==0]
    def ratio(error,denom): return sum(r[error] for r in first)/sum(r[denom] for r in first) if first else None
    timed=[r for r in rows if type(r.get('seconds')) in (int,float) and math.isfinite(r['seconds']) and r['seconds']>=0]
    with_duration=[r for r in timed if type(r.get('duration')) in (int,float) and math.isfinite(r['duration']) and r['duration']>0]
    return {'samples_iteration0':len(first),'observations':len(rows),'wer':ratio('word_errors','words'),'cer':ratio('char_errors','chars'),
        'critical_token_errors_iteration0':sum(r['critical_token_errors'] for r in first),
        'critical_token_errors_all_passes':sum(r['critical_token_errors'] for r in rows),
        'latency_p50':statistics.median(r['seconds'] for r in timed) if timed else None,
        'latency_p95':percentile95([r['seconds'] for r in timed]),
        'timing_observations':len(timed),'missing_or_invalid_timing_rows':len(rows)-len(with_duration),
        'raw_rtf_p95':percentile95([r['seconds']/r['duration'] for r in with_duration]),
        'per_file_budget_exceeded':sum(r['seconds']>max(5,0.5*r['duration']) for r in with_duration),
        'measurement_error_rows':sum(bool(r.get('error') or r.get('truncated')) for r in rows),
        'semantic_exact_raw':None,'semantic_status':'INDEPENDENT_REVIEW_REQUIRED','asr_decision':'NOT_EVALUATED_BY_SCORER'}


def main(args):
    cases=load_cases(args.corpus,args.dev_dataset)
    if args.split!='all': cases={k:v for k,v in cases.items() if v['split']==args.split}
    data=json.loads(args.hypotheses.read_text(encoding='utf-8-sig'))
    measurements=data['measurements']; rows=[]; tasks={}; seen=set()
    for raw in measurements:
        case=cases[raw['id']]; iteration=raw['iteration']; identity=(raw['id'],iteration)
        if identity in seen or type(iteration) is not int or iteration not in range(args.passes): raise ValueError('duplicate/out-of-range observation')
        seen.add(identity)
        hypothesis=raw.get('hypothesis')
        if not isinstance(hypothesis,str): raise ValueError('each observation needs raw synthetic hypothesis, possibly empty on explicit error')
        binding={'id':raw['id'],'iteration':iteration,'split':case['split'],'engine_blind_id':args.engine_id,
          'reference_sha256':sha_bytes(case['text'].encode()),'hypothesis_sha256':sha_bytes(hypothesis.encode())}
        rows.append({**{k:v for k,v in raw.items() if k!='hypothesis'},**binding,**score(case['text'],hypothesis,case['critical'])})
        key=(raw['id'],binding['hypothesis_sha256'])
        if key not in tasks:
            tasks[key]={**binding,'iterations':[],'reference':case['text'],'hypothesis':hypothesis,'gold':case['gold'],
                'dimensions':{x:None for x in DIMENSIONS},'semantic_exact_raw':None,'critical_semantic_failure':None,
                'reason':None,'reviewer_id':None,'note':'Complete independently of compiler; null is unresolved, not PASS.'}
        tasks[key]['iterations'].append(iteration)
    expected={(case,i) for case in cases for i in range(args.passes)}
    missing=sorted(expected-seen)
    output={'version':'c2-lexical-score-2.0.0','input_sha256':sha_bytes(args.hypotheses.read_bytes()),
      'corpus_gold_sha256':sha_bytes(args.corpus.read_bytes()),'scorer_sha256':sha_bytes(Path(__file__).read_bytes()),
      'complete':not missing,'missing':[{'id':id,'iteration':i} for id,i in missing],
      'rows':rows,'summary':summarize(rows),'by_split':{s:summarize([r for r in rows if r['split']==s]) for s in ('dev','holdout')}}
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'scores.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    worksheet={'version':'c2-semantic-review-2.0.0','corpus_gold_sha256':output['corpus_gold_sha256'],'input_sha256':output['input_sha256'],
       'engine_blind_id':args.engine_id,'tasks':list(tasks.values()),'policy':'Synthetic isolated evidence only; no model/compiler authority inference.'}
    (args.output/'semantic-review.json').write_text(json.dumps(worksheet,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'complete':not missing,'rows':len(rows),'review_tasks':len(tasks),'summary':output['summary']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--corpus',type=Path,default=HERE/'CORPUS-GOLD.json')
    p.add_argument('--dev-dataset',type=Path,required=True); p.add_argument('--hypotheses',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--engine-id',required=True)
    p.add_argument('--split',choices=('dev','holdout','all'),default='all'); p.add_argument('--passes',type=int,choices=(1,3),default=3)
    main(p.parse_args())
