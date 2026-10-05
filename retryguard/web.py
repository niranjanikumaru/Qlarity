"""Local interactive execution report: python -m retryguard.web."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile, ZIP_DEFLATED


def write_json(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,allow_nan=False,indent=2));tmp.replace(path)


def worker(request_path,folder):
    from .fixtures import fixtures, load_manifest
    from .diagnosis import diagnose_routine
    from .selection import compare, DEFAULT_WEIGHTS
    from .validation import InputError, validate_budget
    folder=Path(folder);request=json.loads(Path(request_path).read_text())
    state={'status':'running','stage':'load','diagnosis':None}
    def update(**values):
        state.update(values);write_json(folder/'state.json',state)
    try:
        timeout=request.get('timeout',.01);cap=request.get('max_attempts',16)
        validate_budget(timeout,cap)
        if not isinstance(request.get('require_source',False),bool):raise InputError('INVALID_FIELD','Source constraint must be boolean.','require_source')
        if request.get('example')=='upload':
            manifest=request.get('manifest');qasm=request.get('qasm')
            if not isinstance(manifest,list) or len(manifest)!=1 or not isinstance(manifest[0],dict):
                raise InputError('MANIFEST_ROOT','Upload one manifest item and its QASM file.','manifest')
            if not isinstance(qasm,str) or len(qasm)>200000:raise InputError('QASM_SIZE','QASM must be text, at most 200 KB.','qasm')
            # Server chooses the local filename; client paths are never opened.
            entry=dict(manifest[0]);entry['qasm']='input.qasm'
            (folder/'input.qasm').write_text(qasm);write_json(folder/'manifest.json',[entry])
            r=next(load_manifest(folder/'manifest.json'))
        else:
            r=next((r for r in fixtures() if r.name==request.get('example')),None)
            if r is None:raise InputError('UNKNOWN_EXAMPLE','Choose an example or upload files.','example')
        update(stage='diagnose')
        diagnosis=diagnose_routine(r)
        update(stage='repair_verify_compare',diagnosis=diagnosis)
        comparison=compare(r,folder/'circuits',timeout,cap,request.get('weights',DEFAULT_WEIGHTS),request.get('require_source',False))
        report={'run_id':folder.name,'request_sha256':hashlib.sha256(Path(request_path).read_bytes()).hexdigest(),
                'diagnosis':diagnosis,'comparison':comparison}
        write_json(folder/'report.json',report)
        verified=[c['qasm_file'] for c in comparison['candidates'] if c.get('verified')]
        with ZipFile(folder/'evidence.zip','w',ZIP_DEFLATED) as archive:
            for name in ('request.json','report.json'):
                archive.write(folder/name,name)
            for name in verified:archive.write(folder/'circuits'/name,'circuits/'+name)
        update(status='complete',stage='complete',report=report,
               downloads=['report.json','evidence.zip']+['circuits/'+n for n in verified])
    except InputError as error:
        update(status='rejected',stage='stopped',error=error.as_dict())
    except Exception as error:
        update(status='failed',stage='stopped',error={'code':'EXECUTION_ERROR','message':str(error)})


class App(ThreadingHTTPServer):
    def __init__(self,address,root):
        super().__init__(address,Handler);self.root=Path(root);self.token=uuid.uuid4().hex;self.slot=threading.BoundedSemaphore(1)
    def run_job(self,folder):
        try:
            with (folder/'worker.log').open('w') as log:
                result=subprocess.run([sys.executable,'-m','retryguard.web','--worker',str(folder/'request.json'),str(folder)],stdout=log,stderr=log,timeout=120)
            if result.returncode:
                write_json(folder/'state.json',{'status':'failed','error':{'code':'WORKER_EXIT','message':'Execution process failed. See local worker.log.'}})
        except subprocess.TimeoutExpired:
            write_json(folder/'state.json',{'status':'failed','error':{'code':'EXECUTION_TIMEOUT','message':'Execution exceeded the 120-second limit.'}})
        finally:self.slot.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,body,kind='application/json'):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(body)
    def json(self,status,value):self.send(status,json.dumps(value).encode())
    def allowed(self):return self.headers.get('Host') in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port))
    def do_GET(self):
        if not self.allowed():return self.json(403,{'error':'Local access only'})
        if self.path=='/':return self.send(200,Path(__file__).with_name('web.html').read_bytes(),'text/html; charset=utf-8')
        if self.path=='/api/config':return self.json(200,{'token':self.server.token})
        match=re.fullmatch(r'/api/runs/([a-f0-9]{32})(?:/(report.json|evidence.zip|circuits/(?:repaired_source|fixed_retry|selected_retry|deterministic)\.qasm))?',self.path)
        if not match:return self.json(404,{'error':'Not found'})
        folder=self.server.root/match[1]
        try:state=json.loads((folder/'state.json').read_text())
        except FileNotFoundError:return self.json(404,{'error':'Unknown run'})
        if match[2] is None:return self.json(200,state)
        if match[2] not in state.get('downloads',[]):return self.json(404,{'error':'Artifact not available'})
        data=(folder/match[2]).read_bytes()
        self.send(200,data,'application/zip' if match[2].endswith('.zip') else 'application/json' if match[2].endswith('.json') else 'text/plain')
    def do_POST(self):
        if not self.allowed() or self.headers.get('X-RetryGuard-Token')!=self.server.token:return self.json(403,{'error':'Reload the local app before running.'})
        if self.path!='/api/runs':return self.json(404,{'error':'Not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=300000:raise ValueError('Request limit is 300 KB.')
            request=json.loads(self.rfile.read(size))
            json.dumps(request,allow_nan=False)
            if not isinstance(request,dict):raise ValueError('Expected an object.')
        except (ValueError,UnicodeError) as error:return self.json(400,{'error':str(error)})
        if not self.server.slot.acquire(blocking=False):return self.json(429,{'error':'Another run is executing. Try again when it finishes.'})
        folder=self.server.root/uuid.uuid4().hex;folder.mkdir(parents=True)
        write_json(folder/'request.json',request);write_json(folder/'state.json',{'status':'running','stage':'load'})
        threading.Thread(target=self.server.run_job,args=(folder,),daemon=True).start()
        self.json(202,{'run_id':folder.name})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--runs',default='web_runs');parser.add_argument('--worker',nargs=2)
    args=parser.parse_args()
    if args.worker:return worker(*args.worker)
    root=Path(args.runs).resolve();root.mkdir(parents=True,exist_ok=True)
    server=App(('127.0.0.1',args.port),root)
    print(f'RetryGuard: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
