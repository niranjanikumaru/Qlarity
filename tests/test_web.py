import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zipfile import ZipFile
import io
from retryguard.web import App, worker, write_json

class WebExecution(unittest.TestCase):
    def test_real_http_run_download_and_request_guard(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(('127.0.0.1',0),d);thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(app.server_port)
            try:
                page=urlopen(base+'/').read();self.assertIn(b'No precomputed scores',page)
                config=json.load(urlopen(base+'/api/config'))
                data=json.dumps({'example':'gearbox','timeout':.01,'max_attempts':16}).encode()
                with self.assertRaises(HTTPError) as e:urlopen(Request(base+'/api/runs',data=data))
                self.assertEqual(e.exception.code,403)
                request=Request(base+'/api/runs',data=data,headers={'X-RetryGuard-Token':config['token']})
                run=json.load(urlopen(request))['run_id']
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    state=json.load(urlopen(base+'/api/runs/'+run))
                    if state['status']!='running':break
                    time.sleep(.1)
                self.assertEqual(state['status'],'complete',state)
                self.assertEqual(state['report']['comparison']['recommendation']['policy'],'deterministic')
                self.assertTrue(all(c['verified'] for c in state['report']['comparison']['candidates']))
                archive=ZipFile(io.BytesIO(urlopen(base+'/api/runs/'+run+'/evidence.zip').read()))
                self.assertIn('circuits/repaired_source.qasm',archive.namelist())
                self.assertEqual(json.loads(archive.read('report.json'))['run_id'],run)
                with self.assertRaises(HTTPError):urlopen(base+'/api/runs/'+run+'/request.json')
            finally:app.shutdown();app.server_close();thread.join()

    def test_upload_rejection_retains_diagnosis_and_no_downloads(self):
        from qiskit import qasm3
        from retryguard.fixtures import fixtures
        r=next(fixtures())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);entry={'name':'wrong_target','qasm':'ignored.qasm','target_real':[[1,0],[0,1]],'target_imag':[[0,0],[0,0]],'source':'test','lineage':'test'}
            write_json(p/'request.json',{'example':'upload','manifest':[entry],'qasm':qasm3.dumps(r.trial),'timeout':.01,'max_attempts':16})
            worker(p/'request.json',p);state=json.loads((p/'state.json').read_text())
            self.assertEqual(state['status'],'rejected');self.assertEqual(state['error']['code'],'TARGET_MISMATCH')
            self.assertIsNotNone(state['diagnosis']);self.assertNotIn('downloads',state)

    def test_input_validation_prevents_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);write_json(p/'request.json',{'example':'gearbox','max_attempts':100})
            worker(p/'request.json',p);state=json.loads((p/'state.json').read_text())
            self.assertEqual(state['status'],'rejected');self.assertIsNone(state['diagnosis'])
