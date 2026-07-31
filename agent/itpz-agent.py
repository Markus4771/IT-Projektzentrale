#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, platform, re, shutil, socket, subprocess, time, uuid, tarfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION='2.3.0'
TOKEN_HASH=os.environ.get('ITPZ_AGENT_TOKEN_HASH','').strip()
HOST=os.environ.get('ITPZ_AGENT_HOST','0.0.0.0')
PORT=int(os.environ.get('ITPZ_AGENT_PORT','8765'))
STATE=Path(os.environ.get('ITPZ_AGENT_STATE','/var/lib/itpz-agent'))
PACKAGES=STATE/'packages'; BACKUPS=STATE/'backups'; JOBS=STATE/'jobs'; COMPOSE=Path('/srv/itpz-compose'); COMPOSE_BACKUPS=BACKUPS/'compose'
SLUG=re.compile(r'^[a-z0-9][a-z0-9-]{1,62}$')
ALLOWED={'apt-update','apt-upgrade','backup','install','compose-status','compose-up','compose-down','compose-restart','compose-pull','compose-update','compose-logs','compose-backup','compose-rollback'}

def run(args,timeout=1800,cwd=None): return subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False,cwd=cwd)
def status():
 d=shutil.disk_usage('/'); up=int(float(Path('/proc/uptime').read_text().split()[0]))
 return {'status':'online','agent_version':VERSION,'hostname':socket.gethostname(),'fingerprint':hashlib.sha256(socket.gethostname().encode()).hexdigest(),'os_name':platform.platform(),'kernel':platform.release(),'disk_percent':round(d.used*100/d.total,1),'uptime_seconds':up,'docker_available':bool(shutil.which('docker')),'compose_projects':len([p for p in COMPOSE.glob('*') if p.is_dir()]),'collected_at':time.time()}
def authorized(h): return bool(TOKEN_HASH and h.headers.get('Authorization','')=='Bearer '+TOKEN_HASH)
def compose_project(payload):
 slug=str(payload.get('slug','')).strip()
 if not SLUG.fullmatch(slug): raise RuntimeError('Ungültige Compose-ID')
 root=(COMPOSE/slug).resolve(); root.relative_to(COMPOSE.resolve())
 compose=root/'compose.yaml'
 if not compose.is_file(): compose=root/'docker-compose.yml'
 if not compose.is_file(): raise RuntimeError('Compose-Datei fehlt')
 return slug,root,compose

def compose_execute(action,payload):
 slug,root,compose=compose_project(payload); base=['/usr/bin/docker','compose','-f',str(compose)]
 if action=='compose-status': args=base+['ps','--format','json']
 elif action=='compose-up': args=base+['up','-d','--remove-orphans']
 elif action=='compose-down': args=base+['down']
 elif action=='compose-restart': args=base+['restart']
 elif action=='compose-pull': args=base+['pull']
 elif action=='compose-update':
  first=run(base+['pull'],cwd=root)
  if first.returncode: return {'state':'failed','output':first.stdout[-100000:],'error':first.stderr[-100000:]}
  args=base+['up','-d','--remove-orphans']
 elif action=='compose-logs': args=base+['logs','--no-color','--tail','300']
 elif action=='compose-backup':
  COMPOSE_BACKUPS.mkdir(parents=True,exist_ok=True); target=COMPOSE_BACKUPS/f'{slug}-{int(time.time())}.tar.gz'
  with tarfile.open(target,'w:gz') as archive: archive.add(root,arcname=slug,recursive=True)
  return {'state':'succeeded','output':str(target),'backup_file':target.name}
 elif action=='compose-rollback':
  name=Path(str(payload.get('backup_file',''))).name; backup=(COMPOSE_BACKUPS/name).resolve(); backup.relative_to(COMPOSE_BACKUPS.resolve())
  if not backup.is_file() or not name.startswith(slug+'-'): raise RuntimeError('Backup fehlt')
  tmp=COMPOSE/f'.restore-{slug}-{int(time.time())}'
  with tarfile.open(backup,'r:gz') as archive:
   for member in archive.getmembers():
    if member.name.startswith('/') or '..' in Path(member.name).parts or member.issym() or member.islnk(): raise RuntimeError('Unsicheres Backup')
   archive.extractall(tmp)
  restored=tmp/slug
  if root.exists(): shutil.rmtree(root)
  shutil.move(str(restored),str(root)); shutil.rmtree(tmp,ignore_errors=True)
  args=base+['up','-d','--remove-orphans']
 else: raise RuntimeError('Compose-Aktion nicht erlaubt')
 r=run(args,cwd=root); return {'state':'succeeded' if r.returncode==0 else 'failed','output':r.stdout[-100000:],'error':r.stderr[-100000:]}

def execute(action,payload):
 if action.startswith('compose-'): return compose_execute(action,payload)
 if action=='apt-update': cmd=['/usr/bin/apt-get','update']
 elif action=='apt-upgrade': cmd=['/usr/bin/apt-get','-y','upgrade']
 elif action=='backup':
  BACKUPS.mkdir(parents=True,exist_ok=True); p=BACKUPS/f'{int(time.time())}.txt'; p.write_text(json.dumps(status()),encoding='utf-8'); return {'state':'succeeded','output':str(p)}
 elif action=='install':
  name=Path(str(payload.get('package_file',''))).name; p=(PACKAGES/name).resolve(); p.relative_to(PACKAGES.resolve())
  if not p.is_file() or p.suffix!='.deb': raise RuntimeError('Paket fehlt')
  cmd=['/usr/bin/apt-get','install','-y',str(p)]
 else: raise RuntimeError('Aktion nicht erlaubt')
 r=run(cmd); return {'state':'succeeded' if r.returncode==0 else 'failed','output':r.stdout[-100000:],'error':r.stderr[-100000:]}
class H(BaseHTTPRequestHandler):
 def sendj(self,c,o):
  b=json.dumps(o).encode(); self.send_response(c); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  if not authorized(self): return self.sendj(401,{'error':'unauthorized'})
  if self.path=='/v1/status': return self.sendj(200,status())
  self.sendj(404,{'error':'not found'})
 def do_POST(self):
  if not authorized(self): return self.sendj(401,{'error':'unauthorized'})
  if self.path!='/v1/jobs': return self.sendj(404,{'error':'not found'})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if n<0 or n>1024*1024: raise RuntimeError('Anfrage zu groß')
   body=json.loads(self.rfile.read(n) or b'{}'); action=body.get('action',''); payload=body.get('payload') or {}
   if action not in ALLOWED: raise RuntimeError('Aktion nicht erlaubt')
   jid=str(uuid.uuid4()); result=execute(action,payload); result['job_id']=jid
   JOBS.mkdir(parents=True,exist_ok=True); (JOBS/f'{jid}.json').write_text(json.dumps(result),encoding='utf-8'); self.sendj(200,result)
  except Exception as e: self.sendj(400,{'state':'failed','error':str(e)})
 def log_message(self,*a): pass
if __name__=='__main__':
 for p in (STATE,PACKAGES,BACKUPS,JOBS,COMPOSE,COMPOSE_BACKUPS): p.mkdir(parents=True,exist_ok=True)
 ThreadingHTTPServer((HOST,PORT),H).serve_forever()
