"""Exact owner-authorized comparator acquisition; no credentials or model execution."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'.runtime/asr-qualification/gigaam-onnx'
CAP=1_000_000_000
total=0
receipt=[]


def fetch(url, path, expected):
    global total
    if path.exists():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
        total+=path.stat().st_size
        assert total<=CAP
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(); size=0
    with urllib.request.urlopen(url,timeout=60) as response, path.open('xb') as out:
        while block:=response.read(1024*1024):
            total+=len(block); size+=len(block)
            if total>CAP: raise RuntimeError('authorized download budget exceeded')
            digest.update(block); out.write(block)
    if digest.hexdigest()!=expected: raise RuntimeError('download digest mismatch')
    receipt.append(dict(name=path.name,sha256=expected,bytes=size))
    (DEST/'download-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(path.name,size,flush=True)


for line in Path(__file__).with_name('comparator-requirements.txt').read_text().splitlines():
    pin, digest=line.split(' --hash=sha256:'); name, version=pin.split('==')
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as r: info=json.load(r)
    wheels=[u for u in info['urls'] if u['digests']['sha256']==digest and u['filename'].endswith('.whl')]
    assert len(wheels)==1 and not info.get('vulnerabilities')
    fetch(wheels[0]['url'],DEST/'wheelhouse'/wheels[0]['filename'],digest)

repo='istupakov/gigaam-v3-onnx'; rev='322c3b29492673eb7d0b434bfa9dfb8653e34d02'
files={
 'v3_e2e_rnnt_encoder.onnx':'cd60b3764a832e8560ae6d3ad0b10adc1a42ffae412b9476f25620aae4f4a508',
 'v3_e2e_rnnt_decoder.onnx':'7b0a16d67fd2cb37061decc93c69e364a9ab27afee3c57495d55b1c974cf7231',
 'v3_e2e_rnnt_joint.onnx':'602ff7017a93311aad34df1437c8d7f49911353c13d6eae7a6ee7b041339465c',
 'v3_e2e_rnnt_vocab.txt':'39abae20e692998290c574e606f11a9edef2902a1995463fcff63d1490cf22b7',
 'config.json':'0641fcf73f4af791c73f05083e38a658ff5dcbee3534a0c61396c10f4b97f0fe',
 'LICENSE.txt':'f00de6715714c7a63d08639cdbfaa40224eefc407302614bd19f1a8b98c875aa'}
for name,digest in files.items(): fetch(f'https://huggingface.co/{repo}/resolve/{rev}/{name}',DEST/'models'/name,digest)
# VAD is optional and separately pinned; fetch its config/license metadata before binaries.
print('authorized model and wheels complete',total,flush=True)
