from __future__ import annotations
import json,threading,time,webbrowser
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,unquote,urlparse
from scanner import source_files,read_text,rel,analyze
from graph_engine import build_graph,graph_metrics

HOST,PORT,INTERVAL='127.0.0.1',8765,1.0
HERE=Path(__file__).resolve().parent
FORGE=None

def stamp():return datetime.now().strftime('%H:%M:%S')

class Forge:
    def __init__(self,project):
        self.project=project.resolve();self.lock=threading.RLock();self.scan_id=0;self.state={};self.history=[];self.activity=[];self.snapshot={};self.live=True
    def emit(self,msg):
        with self.lock:self.activity.insert(0,f'[{stamp()}] {msg}');self.activity=self.activity[:160]
        print(self.activity[0])
    def snap(self):
        out={}
        for f in source_files(self.project):
            try:s=f.stat();out[rel(self.project,f)]=(s.st_mtime_ns,s.st_size)
            except FileNotFoundError:pass
        return out
    def scan(self):
        started=time.perf_counter();result=analyze(self.project);nodes,edges=build_graph(self.project,[self.project/x['path'] for x in result['files']],{self.project/x['path']:read_text(self.project/x['path']) for x in result['files']});gm=graph_metrics(nodes,edges);issues=result['issues'];sev=result['severity'];self.scan_id+=1
        tests=result['tests'];test_ratio=round(100*len(tests)/max(1,len(result['files'])),1)
        history_item={'scan':self.scan_id,'time':stamp(),'health':result['health'],'issues':len(issues),'critical':sev.get('CRITICAL',0),'high':sev.get('HIGH',0)}
        with self.lock:
            self.history.append(history_item);self.history=self.history[-80:]
            self.state={'project':str(self.project),'watching':self.live,'scan':self.scan_id,'duration_ms':round((time.perf_counter()-started)*1000,1),'health':result['health'],'stats':{'files':len(result['files']),'lines':result['metrics'].get('lines',0),'functions':result['metrics'].get('functions',0),'classes':result['metrics'].get('classes',0),'imports':result['metrics'].get('imports',0),'bytes':result['metrics'].get('bytes',0)},'languages':result['languages'],'issues':issues,'shortages':issues[:30],'bugs':issues,'summary':{'total':len(issues),'critical':sev.get('CRITICAL',0),'high':sev.get('HIGH',0),'medium':sev.get('MEDIUM',0),'low':sev.get('LOW',0)},'dna':result['dna'],'security':[x for x in issues if x['type'] in {'SECRET','DANGEROUS_EXEC','COMMAND_EXEC','SQL_INJECTION','DOM_XSS','UNSAFE_DESERIALIZE','PASSWORD_LITERAL'}],'graph':{'nodes':nodes,'edges':edges,'metrics':gm},'files':result['files'],'tests':{'files':tests,'coverage_proxy':test_ratio,'count':len(tests)},'history':self.history,'activity':self.activity}
        self.snapshot=self.snap();self.emit(f'SCAN #{self.scan_id:03d} // {len(result["files"])} files // health {result["health"]}')
    def watch(self):
        self.scan();last=self.snapshot
        while self.live:
            time.sleep(INTERVAL)
            now=self.snap()
            if now!=last:
                changed=sorted(set(last)^set(now));self.emit(f'CHANGE DETECTED // {changed[0] if changed else "project"}');self.scan();last=self.snapshot
    def search(self,q):
        q=q.lower().strip();out=[]
        for f in source_files(self.project):
            text=read_text(f)
            for i,line in enumerate(text.splitlines(),1):
                if q and q in line.lower():out.append({'file':rel(self.project,f),'line':i,'text':line[:320]})
                if len(out)>=250:return out
        return out

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def send_json(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path);p=u.path;qs=parse_qs(u.query)
        if p=='/':return self.html()
        if p=='/style.css':return self.static('style.css','text/css')
        if p=='/api/state':
            with FORGE.lock:data=dict(FORGE.state)
            return self.send_json(data)
        if p=='/api/graph':return self.send_json(FORGE.state.get('graph',{}))
        if p=='/api/search':return self.send_json({'results':FORGE.search(qs.get('q',[''])[0])})
        if p=='/api/file':
            path=unquote(qs.get('path',[''])[0]);target=(FORGE.project/path).resolve()
            if FORGE.project not in target.parents or not target.is_file():return self.send_json({'error':'file not found'},404)
            return self.send_json({'path':rel(FORGE.project,target),'language':target.suffix.lower(),'content':read_text(target)})
        if p=='/api/export':return self.send_json(FORGE.state)
        self.send_json({'error':'not found'},404)
    def html(self):
        try:raw=(HERE/'index.html').read_bytes()
        except FileNotFoundError:return self.send_json({'error':'index missing'},500)
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def static(self,name,ctype):
        try:raw=(HERE/name).read_bytes()
        except FileNotFoundError:return self.send_json({'error':'asset missing'},404)
        self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def choose_project():
    import tkinter as tk
    from tkinter import filedialog
    root=tk.Tk();root.withdraw();p=filedialog.askdirectory(title='PROJECT FORGE // Select project folder');root.destroy()
    if not p:raise SystemExit('No project selected.')
    return Path(p)

def main():
    global FORGE
    project=choose_project();FORGE=Forge(project);threading.Thread(target=FORGE.watch,daemon=True).start();server=ThreadingHTTPServer((HOST,PORT),Handler);url=f'http://{HOST}:{PORT}';print(f'PROJECT FORGE // {url}');webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:FORGE.live=False;server.server_close()

if __name__=='__main__':main()
