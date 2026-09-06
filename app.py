from __future__ import annotations
import ast,builtins,importlib.util,json,os,sys,threading,time,webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
HOST='127.0.0.1';PORT=8765;INTERVAL=1
IGNORE={'.git','__pycache__','.venv','venv','node_modules','.idea','.vscode','build','dist'}
ROOT=Path(__file__).resolve().parent; HTML=ROOT/'index.html'; CSS=ROOT/'style.css'; FORGE=None

def stamp(): return datetime.now().strftime('%H:%M:%S')
def files(p):
 r=[]
 for root,dirs,names in os.walk(p):
  dirs[:]=[d for d in dirs if d not in IGNORE]
  r += [Path(root)/n for n in names if n.endswith('.py')]
 return r
def rel(p,f): return str(f.relative_to(p))
def issue(a,t,f,l,msg,title,sev): a.append({'type':t,'file':f,'line':l or 0,'message':msg,'title':title,'severity':sev})

class Names(ast.NodeVisitor):
 def __init__(self): self.defs=set();self.uses=[]
 def visit_Import(self,n):
  for x in n.names:self.defs.add(x.asname or x.name.split('.')[0])
 def visit_ImportFrom(self,n):
  for x in n.names:
   if x.name!='*':self.defs.add(x.asname or x.name)
 def visit_FunctionDef(self,n):
  self.defs.add(n.name)
  for x in list(n.args.posonlyargs)+list(n.args.args)+list(n.args.kwonlyargs):self.defs.add(x.arg)
  if n.args.vararg:self.defs.add(n.args.vararg.arg)
  if n.args.kwarg:self.defs.add(n.args.kwarg.arg)
  for x in n.body:self.visit(x)
 visit_AsyncFunctionDef=visit_FunctionDef
 def visit_ClassDef(self,n):
  self.defs.add(n.name)
  for x in n.body:self.visit(x)
 def visit_Name(self,n):
  if isinstance(n.ctx,ast.Store):self.defs.add(n.id)
  else:self.uses.append((n.id,n.lineno))

def undefined(t):
 a=Names();a.visit(t);out=[];seen=set();bi=set(dir(builtins))
 for n,l in a.uses:
  if n not in a.defs and n not in bi and (n,l) not in seen and not(n.startswith('__') and n.endswith('__')):seen.add((n,l));out.append((n,l))
 return out
class Bugs(ast.NodeVisitor):
 def __init__(self):self.a=[]
 def add(self,t,n,m,title,s='MEDIUM'):self.a.append({'type':t,'line':n,'message':m,'title':title,'severity':s})
 def visit_BinOp(self,n):
  if isinstance(n.op,(ast.Div,ast.FloorDiv,ast.Mod)) and isinstance(n.right,ast.Constant) and n.right.value==0:self.add('DIV_ZERO',n.lineno,'Literal zero is used as the divisor.','Division by zero','CRITICAL')
  self.generic_visit(n)
 def visit_While(self,n):
  if isinstance(n.test,ast.Constant) and n.test.value is True:self.add('INFINITE_LOOP_RISK',n.lineno,'Condition is always True; verify a reachable break.','Possible infinite loop')
  self.generic_visit(n)
 def visit_If(self,n):
  if isinstance(n.test,ast.Constant) and isinstance(n.test.value,bool) and ((n.test.value and n.orelse) or (not n.test.value and n.body)):self.add('CONSTANT_BRANCH',n.lineno,'This branch condition is constant.','Constant condition','LOW')
  self.generic_visit(n)
 def visit_Try(self,n):
  for h in n.handlers:
   if h.type is None:self.add('BARE_EXCEPT',h.lineno,'Bare except catches every exception.','Bare except')
  self.generic_visit(n)
 def visit_FunctionDef(self,n):
  if len(n.body)==1 and isinstance(n.body[0],ast.Pass):self.add('EMPTY_FUNCTION',n.lineno,'Function contains only pass.','Empty function','LOW')
  self.generic_visit(n)
 visit_AsyncFunctionDef=visit_FunctionDef
 def visit_Subscript(self,n):
  if isinstance(n.value,(ast.List,ast.Tuple)) and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,int):
   size=len(n.value.elts);i=n.slice.value
   if i>=size or i< -size:self.add('INDEX_ERROR',n.lineno,f'Index {i} is outside sequence length {size}.','Index out of range','HIGH')
  self.generic_visit(n)
 def visit_For(self,n):
  if isinstance(n.iter,(ast.List,ast.Tuple,ast.Set)) and not n.iter.elts:self.add('UNREACHABLE_LOOP',n.lineno,'Loop iterates over an empty literal.','Loop never executes','LOW')
  self.generic_visit(n)
class Forge:
 def __init__(self,p):self.p=p.resolve();self.issues=[];self.log=[];self.state={};self.num=0;self.stats={};self.live=True
 def emit(self,x):self.log.insert(0,f'[{stamp()}] {x}');self.log=self.log[:60];print(self.log[0])
 def snap(self):
  out={}
  for f in files(self.p):
   try:s=f.stat();out[str(f)]=(s.st_mtime_ns,s.st_size)
   except FileNotFoundError:pass
  return out
 def scan(self):
  start=time.perf_counter();out=[];fs=files(self.p);lines=funcs=classes=imports=0;local={f.stem for f in fs}
  for f in fs:
   try:s=f.read_text(encoding='utf-8',errors='replace');lines+=s.count('\n')+bool(s);t=ast.parse(s,filename=str(f))
   except SyntaxError as e:issue(out,'SYNTAX_ERROR',rel(self.p,f),e.lineno,e.msg,'Syntax error','CRITICAL');continue
   except Exception as e:issue(out,'READ_ERROR',rel(self.p,f),0,str(e),'Read error','HIGH');continue
   funcs+=sum(isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) for x in ast.walk(t));classes+=sum(isinstance(x,ast.ClassDef) for x in ast.walk(t));imports+=sum(isinstance(x,(ast.Import,ast.ImportFrom)) for x in ast.walk(t))
   for n,l in undefined(t):issue(out,'UNDEFINED_NAME',rel(self.p,f),l,f"'{n}' is used but not defined or imported.",f'Undefined name: {n}','HIGH')
   for x in ast.walk(t):
    if isinstance(x,ast.Import):mods=[z.name.split('.')[0] for z in x.names]
    elif isinstance(x,ast.ImportFrom) and x.module:mods=[x.module.split('.')[0]]
    else:mods=[]
    for m in mods:
     if m not in sys.stdlib_module_names and m not in local:
      try:ok=importlib.util.find_spec(m) is not None
      except Exception:ok=False
      if not ok:issue(out,'MISSING_PACKAGE',rel(self.p,f),x.lineno,f"Python cannot resolve '{m}'.",f'Missing package: {m}','HIGH')
   for b in Bugs().visit(t) or []:pass
   v=Bugs();v.visit(t)
   for b in v.a:b['file']=rel(self.p,f);out.append(b)
  self.issues=out;self.stats={'files':len(fs),'lines':lines,'functions':funcs,'classes':classes,'imports':imports,'ms':round((time.perf_counter()-start)*1000,1)};self.num+=1
 def watch(self):
  self.state=self.snap();self.scan();self.emit(f'Initial scan complete — {len(self.state)} Python files.')
  while self.live:
   time.sleep(INTERVAL);cur=self.snap()
   if cur==self.state:continue
   old=self.state;self.state=cur;changed=[Path(x).name for x in set(old)&set(cur) if old[x]!=cur[x]];added=[Path(x).name for x in set(cur)-set(old)];removed=[Path(x).name for x in set(old)-set(cur)];self.scan()
   if added:self.emit('FILE ADDED  :: '+', '.join(added))
   if changed:self.emit('FILE CHANGED :: '+', '.join(changed))
   if removed:self.emit('FILE REMOVED :: '+', '.join(removed))
 def data(self):
  gaps=[x for x in self.issues if x['type'] in {'UNDEFINED_NAME','MISSING_PACKAGE','SYNTAX_ERROR','READ_ERROR'}];bugs=[x for x in self.issues if x not in gaps];c=sum(x['severity']=='CRITICAL' for x in self.issues);h=sum(x['severity']=='HIGH' for x in self.issues);score=max(0,100-c*15-h*7-max(0,len(self.issues)-c-h)*2)
  return {'project':str(self.p),'watching':self.live,'scan':self.num,'last':stamp(),'health':score,'stats':self.stats,'summary':{'total':len(self.issues),'critical':c,'high':h},'shortages':gaps,'bugs':bugs,'activity':self.log}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def out(self,b,typ):self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
 def do_GET(self):
  p=urlparse(self.path).path
  if p=='/':return self.out(HTML.read_bytes(),'text/html; charset=utf-8')
  if p=='/style.css':return self.out(CSS.read_bytes(),'text/css; charset=utf-8')
  if p=='/api/state':return self.out(json.dumps(FORGE.data()).encode(),'application/json')
  self.send_error(404)
def main():
 global FORGE
 raw=input('Project folder > ').strip().strip('"');p=Path(raw).expanduser()
 while not p.is_dir():print('Folder not found.');raw=input('Project folder > ').strip().strip('"');p=Path(raw).expanduser()
 FORGE=Forge(p);threading.Thread(target=FORGE.watch,daemon=True).start();url=f'http://{HOST}:{PORT}';print(f'PROJECT FORGE :: {url}');webbrowser.open(url);ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
if __name__=='__main__':main()
