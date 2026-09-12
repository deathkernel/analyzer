from __future__ import annotations
import ast
from collections import Counter, defaultdict, deque
from pathlib import Path
from scanner import import_tokens, rel

EXT_CANDIDATES=('.py','.js','.jsx','.ts','.tsx','.java','.kt','.c','.h','.cpp','.hpp','.cs','.go','.rs','.rb','.php')

def _file_candidates(base):
    return [base, *[Path(str(base)+ext) for ext in EXT_CANDIDATES], base/'__init__.py', base/'index.js', base/'index.ts', base/'index.tsx']

def resolve_import(token, src, root, by_stem, by_name):
    clean=token.replace('\\','/').strip();candidates=[]
    if clean.startswith('.'):
        level=len(clean)-len(clean.lstrip('.'));module=clean[level:].lstrip('/');base=src.parent
        for _ in range(max(0,level-1)):base=base.parent
        if module:candidates.extend(_file_candidates(base/module.replace('.','/')))
        else:return None
    else:
        normalized=clean.lstrip('./').lower();module_path=normalized.replace('.','/')
        for key in (normalized,module_path):
            for candidate in _file_candidates(root/key):
                value=by_name.get(str(candidate.relative_to(root)).replace('\\','/').lower())
                if value:candidates.extend(value if isinstance(value,list) else [value])
            for candidate_key in (key,key+'.py',key+'.js',key+'.jsx',key+'.ts',key+'.tsx',key+'.java',key+'.kt',key+'.go',key+'.rs',key+'/__init__.py'):
                value=by_name.get(candidate_key)
                if value:candidates.extend(value if isinstance(value,list) else [value])
        last=normalized.split('/')[-1].split('.')[-1];matches=by_stem.get(last,[])
        if len(matches)==1:candidates.append(matches[0])
    seen=set()
    for c in candidates:
        if not c or c in seen:continue
        seen.add(c)
        try:
            if c.is_file() and root in c.parents:return c
        except OSError:continue
    return None

def _path_node(root,path,kind='file'):
    return '@file:'+rel(root,path) if kind=='file' else '@folder:'+path

def _semantic_edges(root,fs,contents,nodes,seen):
    edges=[];by_rel={rel(root,f).lower():f for f in fs};by_name=defaultdict(list)
    for f in fs:by_name[f.name.lower()].append(f);by_name[rel(root,f).lower()].append(f)
    template_files={p:f for p,f in by_rel.items() if '/templates/' in '/'+p or p.startswith('templates/')}
    asset_files={p:f for p,f in by_rel.items() if '/static/' in '/'+p or p.startswith('static/')}
    db_files={p:f for p,f in by_rel.items() if any(x in p for x in ('database/','db/','models/','schema.sql'))}
    def add(source,target,relation,confidence='inferred'):
        if source==target or source not in nodes or target not in nodes:return
        key=(source,target,relation)
        if key in seen:return
        seen.add(key);edges.append({'source':source,'target':target,'kind':'neural','relation':relation,'confidence':confidence})
    for f in fs:
        rp=rel(root,f).replace('\\','/').lower();nid=_path_node(root,f);text=contents.get(f,'')
        if rp.endswith('.py'):
            import re
            for name in re.findall(r"render_template\(\s*['\"]([^'\"]+)",text):
                candidate=template_files.get(('templates/'+name).lower())
                if not candidate and by_name.get(Path(name).name.lower()):
                    matches=by_name[Path(name).name.lower()];candidate=matches[0] if len(matches)==1 else None
                if candidate:add(nid,_path_node(root,candidate),'renders')
            if any(x in text for x in ('Blueprint(','blueprint','@app.','route(')):
                for dbp,dbf in db_files.items():
                    if dbp.endswith(('.py','.sql')) and any(t in rp for t in ('route','app.py','controller','api')):add(nid,_path_node(root,dbf),'data-access')
            if f.name.lower() in ('app.py','main.py','server.py','index.py'):
                for other in fs:
                    op=rel(root,other).replace('\\','/').lower()
                    if other==f:continue
                    if any(t in op for t in ('routes/','route/','controllers/','api/')):add(nid,_path_node(root,other),'dispatches')
                    if op.endswith(('config.py','settings.py')):add(nid,_path_node(root,other),'configures')
                    if op in db_files:add(nid,_path_node(root,other),'initializes-data')
        if f.suffix.lower() in ('.html','.htm','.jinja','.jinja2'):
            import re
            for ref in re.findall(r'''(?:href|src)\s*=\s*["']([^"']+)["']''',text,flags=re.I):
                ref=ref.split('?')[0].split('#')[0].lstrip('./').lower();candidate=asset_files.get(ref) or asset_files.get('static/'+ref) or asset_files.get(ref.lstrip('/'))
                if candidate:add(nid,_path_node(root,candidate),'loads')
            for name in re.findall(r'''\{%\s*(?:extends|include)\s+["']([^"']+)["']''',text,flags=re.I):
                candidate=template_files.get(('templates/'+name).lower())
                if not candidate and by_name.get(Path(name).name.lower()):
                    matches=by_name[Path(name).name.lower()];candidate=matches[0] if len(matches)==1 else None
                if candidate:add(nid,_path_node(root,candidate),'composes')
    for n in nodes.values():
        p=str(n.get('path','')).replace('\\','/').lower()
        if n.get('kind')=='folder':n['role']='container'
        elif p.endswith(('app.py','main.py','server.py')):n['role']='entrypoint'
        elif '/routes/' in '/'+p or p.startswith('routes/') or '/controllers/' in '/'+p:n['role']='controller'
        elif '/templates/' in '/'+p or p.startswith('templates/'):n['role']='view'
        elif '/static/' in '/'+p or p.startswith('static/'):n['role']='asset'
        elif any(x in p for x in ('database/','db/','models/')) or p.endswith('schema.sql'):n['role']='data'
        else:n['role']='module'
    return edges

def _extract_symbol_flow(root,fs,contents,nodes,seen):
    edges=[]
    def add(source,target,relation='calls',confidence='ast'):
        if source==target or source not in nodes or target not in nodes:return
        key=(source,target,relation)
        if key in seen:return
        seen.add(key);edges.append({'source':source,'target':target,'kind':'flow','relation':relation,'confidence':confidence})
    py_defs={}
    for f in fs:
        if f.suffix.lower()!='.py':continue
        try:tree=ast.parse(contents.get(f,''))
        except Exception:continue
        path_node=_path_node(root,f);local=set()
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                local.add(node.name);py_defs.setdefault(node.name,[]).append(path_node)
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for call in ast.walk(node):
                    if isinstance(call,ast.Call):
                        callee=call.func.id if isinstance(call.func,ast.Name) else call.func.attr if isinstance(call.func,ast.Attribute) else None
                        if callee and callee in py_defs:
                            for target_file in py_defs[callee][:4]:add(path_node,target_file,f'calls:{callee}')
                for branch in ast.walk(node):
                    if isinstance(branch,(ast.If,ast.For,ast.While,ast.Try,ast.Match)):
                        add(path_node,path_node,f'control:{type(branch).__name__}',confidence='ast-local')
    for f in fs:
        if f.suffix.lower() not in ('.js','.jsx','.ts','.tsx'):continue
        text=contents.get(f,'');src=_path_node(root,f)
        import re
        defs=re.findall(r'\b(?:function\s+|(?:const|let|var)\s+)([A-Za-z_$][\w$]*)\s*(?:=\s*\([^)]*\)\s*=>|\()',text)
        known=set(defs)
        for name in sorted(known):
            if re.search(rf'\b{name}\s*\(',text):add(src,src,f'calls:{name}',confidence='text-local')
    return edges

def _layered_positions(nodes,edges):
    useful={n['id'] for n in nodes};directed=[e for e in edges if e['kind'] in ('import','neural','flow') and e['source'] in useful and e['target'] in useful];out=defaultdict(list);indeg=Counter()
    for e in directed:out[e['source']].append(e['target']);indeg[e['target']]+=1
    q=deque(sorted([n for n in useful if indeg[n]==0]));rank={n:0 for n in q};remaining=set(useful)
    while q:
        n=q.popleft();remaining.discard(n)
        for m in sorted(set(out[n])):rank[m]=max(rank.get(m,0),rank[n]+1);indeg[m]-=1;q.append(m) if indeg[m]==0 else None
    for n in sorted(remaining):
        neigh=[rank.get(x,0) for x in out[n]]+[rank.get(e['source'],0) for e in directed if e['target']==n];rank[n]=(min(neigh)+1) if neigh else 0
    buckets=defaultdict(list)
    for n in sorted(useful):buckets[rank[n]].append(n)
    order={r:list(v) for r,v in buckets.items()}
    for _ in range(4):
        for direction in (1,-1):
            ranks=sorted(order,reverse=direction<0);index={n:i for r in order for i,n in enumerate(order[r])}
            for r in ranks:
                if len(order[r])<2:continue
                neighbors=defaultdict(list)
                for e in directed:
                    if rank[e['target']]==r and rank[e['source']]!=r:neighbors[e['target']].append(index[e['source']])
                    if rank[e['source']]==r and rank[e['target']]!=r:neighbors[e['source']].append(index[e['target']])
                order[r].sort(key=lambda n:(sum(neighbors[n])/len(neighbors[n]) if neighbors[n] else index[n],n))
    positions={};maxrank=max(order or {0:0})
    for r in sorted(order):
        arr=order[r];x=110+(r/max(1,maxrank))*980;gap=640/(len(arr)+1)
        for i,n in enumerate(arr):positions[n]={'x':round(x),'y':round(30+(i+1)*gap)}
    return rank,positions

def build_graph(root,fs,contents):
    nodes,edges,seen={},[],set();folders={'.'}
    for f in fs:
        rp=rel(root,f);cur=''
        for part in rp.split('/')[:-1]:cur=f'{cur}/{part}'.strip('/');folders.add(cur)
    for folder in sorted(folders,key=lambda x:(x.count('/'),x)):
        nid='@folder:'+folder;nodes[nid]={'id':nid,'label':'PROJECT' if folder=='.' else folder.split('/')[-1],'language':'FOLDER','kind':'folder','path':folder}
        if folder!='.':
            parent='/'.join(folder.split('/')[:-1]) or '.';e=('@folder:'+parent,nid)
            if e not in seen:seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'contains'})
    by_stem=defaultdict(list);by_name=defaultdict(list)
    for f in fs:
        rp=rel(root,f).lower();by_stem[f.stem.lower()].append(f);by_name[rp].append(f);by_name[f.name.lower()].append(f)
    for f in fs:
        rp=rel(root,f);nid='@file:'+rp;folder='/'.join(rp.split('/')[:-1]) or '.';nodes[nid]={'id':nid,'label':f.name,'language':f.suffix.lower(),'kind':'file','path':rp,'lines':len(contents[f].splitlines())}
        e=('@folder:'+folder,nid)
        if e not in seen:seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'contains'})
        for token in import_tokens(contents[f],f):
            target=resolve_import(token,f,root,by_stem,by_name)
            if target and target!=f:
                e=(nid,'@file:'+rel(root,target))
                if e not in seen:seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'import','token':token})
    edges.extend(_semantic_edges(root,fs,contents,nodes,seen));edges.extend(_extract_symbol_flow(root,fs,contents,nodes,seen));rank,positions=_layered_positions(list(nodes.values()),edges)
    for n in nodes:nodes[n].update(positions.get(n,{'x':110,'y':40}),rank=rank.get(n,0))
    return list(nodes.values()),edges

def graph_metrics(nodes,edges):
    kinds=Counter(e['kind'] for e in edges);return {'nodes':len(nodes),'edges':len(edges),'imports':kinds.get('import',0),'semantic':kinds.get('neural',0),'flow':kinds.get('flow',0),'contains':kinds.get('contains',0),'density':round(len(edges)/max(1,len(nodes)),2)}

def _cycle_components(nodes,edges):
    ids={n['id'] for n in nodes};adj=defaultdict(list)
    for e in edges:
        if e['kind'] in ('import','neural','flow') and e['source'] in ids and e['target'] in ids:adj[e['source']].append(e['target'])
    index=0;stack=[];onstack=set();indices={};low={};components=[]
    def visit(v):
        nonlocal index
        indices[v]=index;low[v]=index;index+=1;stack.append(v);onstack.add(v)
        for w in adj[v]:
            if w not in indices:visit(w);low[v]=min(low[v],low[w])
            elif w in onstack:low[v]=min(low[v],indices[w])
        if low[v]==indices[v]:
            comp=[]
            while True:
                w=stack.pop();onstack.remove(w);comp.append(w)
                if w==v:break
            if len(comp)>1:components.append(comp)
            elif comp and comp[0] in adj[comp[0]]:components.append(comp)
    for v in sorted(ids):
        if v not in indices:visit(v)
    return components

def _impact(nodes,edges,focus_id=None):
    if not focus_id:return {'focused':None,'upstream':[],'downstream':[],'blast_radius':0}
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for e in edges:
        if e['kind'] in ('import','neural','flow'):outgoing[e['source']].append(e['target']);incoming[e['target']].append(e['source'])
    def walk(start,adj):
        seen=set();q=deque([start])
        while q:
            x=q.popleft()
            for y in adj.get(x,[]):
                if y not in seen and y!=start:seen.add(y);q.append(y)
        return seen
    up=walk(focus_id,incoming);down=walk(focus_id,outgoing);labels={n['id']:n.get('path',n.get('label')) for n in nodes}
    return {'focused':labels.get(focus_id,focus_id),'upstream':sorted(labels[x] for x in up),'downstream':sorted(labels[x] for x in down),'blast_radius':len(up|down)}

def _xray(nodes,edges):
    roles=Counter(n.get('role','module') for n in nodes);ids={n['id'] for n in nodes};adjacency=defaultdict(list)
    for e in edges:
        if e['kind'] in ('import','neural','flow') and e['source'] in ids and e['target'] in ids:adjacency[e['source']].append(e['target'])
    entry=[n for n in nodes if n.get('role')=='entrypoint'];data={n['id'] for n in nodes if n.get('role')=='data'};paths=[]
    for e in entry:
        q=deque([(e['id'],[e.get('path',e['label'])])]);seen={e['id']}
        while q:
            cur,path=q.popleft()
            if cur in data:paths.append(path);continue
            for nb in adjacency[cur]:
                if nb not in seen:
                    seen.add(nb);node=next((x for x in nodes if x['id']==nb),None)
                    if node:q.append((nb,path+[node.get('path',node['label'])]))
    return {'roles':dict(roles),'entrypoints':[n.get('path',n.get('label')) for n in entry],'data_nodes':len(data),'flows':paths[:30]}

def _dead_code(nodes,edges,contents=None):
    contents=contents or {};incoming=Counter(e['target'] for e in edges if e['kind'] in ('import','neural','flow'));candidates=[]
    for n in nodes:
        if n.get('kind')=='file' and incoming[n['id']]==0 and n.get('role')!='entrypoint':candidates.append({'path':n.get('path'),'reason':'No inbound flow/dependency edge'})
    if contents:
        for f,text in contents.items():
            if str(getattr(f,'suffix','')).lower()=='.py':
                try:tree=ast.parse(text)
                except Exception:continue
                refs=Counter(x.id for x in ast.walk(tree) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load))
                for node in ast.walk(tree):
                    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.name not in refs and not node.name.startswith('_'):candidates.append({'path':str(f),'line':node.lineno,'symbol':node.name,'reason':'Defined but never referenced in module'})
    unique=[];seen=set()
    for x in candidates:
        k=(x.get('path'),x.get('line'),x.get('symbol'),x.get('reason'))
        if k not in seen:seen.add(k);unique.append(x)
    return unique[:200]

def intelligence_report(nodes,edges,contents=None,focus_id=None):
    cycles=_cycle_components(nodes,edges)
    return {'cycles':[[next((n.get('path',n.get('label')) for n in nodes if n['id']==i),i) for i in comp] for comp in cycles],'cycle_count':len(cycles),'impact':_impact(nodes,edges,focus_id),'xray':_xray(nodes,edges),'dead_code':_dead_code(nodes,edges,contents)}
