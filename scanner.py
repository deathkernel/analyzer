from __future__ import annotations
import ast, os, re
from collections import Counter
from pathlib import Path

IGNORE={'.git','.hg','.svn','__pycache__','.venv','venv','env','node_modules','.idea','.vscode','build','dist','target','bin','obj','.next','.nuxt','coverage','.pytest_cache','.mypy_cache'}
LANG={'.py':'Python','.js':'JavaScript','.jsx':'JavaScript JSX','.ts':'TypeScript','.tsx':'TypeScript JSX','.java':'Java','.c':'C','.h':'C/C++','.cpp':'C++','.cc':'C++','.hpp':'C++','.cs':'C#','.go':'Go','.rs':'Rust','.rb':'Ruby','.php':'PHP','.swift':'Swift','.kt':'Kotlin','.kts':'Kotlin','.dart':'Dart','.scala':'Scala','.sh':'Shell','.bash':'Shell','.zsh':'Shell','.ps1':'PowerShell','.sql':'SQL','.html':'HTML','.css':'CSS','.scss':'SCSS','.vue':'Vue','.svelte':'Svelte','.xml':'XML','.json':'JSON','.yaml':'YAML','.yml':'YAML','.toml':'TOML','.r':'R','.lua':'Lua','.ex':'Elixir','.exs':'Elixir','.erl':'Erlang','.fs':'F#','.fsx':'F#','.m':'Objective-C','.mm':'Objective-C++'}
EXTS=set(LANG)
SECRET=re.compile(r'''(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key)\s*[:=]\s*["'][^"']{8,}["']''')
TEST=re.compile(r'(^|[/\\])(tests?|specs?)([/\\]|$)|(^|[/\\])test_[^/\\]+|[^/\\]+_(test|spec)\.[^.]+$',re.I)

def rel(root,p):
    try:return str(p.relative_to(root)).replace('\\','/')
    except ValueError:return str(p).replace('\\','/')

def source_files(root):
    out=[]
    for base,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in IGNORE]
        out.extend(Path(base)/n for n in names if Path(n).suffix.lower() in EXTS)
    return sorted(out,key=lambda p:rel(root,p).lower())

def read_text(p):
    try:return p.read_text(encoding='utf-8',errors='replace')
    except Exception:return ''

def issue(out,kind,file,line,title,message,severity='MEDIUM',**extra):
    x={'type':kind,'file':file,'line':int(line or 0),'title':title,'message':message,'severity':severity};x.update(extra);out.append(x)

def python_checks(text,path,root,out,m):
    try:tree=ast.parse(text,filename=str(path))
    except SyntaxError as e:
        issue(out,'SYNTAX_ERROR',rel(root,path),e.lineno,'Syntax error',e.msg or 'Invalid Python syntax.','CRITICAL');return
    m['functions']+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree));m['classes']+=sum(isinstance(n,ast.ClassDef) for n in ast.walk(tree));m['imports']+=sum(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(tree))
    defined=set(dir(__builtins__)) if not isinstance(__builtins__,dict) else set(__builtins__);defined.update({'self','cls'})
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            for a in n.names:defined.add(a.asname or a.name.split('.')[0])
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):defined.add(n.name)
        elif isinstance(n,ast.arg):defined.add(n.arg)
        elif isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store):defined.add(n.id)
    seen=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id not in defined and not n.id.startswith('__'):
            k=(n.lineno,n.id)
            if k not in seen:seen.add(k);issue(out,'UNDEFINED_NAME',rel(root,path),n.lineno,f'Undefined name: {n.id}',f"'{n.id}' is used but is not defined or imported in this module.",'HIGH')
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Div,ast.FloorDiv,ast.Mod)) and isinstance(n.right,ast.Constant) and n.right.value==0:issue(out,'DIV_ZERO',rel(root,path),n.lineno,'Division by zero','Literal zero is used as the divisor.','CRITICAL')
        if isinstance(n,ast.While) and isinstance(n.test,ast.Constant) and n.test.value is True:issue(out,'INFINITE_LOOP_RISK',rel(root,path),n.lineno,'Possible infinite loop','Condition is always True; verify a reachable break.','MEDIUM')
        if isinstance(n,ast.Try):
            for h in n.handlers:
                if h.type is None:issue(out,'BARE_EXCEPT',rel(root,path),h.lineno,'Bare except','Bare except catches every exception.','MEDIUM')
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and len(n.body)==1 and isinstance(n.body[0],ast.Pass):issue(out,'EMPTY_FUNCTION',rel(root,path),n.lineno,'Empty function','Function body contains only pass.','LOW')
        if isinstance(n,ast.Subscript) and isinstance(n.value,(ast.List,ast.Tuple)) and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,int):
            i,size=n.slice.value,len(n.value.elts)
            if i>=size or i< -size:issue(out,'INDEX_ERROR',rel(root,path),n.lineno,'Index out of range',f'Index {i} is outside literal sequence length {size}.','HIGH')

def generic_checks(text,p,root,out,m):
    rp=rel(root,p);ext=p.suffix.lower();lines=text.splitlines();m['lines']+=len(lines);m['bytes']+=len(text.encode('utf-8',errors='ignore'));m['comments']+=sum(bool(re.match(r'^\s*(#|//|/\*|\*|<!--|;)',x)) for x in lines);m['long_lines']+=sum(len(x)>140 for x in lines);m['tests']+=int(bool(TEST.search(rp)))
    for no,line in enumerate(lines,1):
        low=line.lower()
        if SECRET.search(line) and not any(x in low for x in ('example','sample','dummy','placeholder','changeme')):issue(out,'SECRET',rp,no,'Possible hardcoded secret','Credential-like literal detected in source.','CRITICAL')
        if re.search(r'\b(eval|exec)\s*\(',line) or re.search(r'child_process\.(exec|execSync)\s*\(',line):issue(out,'DANGEROUS_EXEC',rp,no,'Dynamic execution','Dynamic code or shell execution needs input validation.','HIGH')
        if re.search(r'\b(subprocess\.(run|Popen|call)|os\.system)\s*\(',line):issue(out,'COMMAND_EXEC',rp,no,'Command execution','Process execution detected; audit input handling.','MEDIUM')
        if ext in {'.py','.js','.ts','.java','.php','.rb'} and re.search(r'(?i)(select|insert|update|delete).*(\+|f["\']|\.format\(|%s)',line):issue(out,'SQL_INJECTION',rp,no,'Possible SQL injection','SQL appears to be assembled dynamically.','HIGH')
        if re.search(r'(?i)\b(todo|fixme|hack|xxx)\b',line):issue(out,'TODO',rp,no,'Work item marker',line.strip()[:220],'LOW')
        if len(line)>140:issue(out,'LONG_LINE',rp,no,'Long line','Line exceeds 140 characters.','LOW')
        if ext in {'.js','.ts','.jsx','.tsx'} and re.search(r'innerHTML\s*=',line):issue(out,'DOM_XSS',rp,no,'Potential DOM XSS','Direct innerHTML assignment should be reviewed when data is untrusted.','HIGH')
        if ext=='.py' and re.search(r'pickle\.(load|loads)\s*\(',line):issue(out,'UNSAFE_DESERIALIZE',rp,no,'Unsafe deserialization','Pickle can execute code when loading untrusted data.','HIGH')
        if ext in {'.py','.js','.ts','.java','.php','.rb'} and re.search(r'(?i)password\s*=\s*["\']',line):issue(out,'PASSWORD_LITERAL',rp,no,'Password in source','Password-like assignment found in source.','CRITICAL')
        if re.search(r'\bfor\b.*\bfor\b',line) and len(lines)>300:issue(out,'LOOP_HOTSPOT',rp,no,'Performance hotspot','Nested-loop style pattern detected; inspect algorithmic cost.','MEDIUM')
    if ext!='.py':m['functions']+=sum(bool(re.search(r'\b(def|function|func|fn)\b',x)) for x in lines)
    m['classes']+=sum(bool(re.search(r'\b(class|interface|struct|enum)\s+\w+',x)) for x in lines)
    if ext!='.py':m['imports']+=sum(bool(re.search(r'\b(import\s+|from\s+\S+\s+import|require\(|#include|using\s+|include\s*[<"]|use\s+)',x)) for x in lines)

def analyze(root):
    fs=source_files(root);contents={f:read_text(f) for f in fs};issues=[];m=Counter();languages=Counter()
    for f in fs:
        languages[LANG.get(f.suffix.lower(),'Other')]+=1
        text=contents[f];
        if f.suffix.lower()=='.py':python_checks(text,f,root,issues,m)
        generic_checks(text,f,root,issues,m)
    severity=Counter(x['severity'] for x in issues);health=max(0,100-severity['CRITICAL']*18-severity['HIGH']*9-severity['MEDIUM']*4-severity['LOW'])
    duplication=max(0,min(100,100-int(m['long_lines']*1.7)))
    complexity=max(0,min(100,100-int((m['functions']+m['classes']*2)/max(1,m['lines'])*80)))
    coupling=max(0,min(100,100-int(m['imports']/max(1,len(fs))*35)))
    security=max(0,100-severity['CRITICAL']*25-severity['HIGH']*12)
    maintainability=max(0,min(100,(complexity+coupling+duplication)//3))
    dna={'complexity':complexity,'coupling':coupling,'duplication':duplication,'security':security,'maintainability':maintainability,'architecture':'MODULAR' if len(fs)>8 else ('COMPACT' if len(fs)>2 else 'MINIMAL')}
    tests=[rel(root,f) for f in fs if TEST.search(rel(root,f))]
    files=[{'path':rel(root,f),'language':LANG.get(f.suffix.lower(),'Other'),'lines':len(contents[f].splitlines()),'bytes':mbytes(contents[f])} for f in fs]
    return {'files':files,'contents':contents,'issues':issues,'metrics':dict(m),'languages':dict(languages),'health':health,'dna':dna,'tests':tests,'severity':dict(severity)}

def mbytes(text):return len(text.encode('utf-8',errors='ignore'))

def import_tokens(text,p):
    pats={'.py':[r'^\s*from\s+([\w.]+)\s+import',r'^\s*import\s+([\w.]+)'],'.js':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],'.jsx':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],'.ts':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],'.tsx':[r'(?:from|import)\s*["\'](.+?)["\']',r'require\(\s*["\'](.+?)["\']'],'.java':[r'^\s*import\s+([\w.]+)'],'.kt':[r'^\s*import\s+([\w.]+)'],'.c':[r'#include\s*[<"]([^>"]+)'],'.h':[r'#include\s*[<"]([^>"]+)'],'.cpp':[r'#include\s*[<"]([^>"]+)'],'.hpp':[r'#include\s*[<"]([^>"]+)'],'.go':[r'"([\w./-]+)"'],'.rs':[r'\b(?:mod|use)\s+([\w:]+)'],'.rb':[r'require\s+["\'](.+?)["\']'],'.php':[r'(?:require|include)(?:_once)?\s*\(?\s*["\'](.+?)["\']']}
    out=[]
    for pat in pats.get(p.suffix.lower(),[]):out.extend(re.findall(pat,text,re.M))
    return list(dict.fromkeys(out))
