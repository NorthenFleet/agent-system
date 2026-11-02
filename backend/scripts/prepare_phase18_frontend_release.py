"""Narrow, additive frontend release with content-checked index rollback.

The pre-edit component hash matches the previously verified phase15/17 release.
Keep old chunks for existing tabs. Publish/rollback atomically replaces only index.html.
"""
import hashlib,json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LAB=ROOT/'docs/review/computer-use-phase18-20261008'
PROD=ROOT/'frontend-v2/dist'
CANDIDATE=Path('/private/tmp/agent-system-phase18-candidate')
PACKAGE=LAB/'release'
NEW=Path('/private/tmp/agent-system-phase18-dist/assets')
BASE=Path('/private/tmp/agent-system-phase18-baseline/dist/assets')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace_index(data):
 temp=PROD/'index.phase18.tmp';temp.write_bytes(data);temp.replace(PROD/'index.html')
if '--rollback' in sys.argv:
 manifest=json.loads((LAB/'release-manifest.json').read_text())
 assert sha(PROD/'index.html')==manifest['new_index_sha256'],'Live index changed; do not overwrite'
 assert sha(LAB/'index-before.html')==manifest['old_index_sha256'],'Backup changed'
 replace_index((LAB/'index-before.html').read_bytes())
 print('Rolled back index; additive assets retained');sys.exit()
if '--publish' in sys.argv:
 manifest=json.loads((LAB/'release-manifest.json').read_text())
 assert sha(PROD/'index.html')==manifest['old_index_sha256'],'Live index changed; rebuild candidate'
 assert all(sha(PROD/rel)==h for rel,h in manifest['unchanged_production_files'].items()),'Production assets changed; recheck scope'
 assert all(sha(PACKAGE/rel)==h for rel,h in manifest['new_assets'].items())
 assert sha(PACKAGE/'index.html')==manifest['new_index_sha256']
 for rel,h in manifest['new_assets'].items():
  target=PROD/rel
  if target.exists():assert sha(target)==h,'Content collision'
  else:shutil.copy2(PACKAGE/rel,target)
 replace_index((PACKAGE/'index.html').read_bytes())
 assert sha(PROD/'index.html')==manifest['new_index_sha256']
 print('Published three additive assets and index; previous chunks retained');sys.exit()
assert not CANDIDATE.exists() and not (LAB/'release-manifest.json').exists(),'One-shot preparation'
baseline=json.loads((ROOT/'docs/review/computer-use-phase15-20261007/source-hashes.json').read_text())
assert sha(LAB/'CommandCenter-before.vue')==baseline['frontend-v2/src/views/CommandCenter.vue']
new_names=['CommandCenter-Cq-oCBUg.js', 'CommandCenter-B6uRAkkj.css']
for name in new_names:
 for dep in re.findall(r'"\./([^"/]+\.(?:js|css))"',(NEW/name).read_text()):
  if dep not in new_names:assert (NEW/dep).read_bytes()==(PROD/'assets'/dep).read_bytes(),dep

shutil.copytree(PROD,CANDIDATE)
for name in new_names:shutil.copy2(NEW/name,CANDIDATE/'assets'/name)
entry=PROD/'assets/main-phase17-895d3da4dd47.js';data=entry.read_text()
for old,new in [('CommandCenter-CS5wr00t.js',new_names[0]),('CommandCenter-2eTYgWrM.css',new_names[1])]:
 assert old in data;data=data.replace(old,new)
new_entry='main-phase18-'+hashlib.sha256(data.encode()).hexdigest()[:12]+'.js'
(CANDIDATE/'assets'/new_entry).write_text(data)
index=(PROD/'index.html').read_text();assert entry.name in index
(CANDIDATE/'index.html').write_text(index.replace(entry.name,new_entry))
shutil.copy2(PROD/'index.html',LAB/'index-before.html')
assets={str(p.relative_to(CANDIDATE)):sha(p) for p in [CANDIDATE/'assets'/n for n in new_names+[new_entry]]}
manifest={'old_index_sha256':sha(PROD/'index.html'),'new_index_sha256':sha(CANDIDATE/'index.html'),'new_assets':assets,'old_entry':entry.name,'new_entry':new_entry,'unchanged_production_files':{str(f.relative_to(PROD)):sha(f) for f in PROD.rglob('*') if f.is_file() and f.name!='index.html'}}
(LAB/'release-manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'new_assets':list(assets),'changed_existing_files':['index.html']},indent=2))
for rel in ['index.html',*assets]:
 target=PACKAGE/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(CANDIDATE/rel,target)
