from __future__ import annotations
import ast, hashlib, json, os, re, sys, threading, time, webbrowser
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HOST='127.0.0.1'; PORT=8765; INTERVAL=1.0
ROOT=Path(__file__).resolve().parent; HTML=ROOT/'index.html'; CSS=ROOT/'style.css'; FORGE=None
IGNORE={'.git','.hg','.svn','__pycache__','.venv','venv','env','node_modules','.idea','.vscode','build','dist','target','bin','obj','.next','.nuxt','coverage'}
LANG={
'.py':'Python','.js':'JavaScript','.jsx':'JavaScript JSX','.ts':'TypeScript','.tsx':'TypeScript JSX','.java':'Java','.c':'C','.h':'C/C++','.cpp':'C++','.cc':'C++','.hpp':'C++','.cs':'C#','.go':'Go','.rs':'Rust','.rb':'Ruby','.php':'PHP','.swift':'Swift','.kt':'Kotlin','.kts':'Kotlin','.dart':'Dart','.scala':'Scala','.sh':'Shell','.bash':'Shell','.zsh':'Shell','.ps1':'PowerShell','.sql':'SQL','.html':'HTML','.css':'CSS','.scss':'SCSS','.vue':'Vue','.svelte':'Svelte','.xml':'XML','.json':'JSON','.yaml':'YAML','.yml':'YAML','.toml':'TOML','.r':'R','.lua':'Lua','.ex':'Elixir','.exs':'Elixir','.erl':'Erlang','.fs':'F#','.fsx':'F#','.m':'Objective-C','.mm':'Objective-C++'}
CODE_EXT=set(LANG); TEST_RE=re.compile(r'(^|[/\\])(test[s]?|spec[s]?)([/\\]|$)|(^|[/\\])test_[^/\\]+|[^/\\]+_(test|spec)\.[^.]+$',re.I)
SECRET_RE=re.compile(r'(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key)\s*[:=]\s*["\'][^"\']{8,}["\']')

def stamp(): return datetime.now().strftime('%H:%M:%S')
def rel(root,p):
    try:return str(p.relative_to(root)).replace('\\','/')
    except ValueError:return str(p)
def files(root):
    out=[]
    for base,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in IGNORE]
        out += [Path(base)/n for n in names if Path(n).suffix.lower() in CODE_EXT]
    return out
def lang(p): return LANG.get(p.suffix.lower(),'Other')
def add(a,t,f,l,msg,title,sev='MEDIUM',extra=None):
    x={'type':t,'file':f,'line':int(l or 0),'message':msg,'title':title,'severity':sev}
    if extra:x.update(extra)
    a.append(x)
def read(p):
    try:return p.read_text(encoding='utf-8',errors='replace')
    except Exception:return ''
def normalized_lines(s):
    return [re.sub(r'\s+',' ',re.sub(r'//.*|#.*$','',x)).strip() for x in s.splitlines()]

def py_ast(source,path,root,issues,metrics):
    try: tree=ast.parse(source,filename=str(path))
    except SyntaxError as e:
        add(issues,'SYNTAX_ERROR',rel(root,path),e.lineno,e.msg or 'Invalid syntax.','Syntax error','CRITICAL'); return
    metrics['functions']+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree)); metrics['classes']+=sum(isinstance(n,ast.ClassDef) for n in ast.walk(tree)); metrics['imports']+=sum(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(tree))
    defs=set(dir(__builtins__)) if isinstance(__builtins__,dict) else set(dir(__builtins__))
    defs.update({'self','cls'})
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            for x in n.names: defs.add(x.asname or x.name.split('.')[0])
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): defs.add(n.name)
        elif isinstance(n,ast.arg): defs.add(n.arg)
        elif isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store): defs.add(n.id)
    for n in ast.walk(tree):
        if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id not in defs and not(n.id.startswith('__') and n.id.endswith('__')):
            add(issues,'UNDEFINED_NAME',rel(root,path),n.lineno,f"'{n.id}' is used but is not defined or imported in this module.",f'Undefined name: {n.id}','HIGH')
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Div,ast.FloorDiv,ast.Mod)) and isinstance(n.right,ast.Constant) and n.right.value==0:add(issues,'DIV_ZERO',rel(root,path),n.lineno,'Literal zero is used as the divisor.','Division by zero','CRITICAL')
        if isinstance(n,ast.While) and isinstance(n.test,ast.Constant) and n.test.value is True:add(issues,'INFINITE_LOOP_RISK',rel(root,path),n.lineno,'Condition is always True; verify a reachable break.','Possible infinite loop','MEDIUM')
        if isinstance(n,ast.Try):
            for h in n.handlers:
                if h.type is None:add(issues,'BARE_EXCEPT',rel(root,path),h.lineno,'Bare except catches every exception.','Bare except','MEDIUM')
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and len(n.body)==1 and isinstance(n.body[0],ast.Pass):add(issues,'EMPTY_FUNCTION',rel(root,path),n.lineno,'Function body contains only pass.','Empty function','LOW')
        if isinstance(n,ast.Subscript) and isinstance(n.value,(ast.List,ast.Tuple)) and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,int):
            size=len(n.value.elts);i=n.slice.value
            if i>=size or i< -size:add(issues,'INDEX_ERROR',rel(root,path),n.lineno,f'Index {i} is outside literal sequence length {size}.','Index out of range','HIGH')
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            mods=[]
            if isinstance(n,ast.Import):mods=[x.name.split('.')[0] for x in n.names]
            elif n.module:mods=[n.module.split('.')[0]]
            for m in mods: metrics['deps'].add(m)

def generic_analysis(source,p,issues,metrics):
    relpath=str(p).replace('\\','/'); extension=p.suffix.lower(); lines=source.splitlines()
    metrics['lines']+=len(lines); metrics['bytes']+=len(source.encode('utf-8',errors='ignore')); metrics['comments']+=sum(bool(re.match(r'^\s*(#|//|/\*|\*|<!--|--|;)',x)) for x in lines)
    metrics['long_lines']+=sum(len(x)>140 for x in lines)
    metrics['tests']+=bool(TEST_RE.search(relpath))
    for i,line in enumerate(lines,1):
        low=line.lower()
        if SECRET_RE.search(line) and not any(x in low for x in ('example','sample','dummy','placeholder','changeme')):add(issues,'SECRET','',i,'A credential-like literal appears in source.','Possible hardcoded secret','CRITICAL',{'file':relpath})
        if re.search(r'\b(eval|exec)\s*\(',line) or re.search(r'child_process\.(exec|execSync)\s*\(',line):add(issues,'DANGEROUS_EXEC',relpath,i,'Dynamic code or shell execution can turn untrusted input into code execution.','Dynamic execution','HIGH')
        if re.search(r'\b(subprocess\.(run|Popen|call)|os\.system)\s*\(',line) or re.search(r'\b(system|popen)\s*\(',line) and extension in {'.c','.cpp','.h'}:add(issues,'COMMAND_EXEC',relpath,i,'Process execution detected; audit input handling.','Command execution','MEDIUM')
        if re.search(r'(?i)(select|insert|update|delete).*(\+|f["\']|\.format\(|%s)',line) and extension in {'.py','.js','.ts','.java','.php','.rb'}:add(issues,'SQL_INJECTION',relpath,i,'SQL appears to be assembled dynamically.','Possible SQL injection','HIGH')
        if re.search(r'(?i)(todo|fixme|hack|xxx)\b',line):add(issues,'TODO',relpath,i,line.strip(),'Work item marker','LOW')
        if len(line)>140:add(issues,'LONG_LINE',relpath,i,'Line exceeds 140 characters.','Long line','LOW')
        if extension in {'.js','.ts','.jsx','.tsx'} and re.search(r'innerHTML\s*=',line):add(issues,'DOM_XSS',relpath,i,'Direct innerHTML assignment should be reviewed when data is untrusted.','Potential DOM XSS','HIGH')
        if extension in {'.py'} and re.search(r'pickle\.(load|loads)\s*\(',line):add(issues,'UNSAFE_DESERIALIZE',relpath,i,'Pickle can execute code when loading untrusted data.','Unsafe deserialization','HIGH')
        if extension in {'.py','.js','.ts','.java','.php','.rb'} and re.search(r'(?i)password\s*=\s*["\']',line):add(issues,'PASSWORD_LITERAL',relpath,i,'Password-like assignment found in source.','Password in source','CRITICAL')
        if re.search(r'\bfor\b.*\bfor\b',line) and len(lines)>300:add(issues,'LOOP_HOTSPOT',relpath,i,'Nested-loop style pattern detected; inspect algorithmic cost.','Performance hotspot','MEDIUM')
    for i,line in enumerate(lines,1):
        if re.search(r'^(\s*)(def |function |func |fn |public |private |protected |class |struct |interface )',line): metrics['functions'] += bool(re.search(r'(def |function |func |fn |lambda)',line))
        if re.search(r'\b(class|interface|struct|enum)\s+\w+',line):metrics['classes']+=1
        if re.search(r'\b(import\s+|from\s+\S+\s+import|require\(|include\s*[<"]|using\s+|#include|use\s+|package\s+)',line):metrics['imports']+=1

def deps_for(source,p,all_files):
    ext=p.suffix.lower(); found=[]
    patterns=[]
    if ext in {'.js','.jsx','.ts','.tsx','.vue','.svelte'}: patterns=[r"(?:from|import)\s*['\"](.+?)['\"]",r"require\(\s*['\"](.+?)['\"]"]
    elif ext=='.py':patterns=[r'^(?:from|import)\s+([A-Za-z0-9_\.]+)']
    elif ext in {'.java','.kt','.kts','.scala'}:patterns=[r'^(?:import|package)\s+([A-Za-z0-9_\.]+)']
    elif ext in {'.c','.h','.cpp','.cc','.hpp','.m','.mm'}:patterns=[r'#include\s*[<\"]([^>\"]+)']
    elif ext=='.go':patterns=[r'"([A-Za-z0-9_./-]+)"']
    elif ext in {'.rb'}:patterns=[r'require\s+["\'](.+?)["\']']
    elif ext in {'.php'}:patterns=[r'(?:require|include)(?:_once)?\s*\(?\s*["\'](.+?)["\']']
    for pat in patterns:
        found += re.findall(pat,source,re.M)
    stems={f.stem:f for f in all_files}; names={str(f.relative_to(all_files[0].parents[len(all_files[0].parts)-1])) if False else f.name:f for f in all_files}
    resolved=[]
    for d in found:
        base=d.split('/')[-1].split('.')[-1]
        if d.startswith('.') or base in stems or d in names: resolved.append(d)
    return list(dict.fromkeys(resolved))

class Forge:
    def __init__(self,project):
        self.project=project.resolve(); self.lock=threading.RLock(); self.issues=[]; self.activity=[]; self.history=[]; self.snapshot={}; self.data_cache={}; self.num=0; self.live=True
    def emit(self,msg):
        with self.lock:self.activity.insert(0,f'[{stamp()}] {msg}');self.activity=self.activity[:100]
        print(self.activity[0])
    def snap(self):
        out={}
        for f in files(self.project):
            try:s=f.stat();out[rel(self.project,f)]=(s.st_mtime_ns,s.st_size)
            except FileNotFoundError:pass
        return out
    def scan(self):
        started=time.perf_counter(); fs=files(self.project); issues=[]; metrics={'lines':0,'bytes':0,'functions':0,'classes':0,'imports':0,'comments':0,'long_lines':0,'tests':0,'deps':set()}; lang_count=Counter(); edges=[]; nodes={}; hashes=defaultdict(list); search_docs=[]
        for f in fs:
            rp=rel(self.project,f); source=read(f); L=lang(f); lang_count[L]+=1; nodes[rp]={'id':rp,'label':f.name,'language':L,'lines':len(source.splitlines())}; generic_analysis(source,f,issues,metrics); search_docs.append({'path':rp,'language':L,'lines':len(source.splitlines())})
            if f.suffix.lower()=='.py':py_ast(source,f,self.project,issues,metrics)
            norm='\n'.join(x for x in normalized_lines(source) if x)
            if norm: hashes[hashlib.sha1(norm.encode()).hexdigest()].append(rp)
            # local dependency edges
            for d in deps_for(source,f,fs):
                target=None
                for candidate in fs:
                    if candidate.stem==d.split('/')[-1] or candidate.name==d.split('/')[-1] or rel(self.project,candidate).replace('/','.') in {d,d+'.py'}:
                        target=rel(self.project,candidate);break
                if target and target!=rp:edges.append({'source':rp,'target':target,'kind':'import'})
        duplicates=[v for v in hashes.values() if len(v)>1 and len(v[0])>0]
        for group in duplicates:
            for rp in group[1:]:add(issues,'DUPLICATE_FILE_PATTERN',rp,1,'This file has an identical normalized-content fingerprint to another scanned file.','Duplicate code/file fingerprint','MEDIUM',{'related':group})
        # dependency graph fallback by shared directory and imports
        graph_edges=[]; seen=set()
        for e in edges:
            k=(e['source'],e['target']);
            if k not in seen:seen.add(k);graph_edges.append(e)
        # Architecture clusters
        clusters=Counter((p.split('/')[0] if '/' in p else 'ROOT') for p in nodes)
        critical=sum(x['severity']=='CRITICAL' for x in issues); high=sum(x['severity']=='HIGH' for x in issues); medium=sum(x['severity']=='MEDIUM' for x in issues); low=sum(x['severity']=='LOW' for x in issues)
        score=max(0,round(100-critical*14-high*6-medium*2-low*0.5))
        score=min(100,score)
        complexity=round(min(100,(metrics['functions']*2+metrics['classes']*3+metrics['long_lines']*0.5+medium*1.5)/max(1,metrics['lines'])*100),1)
        maintain=max(0,round(100-complexity-critical*8-high*3,1)); security=max(0,round(100-critical*10-high*5,1)); coupling=min(100,round(len(graph_edges)/max(1,len(nodes))*100,1)); duplication=min(100,round(len(duplicates)*12,1))
        dna={'complexity':complexity,'coupling':coupling,'duplication':duplication,'maintainability':maintain,'security':security,'architecture':'MODULAR' if len(clusters)>2 else ('MONOLITH' if len(nodes)>15 else 'SCRIPT / SMALL APP')}
        self.num+=1; elapsed=round((time.perf_counter()-started)*1000,1)
        state={'project':str(self.project),'watching':self.live,'scan':self.num,'last':stamp(),'duration_ms':elapsed,'health':score,'stats':{k:(len(v) if k=='deps' else v) for k,v in metrics.items()},'languages':dict(lang_count),'issues':issues,'shortages':[x for x in issues if x['type'] in {'UNDEFINED_NAME','SYNTAX_ERROR'}],'security':[x for x in issues if x['type'] in {'SECRET','DANGEROUS_EXEC','COMMAND_EXEC','SQL_INJECTION','DOM_XSS','UNSAFE_DESERIALIZE','PASSWORD_LITERAL'}],'bugs':[x for x in issues if x['type'] not in {'UNDEFINED_NAME','SYNTAX_ERROR','SECRET','DANGEROUS_EXEC','COMMAND_EXEC','SQL_INJECTION','DOM_XSS','UNSAFE_DESERIALIZE','PASSWORD_LITERAL'}],'summary':{'total':len(issues),'critical':critical,'high':high,'medium':medium,'low':low,'files':len(fs)},'dna':dna,'graph':{'nodes':list(nodes.values()),'edges':graph_edges},'files':search_docs,'history':self.history+[(self.num,score,len(issues))],'activity':self.activity,'tests':sum(bool(TEST_RE.search(x)) for x in nodes),'folders':dict(clusters)}
        with self.lock:
            self.issues=issues;self.data_cache=state
            self.history=(self.history+[(self.num,score,len(issues))])[-30:]
            self.data_cache['history']=self.history
    def watch(self):
        self.snapshot=self.snap();self.scan();self.emit(f'Initial scan complete — {len(self.snapshot)} source files across {len(self.data_cache.get("languages",{}))} languages.')
        while self.live:
            time.sleep(INTERVAL);cur=self.snap()
            if cur==self.snapshot:continue
            old=self.snapshot;self.snapshot=cur;changed=[x for x in set(old)&set(cur) if old[x]!=cur[x]];added=list(set(cur)-set(old));removed=list(set(old)-set(cur));self.scan()
            if added:self.emit('FILE ADDED  :: '+', '.join(added[:8]))
            if changed:self.emit('FILE CHANGED :: '+', '.join(changed[:8]))
            if removed:self.emit('FILE REMOVED :: '+', '.join(removed[:8]))
            self.emit(f'Rescan #{self.num} complete — {len(self.issues)} findings.')
    def get_file(self,path):
        target=(self.project/path).resolve()
        if self.project not in target.parents or target.suffix.lower() not in CODE_EXT:return None
        if not target.is_file():return None
        source=read(target);return {'path':rel(self.project,target),'language':lang(target),'content':source,'lines':len(source.splitlines())}
    def search(self,q):
        q=q.strip().lower();out=[]
        if not q:return out
        for f in files(self.project):
            source=read(f)
            for i,line in enumerate(source.splitlines(),1):
                if q in line.lower():out.append({'file':rel(self.project,f),'line':i,'text':line.strip()[:240],'language':lang(f)})
                if len(out)>=250:return out
        return out
    def data(self):
        with self.lock:return dict(self.data_cache)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def send_json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        global FORGE
        u=urlparse(self.path);p=unquote(u.path)
        if p=='/':return self._raw(HTML,'text/html; charset=utf-8')
        if p=='/style.css':return self._raw(CSS,'text/css; charset=utf-8')
        if p=='/api/state':return self.send_json(FORGE.data())
        if p=='/api/file':
            x=FORGE.get_file(Path(parse_qs(u.query).get('path',[''])[0]));return self.send_json(x or {'error':'File not found'},404 if not x else 200)
        if p=='/api/search':return self.send_json({'results':FORGE.search(parse_qs(u.query).get('q',[''])[0])})
        self.send_json({'error':'Not found'},404)
    def _raw(self,path,typ):
        try:b=path.read_bytes()
        except FileNotFoundError:return self.send_json({'error':'Not found'},404)
        self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)

def choose_project():
    print('\nPROJECT FORGE // MULTI-LANGUAGE CODE INTELLIGENCE');print('='*64);print('Supports Python, JS/TS, Java, C/C++, C#, Go, Rust, PHP, Ruby, Swift, Kotlin, Dart, SQL, HTML/CSS and more.');print('Read-only analysis — the target project is never modified.\n')
    while True:
        p=Path(input('Project folder > ').strip().strip('"')).expanduser()
        if p.is_dir():return p.resolve()
        print('Folder not found. Enter a valid project folder.')

def main():
    global FORGE
    project=choose_project();FORGE=Forge(project);threading.Thread(target=FORGE.watch,name='forge-watch',daemon=True).start();server=ThreadingHTTPServer((HOST,PORT),Handler);url=f'http://{HOST}:{PORT}'
    print(f'\nCORE     :: {url}\nWATCHER  :: ONLINE\nMODE     :: READ ONLY\n')
    webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:FORGE.live=False;server.shutdown();server.server_close()
if __name__=='__main__':main()
