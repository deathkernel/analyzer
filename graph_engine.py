from __future__ import annotations
from collections import Counter, defaultdict, deque
from pathlib import Path
from scanner import import_tokens, rel

EXT_CANDIDATES=('.py','.js','.jsx','.ts','.tsx','.java','.kt','.c','.h','.cpp','.hpp','.cs','.go','.rs','.rb','.php')

def resolve_import(token, src, root, by_stem, by_name):
    clean=token.replace('\\','/').strip()
    candidates=[]
    if clean.startswith('.'):
        base=(src.parent / clean).resolve()
        candidates += [base, Path(str(base)+ext) for ext in EXT_CANDIDATES]
        candidates += [base/'__init__.py', base/'index.js', base/'index.ts', base/'index.tsx']
    else:
        normalized=clean.lstrip('./')
        candidates += [by_name.get(normalized), by_name.get(normalized.lstrip('/'))]
        module_path=normalized.replace('.','/')
        candidates += [by_name.get(module_path), by_name.get(module_path+'/__init__.py')]
        last=normalized.split('/')[-1].split('.')[-1]
        candidates += list(by_stem.get(last,[]))
    seen=set()
    for c in candidates:
        if not c or c in seen: continue
        seen.add(c)
        try:
            if c.exists() and root in c.parents:
                return c
        except OSError:
            continue
    return None

def _path_node(root,path,kind='file'):
    return '@file:'+rel(root,path) if kind=='file' else '@folder:'+path

def _semantic_edges(root,fs,contents,nodes,seen):
    edges=[]
    by_rel={rel(root,f).lower():f for f in fs}
    by_name=defaultdict(list)
    for f in fs:
        by_name[f.name.lower()].append(f)
        by_name[rel(root,f).lower()]=f
    template_files={p:f for p,f in by_rel.items() if '/templates/' in '/'+p or p.startswith('templates/')}
    asset_files={p:f for p,f in by_rel.items() if '/static/' in '/'+p or p.startswith('static/')}
    db_files={p:f for p,f in by_rel.items() if any(x in p for x in ('database/','db/','models/','schema.sql'))}

    def add(source,target,relation,confidence='inferred'):
        if source==target or source not in nodes or target not in nodes:return
        key=(source,target,relation)
        if key in seen:return
        seen.add(key)
        edges.append({'source':source,'target':target,'kind':'neural','relation':relation,'confidence':confidence})

    for f in fs:
        rp=rel(root,f).replace('\\','/').lower()
        nid=_path_node(root,f)
        text=contents.get(f,'')
        if rp.endswith('.py'):
            import re
            for name in re.findall(r"render_template\(\s*['\"]([^'\"]+)",text):
                candidates=[template_files.get(('templates/'+name).lower())]
                candidates += by_name.get(Path(name).name.lower(),[])
                for candidate in candidates:
                    if candidate:add(nid,_path_node(root,candidate),'renders');break
            if any(x in text for x in ('Blueprint(','blueprint','@app.','route(')):
                for dbp,dbf in db_files.items():
                    if dbp.endswith(('.py','.sql')) and any(t in rp for t in ('route','app.py','controller','api')):
                        add(nid,_path_node(root,dbf),'data-access')
            if f.name.lower() in ('app.py','main.py','server.py','index.py'):
                for other in fs:
                    op=rel(root,other).replace('\\','/').lower()
                    if other==f:continue
                    if any(t in op for t in ('routes/','route/','controllers/','api/')):add(nid,_path_node(root,other),'dispatches')
                    if op.endswith(('config.py','settings.py')):add(nid,_path_node(root,other),'configures')
                    if op in db_files:add(nid,_path_node(root,other),'initializes-data')
        if f.suffix.lower() in ('.html','.htm','.jinja','.jinja2'):
            import re
            refs=re.findall(r'''(?:href|src)\s*=\s*["']([^"']+)["']''',text,flags=re.I)
            for ref in refs:
                ref=ref.split('?')[0].split('#')[0].lstrip('./').lower()
                candidates=[asset_files.get(ref),asset_files.get('static/'+ref),asset_files.get(ref.lstrip('/'))]
                for candidate in candidates:
                    if candidate:add(nid,_path_node(root,candidate),'loads');break
            for name in re.findall(r'''\{%\s*(?:extends|include)\s+["']([^"']+)["']''',text,flags=re.I):
                candidate=template_files.get(('templates/'+name).lower()) or by_name.get(Path(name).name.lower(),[None])[0] if Path(name).name.lower() in by_name else None
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

def _layered_positions(nodes,edges):
    useful={n['id'] for n in nodes}
    directed=[e for e in edges if e['kind'] in ('import','neural') and e['source'] in useful and e['target'] in useful]
    out=defaultdict(list);indeg=Counter()
    for e in directed:out[e['source']].append(e['target']);indeg[e['target']]+=1
    q=deque(sorted([n for n in useful if indeg[n]==0]))
    rank={n:0 for n in q};remaining=set(useful)
    while q:
        n=q.popleft();remaining.discard(n)
        for m in sorted(set(out[n])):
            rank[m]=max(rank.get(m,0),rank[n]+1);indeg[m]-=1
            if indeg[m]==0:q.append(m)
    for n in sorted(remaining):
        neigh=[rank.get(x,0) for x in out[n]]+[rank.get(e['source'],0) for e in directed if e['target']==n]
        rank[n]=(min(neigh)+1) if neigh else 0

    buckets=defaultdict(list)
    for n in sorted(useful):buckets[rank[n]].append(n)
    order={r:list(v) for r,v in buckets.items()}
    for _ in range(4):
        for direction in (1,-1):
            ranks=sorted(order,reverse=direction<0)
            index={n:i for r in order for i,n in enumerate(order[r])}
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
        for part in rp.split('/')[:-1]:
            cur=f'{cur}/{part}'.strip('/');folders.add(cur)
    for folder in sorted(folders,key=lambda x:(x.count('/'),x)):
        nid='@folder:'+folder
        nodes[nid]={'id':nid,'label':'PROJECT' if folder=='.' else folder.split('/')[-1],'language':'FOLDER','kind':'folder','path':folder}
        if folder!='.':
            parent='/'.join(folder.split('/')[:-1]) or '.'
            e=('@folder:'+parent,nid)
            if e not in seen:
                seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'contains'})
    by_stem=defaultdict(list)
    by_name={}
    for f in fs:
        by_stem[f.stem.lower()].append(f)
        by_name[rel(root,f).lower()]=f
        by_name[f.name.lower()]=f
    for f in fs:
        rp=rel(root,f);nid='@file:'+rp;folder='/'.join(rp.split('/')[:-1]) or '.'
        nodes[nid]={'id':nid,'label':f.name,'language':f.suffix.lower(),'kind':'file','path':rp,'lines':len(contents[f].splitlines())}
        e=('@folder:'+folder,nid)
        if e not in seen:
            seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'contains'})
        for token in import_tokens(contents[f],f):
            target=resolve_import(token,f,root,by_stem,by_name)
            if target and target!=f:
                e=(nid,'@file:'+rel(root,target))
                if e not in seen:
                    seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'import','token':token})
    edges.extend(_semantic_edges(root,fs,contents,nodes,seen))
    rank,positions=_layered_positions(list(nodes.values()),edges)
    for n in nodes:nodes[n].update(positions.get(n,{'x':110,'y':40}),rank=rank.get(n,0))
    return list(nodes.values()),edges

def graph_metrics(nodes,edges):
    deg=Counter();imports=neural=contains=0
    for e in edges:
        if e['kind'] in ('import','neural'):
            deg[e['source']]+=1;deg[e['target']]+=1
        imports+=e['kind']=='import';neural+=e['kind']=='neural';contains+=e['kind']=='contains'
    for n in nodes:n['degree']=deg[n['id']]
    dependency_edges=imports+neural
    return {'nodes':len(nodes),'edges':len(edges),'dependencies':imports,'neural_links':neural,'contains_links':contains,'dependency_density':round((2*dependency_edges)/max(1,len(nodes)*(len(nodes)-1)),4),'density':round((2*len(edges))/max(1,len(nodes)*(len(nodes)-1)),4)}
