#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, platform, shutil, socket, subprocess, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION='2.2.0'
TOKEN_HASH=os.environ.get('ITPZ_AGENT_TOKEN_HASH','').strip()
HOST=os.environ.get('ITPZ_AGENT_HOST','0.0.0.0')
PORT=int(os.environ.get('ITPZ_AGENT_PORT','8765'))
STATE=Path(os.environ.get('ITPZ_AGENT_STATE','/var/lib/itpz-agent'))
PACKAGES=STATE/'packages'; BACKUPS=STATE/'backups'; JOBS=STATE/'jobs'
ALLOWED={'apt-update','apt-upgrade','backup','install'}

def run(args, timeout=1800): return subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False)
def status():
 d=shutil.disk_usage('/'); up=int(float(Path('/proc/uptime').read_text().split()[0]))
 return {'status':'online','agent_version':VERSION,'hostname':socket.gethostname(),'fingerprint':hashlib.sha256(socket.gethostname().encode()).hexdigest(),'os_name':platform.platform(),'kernel':platform.release(),'disk_percent':round(d.used*100/d.total,1),'uptime_seconds':up,'docker_available':bool(shutil.which('docker')),'collected_at':time.time()}
def authorized(h):
 a=h.headers.get('Authorization','')
 return bool(TOKEN_HASH and a=='Bearer '+TOKEN_HASH)
def execute(action,payload):
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
   n=min(int(self.headers.get('Content-Length','0')),1024*1024); body=json.loads(self.rfile.read(n) or b'{}'); action=body.get('action',''); payload=body.get('payload') or {}
   if action not in ALLOWED: raise RuntimeError('Aktion nicht erlaubt')
   jid=str(uuid.uuid4()); result=execute(action,payload); result['job_id']=jid
   JOBS.mkdir(parents=True,exist_ok=True); (JOBS/f'{jid}.json').write_text(json.dumps(result),encoding='utf-8'); self.sendj(200,result)
  except Exception as e: self.sendj(400,{'state':'failed','error':str(e)})
 def log_message(self,*a): pass
if __name__=='__main__':
 for p in (STATE,PACKAGES,BACKUPS,JOBS): p.mkdir(parents=True,exist_ok=True)
 ThreadingHTTPServer((HOST,PORT),H).serve_forever()
