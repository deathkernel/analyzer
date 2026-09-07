from __future__ import annotations
import json
import socket
import threading
import time
import subprocess
import tempfile
import shutil
import sys
import traceback
import webbrowser
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,unquote,urlparse

from scanner import source_files,read_text,rel,analyze
from graph_engine import build_graph,graph_metrics,intelligence_report
from exception_engine import analyze_exceptions

HOST="127.0.0.1"
DEFAULT_PORT=8765
INTERVAL=1.0
HERE=Path(__file__).resolve().parent
FORGE=None

ASSETS={
    "/style.css":("style.css","text/css; charset=utf-8"),
    "/graph-cinema.css":("graph-cinema.css","text/css; charset=utf-8"),
    "/graph-controls-plus.css":("graph-controls-plus.css","text/css; charset=utf-8"),
    "/forge-ui.js":("forge-ui.js","application/javascript; charset=utf-8"),
    "/graph-controls-plus.js":("graph-controls-plus.js","application/javascript; charset=utf-8"),
    "/exception-ui.js":("exception-ui.js","application/javascript; charset=utf-8"),
}

def stamp():return datetime.now().strftime("%H:%M:%S")

def pick_port(preferred=DEFAULT_PORT):
    for port in range(preferred,preferred+20):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:s.bind((HOST,port));return port
            except OSError:continue
    raise OSError("Could not find a free local port.")

class Forge:
    def __init__(self,project:Path):
        self.project=project.resolve();self.lock=threading.RLock();self.scan_id=0
        self.state={"project":str(self.project),"watching":False,"scan":0,"duration_ms":0,"health":100,
                    "stats":{"files":0,"lines":0,"functions":0,"classes":0,"imports":0,"bytes":0},
                    "languages":{},"issues":[],"shortages":[],"bugs":[],"summary":{"total":0,"critical":0,"high":0,"medium":0,"low":0},
                    "dna":{"complexity":100,"coupling":100,"duplication":100,"security":100,"maintainability":100,"architecture":"EMPTY"},
                    "security":[],"exception_safety":{"score":100,"handlers":0,"risky_findings":0,"metrics":{},"recovery":{"logged":0,"reraised":0,"swallowed":0},"analysis_errors":[]},
                    "graph":{"nodes":[],"edges":[],"metrics":{}},"intelligence":{"cycles":[],"cycle_count":0,"impact":{"focused":None,"upstream":[],"downstream":[],"blast_radius":0},"xray":{"roles":{},"entrypoints":[],"data_nodes":0,"flows":[]},"dead_code":[]},"files":[],
                    "tests":{"files":[],"coverage_proxy":0,"count":0},"history":[],"activity":[],"error":None}
        self.history=[];self.activity=[];self.snapshot={};self.live=True

    def emit(self,message):
        line=f"[{stamp()}] {message}"
        with self.lock:
            self.activity.insert(0,line);self.activity=self.activity[:160]
        print(line,flush=True)

    def snap(self):
        out={}
        try:files=source_files(self.project)
        except Exception:return out
        for f in files:
            try:
                s=f.stat();out[rel(self.project,f)]=(s.st_mtime_ns,s.st_size)
            except OSError:pass
        return out

    def scan(self):
        started=time.perf_counter()
        try:
            result=analyze(self.project);files_abs=[self.project/x["path"] for x in result["files"]]
            contents={f:read_text(f) for f in files_abs};nodes,edges=build_graph(self.project,files_abs,contents);gm=graph_metrics(nodes,edges)
            intel=intelligence_report(nodes,edges,contents)
            exception_report=analyze_exceptions(files_abs,contents,self.project)
            issues=[];seen_issue_keys=set()
            for item in list(result["issues"])+list(exception_report["findings"]):
                key=(item.get("type"),item.get("file"),item.get("line"),item.get("title"))
                if key not in seen_issue_keys:
                    seen_issue_keys.add(key);issues.append(item)
            sev=Counter(x["severity"] for x in issues);self.scan_id+=1;tests=result["tests"]
            base_health=result["health"];exception_health=exception_report["score"]
            health=max(0,min(base_health,round((base_health*0.8)+(exception_health*0.2))))
            test_ratio=round(100*len(tests)/max(1,len(result["files"])),1)
            history_item={"scan":self.scan_id,"time":stamp(),"health":health,"issues":len(issues),"critical":sev.get("CRITICAL",0),"high":sev.get("HIGH",0)}
            with self.lock:
                self.history.append(history_item);self.history=self.history[-80:]
                self.state.update({
                    "project":str(self.project),"watching":self.live,"scan":self.scan_id,
                    "duration_ms":round((time.perf_counter()-started)*1000,1),"health":health,
                    "stats":{"files":len(result["files"]),"lines":result["metrics"].get("lines",0),"functions":result["metrics"].get("functions",0),
                             "classes":result["metrics"].get("classes",0),"imports":result["metrics"].get("imports",0),"bytes":result["metrics"].get("bytes",0)},
                    "languages":result["languages"],"issues":issues,"shortages":issues[:30],"bugs":issues,
                    "summary":{"total":len(issues),"critical":sev.get("CRITICAL",0),"high":sev.get("HIGH",0),"medium":sev.get("MEDIUM",0),"low":sev.get("LOW",0)},
                    "dna":result["dna"],
                    "security":[x for x in issues if x["type"] in {"SECRET","DANGEROUS_EXEC","COMMAND_EXEC","SQL_INJECTION","DOM_XSS","UNSAFE_DESERIALIZE","PASSWORD_LITERAL"}],
                    "exception_safety":exception_report,
                    "graph":{"nodes":nodes,"edges":edges,"metrics":gm},"intelligence":intel,"files":result["files"],
                    "tests":{"files":tests,"coverage_proxy":test_ratio,"count":len(tests)},
                    "history":list(self.history),"activity":list(self.activity),"error":None,
                })
            self.snapshot=self.snap();self.emit(f'SCAN #{self.scan_id:03d} // {len(result["files"])} files // health {health} // exception safety {exception_health}')
        except Exception as exc:
            error=f"{type(exc).__name__}: {exc}";traceback.print_exc()
            with self.lock:
                self.state["watching"]=self.live;self.state["error"]=error;self.state["duration_ms"]=round((time.perf_counter()-started)*1000,1)
            self.emit("SCAN ERROR // "+error)

    def watch(self):
        self.scan();last=self.snapshot
        while self.live:
            time.sleep(INTERVAL);now=self.snap()
            if now!=last:
                changed=sorted(set(last)^set(now))
                self.emit(f'CHANGE DETECTED // {changed[0] if changed else "project"}');self.scan();last=self.snapshot

    def search(self,query):
        q=query.lower().strip()
        if not q:return []
        out=[]
        for f in source_files(self.project):
            text=read_text(f)
            for line_no,line in enumerate(text.splitlines(),1):
                if q in line.lower():
                    out.append({"file":rel(self.project,f),"line":line_no,"text":line[:320]})
                    if len(out)>=250:return out
        return out

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_args):pass

    def send_json(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate");self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)

    def static(self,name,content_type):
        path=(HERE/name).resolve()
        if HERE not in path.parents or not path.is_file():return self.send_json({"error":"asset missing","asset":name},404)
        raw=path.read_bytes();self.send_response(200);self.send_header("Content-Type",content_type)
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate");self.send_header("Content-Length",str(len(raw)))
        self.end_headers();self.wfile.write(raw)

    def do_GET(self):
        try:
            u=urlparse(self.path);p=u.path;qs=parse_qs(u.query)
            if p=="/":return self.static("index.html","text/html; charset=utf-8")
            if p in ASSETS:
                name,ctype=ASSETS[p];return self.static(name,ctype)
            if p=="/api/state":
                with FORGE.lock:return self.send_json(dict(FORGE.state))
            if p=="/api/graph":
                with FORGE.lock:return self.send_json(dict(FORGE.state.get("graph",{})))
            if p=="/api/search":return self.send_json({"results":FORGE.search(qs.get("q",[""])[0])})
            if p=="/api/file":
                path=unquote(qs.get("path",[""])[0]).replace("\\","/");target=(FORGE.project/path).resolve()
                if FORGE.project not in target.parents or not target.is_file():return self.send_json({"error":"file not found"},404)
                return self.send_json({"path":rel(FORGE.project,target),"language":target.suffix.lower(),"content":read_text(target)})
            if p=="/api/health":return self.send_json({"ok":True,"scan":FORGE.scan_id,"error":FORGE.state.get("error")})
            return self.send_json({"error":"not found","path":p},404)
        except Exception as exc:return self.send_json({"error":f"{type(exc).__name__}: {exc}"},500)

def github_project(url):
    if not (url.startswith("https://github.com/") or url.startswith("http://github.com/") or url.startswith("git@github.com:")):
        raise ValueError("Only GitHub repository URLs are supported.")
    base=Path(tempfile.mkdtemp(prefix="forge-github-"));target=base/"repository"
    print(f"FORGE // cloning {url}")
    try:subprocess.run(["git","clone","--depth","1","--no-tags",url,str(target)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    except FileNotFoundError:
        shutil.rmtree(base,ignore_errors=True);raise RuntimeError("Git is not installed or not available on PATH.")
    except subprocess.CalledProcessError as exc:
        output=(exc.stdout or "").strip();shutil.rmtree(base,ignore_errors=True);raise RuntimeError("GitHub clone failed"+(": "+output[-500:] if output else "."))
    return target,base

def choose_project():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk();root.withdraw();root.attributes("-topmost",True)
        selected=filedialog.askdirectory(title="PROJECT FORGE // Select project folder");root.destroy()
        if selected:return Path(selected)
    except Exception as exc:print(f"Folder dialog unavailable: {exc}")
    print("\nPROJECT FORGE // Enter the project folder path");value=input("Project path: ").strip().strip('"')
    if not value:raise SystemExit("No project selected.")
    return Path(value)

def main():
    global FORGE
    temp_workspace=None
    if len(sys.argv)>=3 and sys.argv[1].lower()=="--github":
        try:project,temp_workspace=github_project(sys.argv[2])
        except Exception as exc:raise SystemExit(f"FORGE // {exc}")
    else:project=choose_project()
    if not project.exists() or not project.is_dir():raise SystemExit(f"Invalid project folder: {project}")
    port=pick_port();FORGE=Forge(project)
    threading.Thread(target=FORGE.watch,daemon=True,name="forge-watcher").start()
    server=ThreadingHTTPServer((HOST,port),Handler);url=f"http://{HOST}:{port}"
    print("="*62);print("PROJECT FORGE // LOCAL CODE INTELLIGENCE");print(f"TARGET : {project}");print(f"UI     : {url}");print("STOP   : Ctrl+C");print("="*62)
    try:webbrowser.open(url)
    except Exception:pass
    try:server.serve_forever()
    except KeyboardInterrupt:print("\nFORGE // shutting down")
    finally:
        FORGE.live=False;server.server_close()
        if temp_workspace:shutil.rmtree(temp_workspace,ignore_errors=True)

if __name__=="__main__":main()
