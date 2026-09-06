from __future__ import annotations
import ast, hashlib, json, os, re, threading, time, webbrowser
from collections import Counter, defaultdict, deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HOST, PORT, INTERVAL = '127.0.0.1', 8765, 1.0
HERE = Path(__file__).resolve().parent
HTML, CSS = HERE/'index.html', HERE/'style.css'
FORGE = None
IGNORE = {'.git','.hg','.svn','__pycache__','.venv','venv','env','node_modules','.idea','.vscode','build','dist','target','bin','obj','.next','.nuxt','coverage','.pytest_cache'}
LANG = {'.py':'Python','.js':'JavaScript','.jsx':'JavaScript JSX','.ts':'TypeScript','.tsx':'TypeScript JSX','.java':'Java','.c':'C','.h':'C/C++','.cpp':'C++','.cc':'C++','.hpp':'C++','.cs':'C#','.go':'Go','.rs':'Rust','.rb':'Ruby','.php':'PHP','.swift':'Swift','.kt':'Kotlin','.kts':'Kotlin','.dart':'Dart','.scala':'Scala','.sh':'Shell','.bash':'Shell','.zsh':'Shell','.ps1':'PowerShell','.sql':'SQL','.html':'HTML','.css':'CSS','.scss':'SCSS','.vue':'Vue','.svelte':'Svelte','.xml':'XML','.json':'JSON','.yaml':'YAML','.yml':'YAML','.toml':'TOML','.r':'R','.lua':'Lua','.ex':'Elixir','.exs':'Elixir','.erl':'Erlang','.fs':'F#','.fsx':'F#','.m':'Objective-C','.mm':'Objective-C++'}
EXTS = set(LANG)
SECRET = re.compile(r'(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key)\s*[:=]\s*["\'][^"\']{8,}["\']')
TEST = re.compile(r'(^|[/\\])(tests?|specs?)([/\\]|$)|(^|[/\\])test_[^/\\]+|[^/\\]+_(test|spec)\.[^.]+$', re.I)

def stamp(): return datetime.now().strftime('%H:%M:%S')
def rel(root, p):
    try: return str(p.relative_to(root)).replace('\\','/')
    except ValueError: return str(p).replace('\\','/')
def source_files(root):
    result=[]
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE]
        result.extend(Path(base)/n for n in names if Path(n).suffix.lower() in EXTS)
    return sorted(result, key=lambda p: rel(root,p).lower())
def language(p): return LANG.get(p.suffix.lower(), 'Other')
def read_text(p):
    try: return p.read_text(encoding='utf-8', errors='replace')
    except Exception: return ''
def issue(out, kind, file, line, title, message, severity='MEDIUM', **extra):
    item={'type':kind,'file':file,'line':int(line or 0),'title':title,'message':message,'severity':severity}; item.update(extra); out.append(item)

def python_checks(text, path, root, out, metrics):
    try: tree=ast.parse(text, filename=str(path))
    except SyntaxError as e:
        issue(out,'SYNTAX_ERROR',rel(root,path),e.lineno,'Syntax error',e.msg or 'Invalid Python syntax.','CRITICAL'); return
    metrics['functions'] += sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree))
    metrics['classes'] += sum(isinstance(n,ast.ClassDef) for n in ast.walk(tree))
    metrics['imports'] += sum(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(tree))
    defined=set(dir(__builtins__)) if not isinstance(__builtins__,dict) else set(__builtins__)
    defined.update({'self','cls'})
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            for a in n.names: defined.add(a.asname or a.name.split('.')[0])
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): defined.add(n.name)
        elif isinstance(n,ast.arg): defined.add(n.arg)
        elif isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store): defined.add(n.id)
    seen=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id not in defined and not n.id.startswith('__'):
            key=(n.lineno,n.id)
            if key not in seen: seen.add(key); issue(out,'UNDEFINED_NAME',rel(root,path),n.lineno,f'Undefined name: {n.id}',f"'{n.id}' is used but is not defined or imported in this module.",'HIGH')
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Div,ast.FloorDiv,ast.Mod)) and isinstance(n.right,ast.Constant) and n.right.value==0:
            issue(out,'DIV_ZERO',rel(root,path),n.lineno,'Division by zero','Literal zero is used as the divisor.','CRITICAL')
        if isinstance(n,ast.While) and isinstance(n.test,ast.Constant) and n.test.value is True:
            issue(out,'INFINITE_LOOP_RISK',rel(root,path),n.lineno,'Possible infinite loop','Condition is always True; verify a reachable break.','MEDIUM')
        if isinstance(n,ast.Try):
            for h in n.handlers:
                if h.type is None: issue(out,'BARE_EXCEPT',rel(root,path),h.lineno,'Bare except','Bare except catches every exception.','MEDIUM')
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and len(n.body)==1 and isinstance(n.body[0],ast.Pass):
            issue(out,'EMPTY_FUNCTION',rel(root,path),n.lineno,'Empty function','Function body contains only pass.','LOW')
        if isinstance(n,ast.Subscript) and isinstance(n.value,(ast.List,ast.Tuple)) and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,int):
            i,size=n.slice.value,len(n.value.elts)
            if i>=size or i< -size: issue(out,'INDEX_ERROR',rel(root,path),n.lineno,'Index out of range',f'Index {i} is outside literal sequence length {size}.','HIGH')

def generic_checks(text, p, root, out, metrics):
    rp=rel(root,p); ext=p.suffix.lower(); lines=text.splitlines(); metrics['lines']+=len(lines); metrics['bytes']+=len(text.encode('utf-8',errors='ignore')); metrics['comments']+=sum(bool(re.match(r'^\s*(#|//|/\*|\*|<!--|;)',x)) for x in lines); metrics['long_lines']+=sum(len(x)>140 for x in lines)
    metrics['tests'] += int(bool(TEST.search(rp)))
    for no,line in enumerate(lines,1):
        low=line.lower()
        if SECRET.search(line) and not any(x in low for x in ('example','sample','dummy','placeholder','changeme')): issue(out,'SECRET',rp,no,'Possible hardcoded secret','Credential-like literal detected in source.','CRITICAL')
        if re.search(r'\b(eval|exec)\s*\(',line) or re.search(r'child_process\.(exec|execSync)\s*\(',line): issue(out,'DANGEROUS_EXEC',rp,no,'Dynamic execution','Dynamic code or shell execution needs input validation.','HIGH')
        if re.search(r'\b(subprocess\.(run|Popen|call)|os\.system)\s*\(',line): issue(out,'COMMAND_EXEC',rp,no,'Command execution','Process execution detected; audit input handling.','MEDIUM')
        if ext in {'.py','.js','.ts','.java','.php','.rb'} and re.search(r'(?i)(select|insert|update|delete).*(\+|f["\']|\.format\(|%s)',line): issue(out,'SQL_INJECTION',rp,no,'Possible SQL injection','SQL appears to be assembled dynamically.','HIGH')
        if re.search(r'(?i)\b(todo|fixme|hack|xxx)\b',line): issue(out,'TODO',rp,no,'Work item marker',line.strip()[:220],'LOW')
        if len(line)>140: issue(out,'LONG_LINE',rp,no,'Long line','Line exceeds 140 characters.','LOW')
        if ext in {'.js','.ts','.jsx','.tsx'} and re.search(r'innerHTML\s*=',line): issue(out,'DOM_XSS',rp,no,'Potential DOM XSS','Direct innerHTML assignment should be reviewed when data is untrusted.','HIGH')
        if ext=='.py' and re.search(r'pickle\.(load|loads)\s*\(',line): issue(out,'UNSAFE_DESERIALIZE',rp,no,'Unsafe deserialization','Pickle can execute code when loading untrusted data.','HIGH')
        if ext in {'.py','.js','.ts','.java','.php','.rb'} and re.search(r'(?i)password\s*=\s*["\']',line): issue(out,'PASSWORD_LITERAL',rp,no,'Password in source','Password-like assignment found in source.','CRITICAL')
        if re.search(r'\bfor\b.*\bfor\b',line) and len(lines)>300: issue(out,'LOOP_HOTSPOT',rp,no,'Performance hotspot','Nested-loop style pattern detected; inspect algorithmic cost.','MEDIUM')
    metrics['functions'] += sum(bool(re.search(r'\b(def|function|func|fn)\b',x)) for x in lines) if ext!='.py' else 0
    metrics['classes'] += sum(bool(re.search(r'\b(class|interface|struct|enum)\s+\w+',x)) for x in lines)
    metrics['imports'] += sum(bool(re.search(r'\b(import\s+|from\s+\S+\s+import|require\(|#include|using\s+|include\s*[<"]|use\s+)',x)) for x in lines) if ext!='.py' else 0

def import_tokens(text,p):
    ext=p.suffix.lower(); pats={
        '.py':[r'^\s*from\s+([\w.]+)\s+import',r'^\s*import\s+([\w.]+)'],
        '.js':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],'.jsx':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],
        '.ts':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],'.tsx':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],
        '.java':[r'^\s*import\s+([\w.]+)'],'.kt':[r'^\s*import\s+([\w.]+)'],'.kts':[r'^\s*import\s+([\w.]+)'],
        '.c':[r'#include\s*[<"]([^>"]+)'],'.h':[r'#include\s*[<"]([^>"]+)'],'.cpp':[r'#include\s*[<"]([^>"]+)'],'.hpp':[r'#include\s*[<"]([^>"]+)'],
        '.go':[r'"([\w./-]+)"'],'.rs':[r'\b(?:mod|use)\s+([\w:]+)'],'.rb':[r'require\s+["\'](.+?)["\']'],'.php':[r'(?:require|include)(?:_once)?\s*\(?\s*["\'](.+?)["\']']}
    out=[]
    for pat in pats.get(ext,[]): out.extend(re.findall(pat,text,re.M))
    return list(dict.fromkeys(out))

def resolve_import(token, src, root, by_stem, by_name):
    clean=token.replace('\\','/').strip()
    candidates=[]
    if clean.startswith('.'):
        base=(src.parent/clean).resolve(); candidates += [base,Path(str(base)+'.py'),base/'__init__.py',Path(str(base)+'.js'),Path(str(base)+'.ts'),Path(str(base)+'.tsx')]
    else:
        last=clean.split('/')[-1].split('.')[-1]
        if last in by_stem: candidates.append(by_stem[last])
        if clean in by_name: candidates.append(by_name[clean])
        if clean.replace('.','/') in by_name: candidates.append(by_name[clean.replace('.','/')])
    for c in candidates:
        if c and c.exists() and root in c.parents: return c
    return None

def build_graph(root, fs, contents):
    nodes={}; edges=[]; edge_seen=set()
    folders={'.'}
    for f in fs:
        rp=rel(root,f); parts=rp.split('/')[:-1]; cur=''
        for part in parts: cur=f'{cur}/{part}'.strip('/'); folders.add(cur)
    for folder in sorted(folders,key=lambda x:(x.count('/'),x)):
        nid='@folder:'+folder; label='PROJECT' if folder=='.' else folder.split('/')[-1]; nodes[nid]={'id':nid,'label':label,'language':'FOLDER','kind':'folder','path':folder}
        if folder!='.':
            parent='/'.join(folder.split('/')[:-1]) or '.'; edge_seen.add(('@folder:'+parent,nid)); edges.append({'source':'@folder:'+parent,'target':nid,'kind':'contains'})
    by_stem={f.stem.lower():f for f in fs}; by_name={rel(root,f):f for f in fs}; by_name.update({f.name:f for f in fs})
    for f in fs:
        rp=rel(root,f); nid='@file:'+rp; folder='/'.join(rp.split('/')[:-1]) or '.'
        nodes[nid]={'id':nid,'label':f.name,'language':language(f),'kind':'file','path':rp,'lines':len(contents[f].splitlines())}
        e=('@folder:'+folder,nid)
        if e not in edge_seen: edge_seen.add(e); edges.append({'source':e[0],'target':e[1],'kind':'contains'})
        for token in import_tokens(contents[f],f):
            target=resolve_import(token,f,root,by_stem,by_name)
            if target and target!=f:
                a,b=nid,'@file:'+rel(root,target); e=(a,b)
                if e not in edge_seen: edge_seen.add(e); edges.append({'source':a,'target':b,'kind':'import'})
    # deterministic layered layout: folders above files, dependencies flow left-to-right.
    adj=defaultdict(list); indeg=Counter()
    for e in edges:
        if e['kind']=='import': adj[e['source']].append(e['target']); indeg[e['target']]+=1
    q=deque([n for n in nodes if indeg[n]==0]); rank={n:0 for n in q}
    while q:
        n=q.popleft()
        for m in adj[n]:
            rank[m]=max(rank.get(m,0),rank[n]+1); indeg[m]-=1
            if indeg[m]==0:q.append(m)
    for n in nodes: rank.setdefault(n,0)
    buckets=defaultdict(list)
    for n,r in rank.items(): buckets[r].append(n)
    positions={}; maxrank=max(buckets or {0:0}); W,H=1200,680
    for r in sorted(buckets):
        arr=sorted(buckets[r]); gap=H/(len(arr)+1)
        x=80+(r/max(1,maxrank))*1040
        for i,n in enumerate(arr): positions[n]={'x':round(x),'y':round((i+1)*gap)}
    for n,p in positions.items(): nodes[n]['x']=p['x']; nodes[n]['y']=p['y']; nodes[n]['rank']=rank[n]
    return list(nodes.values()), edges

class Forge:
    def __init__(self,project):
        self.project=project.resolve(); self.lock=threading.RLock(); self.live=True; self.num=0; self.history=[]; self.snapshot={}; self.state={}; self.activity=[]
    def emit(self,msg):
        with self.lock: self.activity.insert(0,f'[{stamp()}] {msg}'); self.activity=self.activity[:120]
        print(self.activity[0])
    def snap(self):
        out={}
        for f in source_files(self.project):
            try: s=f.stat(); out[rel(self.project,f)]=(s.st_mtime_ns,s.st_size)
            except FileNotFoundError: pass
        return out
    def scan(self):
        start=time.perf_counter(); fs=source_files(self.project); contents={f:read_text(f) for f in fs}; issues=[]; metrics={'files':len(fs),'lines':0,'bytes':0,'functions':0,'classes':0,'imports':0,'comments':0,'long_lines':0,'tests':0}; langs=Counter(); docs=[]; fingerprints=defaultdict(list)
        for f in fs:
            text=contents[f]; langs[language(f)]+=1; rp=rel(self.project,f); docs.append({'path':rp,'language':language(f),'lines':len(text.splitlines())})
            generic_checks(text,f,self.project,issues,metrics)
            if f.suffix.lower()=='.py': python_checks(text,f,self.project,issues,metrics)
            normalized='\n'.join(x for x in re.sub(r'//.*|#.*$','',text,flags=re.M).splitlines() if x.strip())
            if normalized: fingerprints[hashlib.sha1(normalized.encode()).hexdigest()].append(rp)
        for group in fingerprints.values():
            if len(group)>1:
                for rp in group[1:]: issue(issues,'DUPLICATE_FILE',rp,1,'Duplicate file fingerprint','Normalized source fingerprint matches: '+', '.join(group),'MEDIUM',related=group)
        nodes,edges=build_graph(self.project,fs,contents)
        critical=sum(i['severity']=='CRITICAL' for i in issues); high=sum(i['severity']=='HIGH' for i in issues); medium=sum(i['severity']=='MEDIUM' for i in issues); low=sum(i['severity']=='LOW' for i in issues)
        health=max(0,min(100,round(100-critical*14-high*6-medium*2-low*.35)))
        complexity=round(min(100,(metrics['functions']*2+metrics['classes']*3+metrics['long_lines']*.5+medium*1.5)/max(1,metrics['lines'])*100),1)
        coupling=round(min(100,sum(e['kind']=='import' for e in edges)/max(1,len(fs))*100),1); duplication=round(min(100,max(0,(len(fingerprints)-sum(len(x)==1 for x in fingerprints.values()))*10)),1)
        maintain=max(0,round(100-complexity-critical*8-high*3,1)); security=max(0,round(100-critical*10-high*5,1))
        folders=Counter((x.rsplit('/',1)[0] if '/' in x else 'ROOT') for x in [d['path'] for d in docs]); arch='MODULAR' if len(folders)>2 or len(nodes)>20 else ('MONOLITH' if len(fs)>15 else 'SCRIPT / SMALL APP')
        self.num+=1; elapsed=round((time.perf_counter()-start)*1000,1); self.history=(self.history+[(self.num,health,len(issues))])[-60:]
        self.state={'project':str(self.project),'watching':self.live,'scan':self.num,'last':stamp(),'duration_ms':elapsed,'health':health,'stats':metrics,'languages':dict(langs),'issues':issues,'shortages':[i for i in issues if i['type'] in {'UNDEFINED_NAME','SYNTAX_ERROR'}],'security':[i for i in issues if i['type'] in {'SECRET','DANGEROUS_EXEC','COMMAND_EXEC','SQL_INJECTION','DOM_XSS','UNSAFE_DESERIALIZE','PASSWORD_LITERAL'}],'bugs':[i for i in issues if i['type'] not in {'UNDEFINED_NAME','SYNTAX_ERROR','SECRET','DANGEROUS_EXEC','COMMAND_EXEC','SQL_INJECTION','DOM_XSS','UNSAFE_DESERIALIZE','PASSWORD_LITERAL'}],'summary':{'total':len(issues),'critical':critical,'high':high,'medium':medium,'low':low,'files':len(fs)},'dna':{'complexity':complexity,'coupling':coupling,'duplication':duplication,'maintainability':maintain,'security':security,'architecture':arch},'graph':{'nodes':nodes,'edges':edges},'files':docs,'history':self.history,'activity':self.activity,'tests':metrics['tests']}
    def watch(self):
        self.snapshot=self.snap(); self.scan(); self.emit(f'Initial scan complete — {len(self.snapshot)} source files / {len(self.state.get("languages",{}))} languages / {len(self.state.get("graph",{}).get("edges",[]))} graph connections.')
        while self.live:
            time.sleep(INTERVAL); cur=self.snap()
            if cur==self.snapshot: continue
            old=self.snapshot; self.snapshot=cur; added=sorted(set(cur)-set(old)); removed=sorted(set(old)-set(cur)); changed=sorted(x for x in set(old)&set(cur) if old[x]!=cur[x]); self.scan()
            if added:self.emit('FILE ADDED  :: '+', '.join(added[:8]))
            if changed:self.emit('FILE CHANGED :: '+', '.join(changed[:8]))
            if removed:self.emit('FILE REMOVED :: '+', '.join(removed[:8]))
            self.emit(f'Rescan #{self.num} complete — {len(self.state.get("issues",[]))} findings / {len(self.state.get("graph",{}).get("edges",[]))} connections.')
    def data(self):
        with self.lock:return dict(self.state)
    def get_file(self,path):
        p=(self.project/path).resolve()
        if self.project not in p.parents or p.suffix.lower() not in EXTS or not p.is_file(): return None
        text=read_text(p); return {'path':rel(self.project,p),'language':language(p),'content':text,'lines':len(text.splitlines())}
    def search(self,q):
        q=q.strip().lower(); out=[]
        if not q:return out
        for f in source_files(self.project):
            for no,line in enumerate(read_text(f).splitlines(),1):
                if q in line.lower(): out.append({'file':rel(self.project,f),'line':no,'text':line.strip()[:260],'language':language(f)})
                if len(out)>=500:return out
        return out

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def json(self,obj,status=200):
        body=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def raw(self,p,typ):
        try:b=p.read_bytes()
        except FileNotFoundError:return self.json({'error':'Not found'},404)
        self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        global FORGE; u=urlparse(self.path); p=unquote(u.path); qs=parse_qs(u.query)
        if p=='/':return self.raw(HTML,'text/html; charset=utf-8')
        if p=='/style.css':return self.raw(CSS,'text/css; charset=utf-8')
        if p=='/api/state':return self.json(FORGE.data())
        if p=='/api/graph':return self.json(FORGE.data().get('graph',{}))
        if p=='/api/file':
            x=FORGE.get_file(qs.get('path',[''])[0]); return self.json(x or {'error':'File not found'},404 if not x else 200)
        if p=='/api/search':return self.json({'results':FORGE.search(qs.get('q',[''])[0])})
        return self.json({'error':'Not found'},404)

def choose_project():
    print('\nPROJECT FORGE // POLYGLOT CODE INTELLIGENCE\n'+'='*70+'\nRead-only continuous analysis. The target project is never modified.\n')
    while True:
        raw=input('Project folder > ').strip().strip('"'); p=Path(raw).expanduser()
        if p.is_dir(): return p.resolve()
        print('Folder not found — enter a valid project folder.')

def main():
    global FORGE
    project=choose_project(); FORGE=Forge(project); threading.Thread(target=FORGE.watch,daemon=True,name='forge-watch').start(); server=ThreadingHTTPServer((HOST,PORT),Handler); url=f'http://{HOST}:{PORT}'; print(f'\nFORGE ONLINE  →  {url}\n'); threading.Timer(.7,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: FORGE.live=False; server.server_close()

if __name__=='__main__': main()
