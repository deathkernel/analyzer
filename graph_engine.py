from __future__ import annotations
from collections import Counter,defaultdict,deque
from pathlib import Path
from scanner import import_tokens,rel

def resolve_import(token,src,root,by_stem,by_name):
    clean=token.replace('\\','/').strip();candidates=[]
    if clean.startswith('.'):
        base=(src.parent/clean).resolve();candidates += [base,Path(str(base)+'.py'),base/'__init__.py',Path(str(base)+'.js'),Path(str(base)+'.ts'),Path(str(base)+'.tsx')]
    else:
        last=clean.split('/')[-1].split('.')[-1]
        if last in by_stem:candidates.append(by_stem[last])
        if clean in by_name:candidates.append(by_name[clean])
        if clean.replace('.','/') in by_name:candidates.append(by_name[clean.replace('.','/')])
    for c in candidates:
        if c and c.exists() and root in c.parents:return c
    return None

def build_graph(root,fs,contents):
    nodes={};edges=[];seen=set();folders={'.'}
    for f in fs:
        rp=rel(root,f);cur=''
        for part in rp.split('/')[:-1]:cur=f'{cur}/{part}'.strip('/');folders.add(cur)
    for folder in sorted(folders,key=lambda x:(x.count('/'),x)):
        nid='@folder:'+folder;nodes[nid]={'id':nid,'label':'PROJECT' if folder=='.' else folder.split('/')[-1],'language':'FOLDER','kind':'folder','path':folder}
        if folder!='.':
            parent='/'.join(folder.split('/')[:-1]) or '.';e=('@folder:'+parent,nid)
            if e not in seen:seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'contains'})
    by_stem={f.stem.lower():f for f in fs};by_name={rel(root,f):f for f in fs};by_name.update({f.name:f for f in fs})
    for f in fs:
        rp=rel(root,f);nid='@file:'+rp;folder='/'.join(rp.split('/')[:-1]) or '.';nodes[nid]={'id':nid,'label':f.name,'language':f.suffix.lower(),'kind':'file','path':rp,'lines':len(contents[f].splitlines())}
        e=('@folder:'+folder,nid)
        if e not in seen:seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'contains'})
        for token in import_tokens(contents[f],f):
            target=resolve_import(token,f,root,by_stem,by_name)
            if target and target!=f:
                e=(nid,'@file:'+rel(root,target))
                if e not in seen:seen.add(e);edges.append({'source':e[0],'target':e[1],'kind':'import','token':token})
    indeg=Counter();adj=defaultdict(list)
    for e in edges:
        if e['kind']=='import':adj[e['source']].append(e['target']);indeg[e['target']]+=1
    q=deque([n for n in nodes if indeg[n]==0]);rank={n:0 for n in q}
    while q:
        n=q.popleft()
        for m in adj[n]:
            rank[m]=max(rank.get(m,0),rank[n]+1);indeg[m]-=1
            if indeg[m]==0:q.append(m)
    for n in nodes:rank.setdefault(n,0)
    buckets=defaultdict(list)
    for n,r in rank.items():buckets[r].append(n)
    maxrank=max(buckets or {0:0});positions={};H=680
    for r in sorted(buckets):
        arr=sorted(buckets[r]);gap=H/(len(arr)+1);x=90+(r/max(1,maxrank))*1020
        for i,n in enumerate(arr):positions[n]={'x':round(x),'y':round((i+1)*gap)}
    for n,p in positions.items():nodes[n].update(p,rank=rank[n])
    return list(nodes.values()),edges

def graph_metrics(nodes,edges):
    deg=Counter();imports=0
    for e in edges:
        deg[e['source']]+=1;deg[e['target']]+=1;imports+=e['kind']=='import'
    for n in nodes:n['degree']=deg[n['id']]
    return {'nodes':len(nodes),'edges':len(edges),'dependencies':imports,'density':round((2*len(edges))/max(1,len(nodes)*(len(nodes)-1)),4)}
