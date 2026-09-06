from __future__ import annotations
from collections import Counter, defaultdict, deque
from pathlib import Path
from scanner import import_tokens, rel


def resolve_import(token, src, root, by_stem, by_name):
    clean = token.replace('\\', '/').strip()
    candidates = []
    if clean.startswith('.'):
        base = (src.parent / clean).resolve()
        candidates += [base, Path(str(base) + '.py'), base / '__init__.py', Path(str(base) + '.js'), Path(str(base) + '.ts'), Path(str(base) + '.tsx')]
    else:
        last = clean.split('/')[-1].split('.')[-1]
        if last in by_stem: candidates.append(by_stem[last])
        if clean in by_name: candidates.append(by_name[clean])
        if clean.replace('.', '/') in by_name: candidates.append(by_name[clean.replace('.', '/')])
    for c in candidates:
        if c and c.exists() and root in c.parents: return c
    return None


def _path_node(root, path, kind='file'):
    return '@file:' + rel(root, path) if kind == 'file' else '@folder:' + path


def _semantic_edges(root, fs, contents, nodes, seen):
    edges = []
    by_rel = {rel(root, f).lower(): f for f in fs}
    by_name = {f.name.lower(): f for f in fs}
    template_files = {p: f for p, f in by_rel.items() if '/templates/' in '/' + p or p.startswith('templates/')}
    asset_files = {p: f for p, f in by_rel.items() if '/static/' in '/' + p or p.startswith('static/')}
    db_files = {p: f for p, f in by_rel.items() if any(x in p for x in ('database/', 'db/', 'models/', 'schema.sql'))}

    def add(source, target, relation):
        if source == target or source not in nodes or target not in nodes: return
        key = (source, target, relation)
        if key in seen: return
        seen.add(key)
        edges.append({'source': source, 'target': target, 'kind': 'neural', 'relation': relation, 'confidence': 'inferred'})

    for f in fs:
        rp = rel(root, f).replace('\\', '/').lower()
        nid = _path_node(root, f)
        text = contents.get(f, '')
        if rp.endswith('.py'):
            import re
            for name in re.findall(r"render_template\(\s*['\"]([^'\"]+)", text):
                candidate = template_files.get(('templates/' + name).lower()) or by_name.get(name.lower())
                if candidate: add(nid, _path_node(root, candidate), 'renders')
            if any(x in text for x in ('Blueprint(', 'blueprint', '@app.', 'route(')):
                for dbp, dbf in db_files.items():
                    if dbp.endswith(('.py', '.sql')) and any(t in rp for t in ('route', 'app.py', 'controller', 'api')):
                        add(nid, _path_node(root, dbf), 'data-access')
            if f.name.lower() in ('app.py', 'main.py', 'server.py', 'index.py'):
                for other in fs:
                    op = rel(root, other).replace('\\', '/').lower()
                    if other == f: continue
                    if any(t in op for t in ('routes/', 'route/', 'controllers/', 'api/')): add(nid, _path_node(root, other), 'dispatches')
                    if op.endswith(('config.py', 'settings.py')): add(nid, _path_node(root, other), 'configures')
                    if op in db_files: add(nid, _path_node(root, other), 'initializes-data')
        if f.suffix.lower() in ('.html', '.htm', '.jinja', '.jinja2'):
            import re
            refs = re.findall(r'''(?:href|src)\s*=\s*["']([^"']+)["']''', text, flags=re.I)
            for ref in refs:
                ref = ref.split('?')[0].split('#')[0].lstrip('./').lower()
                candidate = asset_files.get(ref) or asset_files.get('static/' + ref)
                if candidate: add(nid, _path_node(root, candidate), 'loads')
            for name in re.findall(r'''\{\%\s*(?:extends|include)\s+["']([^"']+)["']''', text, flags=re.I):
                candidate = template_files.get(('templates/' + name).lower()) or by_name.get(name.lower())
                if candidate: add(nid, _path_node(root, candidate), 'composes')

    for n in nodes.values():
        p = str(n.get('path', '')).replace('\\', '/').lower()
        if n.get('kind') == 'folder': n['role'] = 'container'
        elif p.endswith(('app.py', 'main.py', 'server.py')): n['role'] = 'entrypoint'
        elif '/routes/' in '/' + p or p.startswith('routes/') or '/controllers/' in '/' + p: n['role'] = 'controller'
        elif '/templates/' in '/' + p or p.startswith('templates/'): n['role'] = 'view'
        elif '/static/' in '/' + p or p.startswith('static/'): n['role'] = 'asset'
        elif any(x in p for x in ('database/', 'db/', 'models/')) or p.endswith('schema.sql'): n['role'] = 'data'
        else: n['role'] = 'module'
    return edges


def _layered_positions(nodes, edges):
    """Deterministic layered layout with a few crossing-reduction passes."""
    useful = {n['id'] for n in nodes}
    directed = [e for e in edges if e['kind'] in ('import', 'neural') and e['source'] in useful and e['target'] in useful]
    out = defaultdict(list); indeg = Counter()
    for e in directed:
        out[e['source']].append(e['target']); indeg[e['target']] += 1

    # Longest-path ranks; cycles are kept stable instead of producing a tangled force layout.
    q = deque(sorted([n for n in useful if indeg[n] == 0]))
    rank = {n: 0 for n in q}
    remaining = set(useful)
    while q:
        n = q.popleft(); remaining.discard(n)
        for m in sorted(out[n]):
            rank[m] = max(rank.get(m, 0), rank[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0: q.append(m)
    # Cyclic leftovers: place them in a final stable layer based on their minimum neighbor rank.
    for n in sorted(remaining):
        neigh = [rank.get(x, 0) for x in out[n]] + [rank.get(e['source'], 0) for e in directed if e['target'] == n]
        rank[n] = (min(neigh) + 1) if neigh else 0

    buckets = defaultdict(list)
    for n in sorted(useful): buckets[rank[n]].append(n)
    order = {r: list(v) for r, v in buckets.items()}

    # Repeated barycenter sweeps reduce edge crossings while remaining deterministic.
    for _ in range(4):
        for direction in (1, -1):
            ranks = sorted(order, reverse=direction < 0)
            index = {n: i for r in order for i, n in enumerate(order[r])}
            for r in ranks:
                if len(order[r]) < 2: continue
                neighbors = defaultdict(list)
                for e in directed:
                    if rank[e['target']] == r and rank[e['source']] != r:
                        neighbors[e['target']].append(index[e['source']])
                    if rank[e['source']] == r and rank[e['target']] != r:
                        neighbors[e['source']].append(index[e['target']])
                order[r].sort(key=lambda n: (sum(neighbors[n]) / len(neighbors[n]) if neighbors[n] else index[n], n))

    positions = {}
    maxrank = max(order or {0: 0})
    for r in sorted(order):
        arr = order[r]
        x = 110 + (r / max(1, maxrank)) * 980
        gap = 640 / (len(arr) + 1)
        for i, n in enumerate(arr): positions[n] = {'x': round(x), 'y': round(30 + (i + 1) * gap)}
    return rank, positions


def build_graph(root, fs, contents):
    nodes, edges, seen = {}, [], set()
    folders = {'.'}
    for f in fs:
        rp = rel(root, f); cur = ''
        for part in rp.split('/')[:-1]:
            cur = f'{cur}/{part}'.strip('/'); folders.add(cur)
    for folder in sorted(folders, key=lambda x: (x.count('/'), x)):
        nid = '@folder:' + folder
        nodes[nid] = {'id': nid, 'label': 'PROJECT' if folder == '.' else folder.split('/')[-1], 'language': 'FOLDER', 'kind': 'folder', 'path': folder}
        if folder != '.':
            parent = '/'.join(folder.split('/')[:-1]) or '.'; e = ('@folder:' + parent, nid)
            if e not in seen:
                seen.add(e); edges.append({'source': e[0], 'target': e[1], 'kind': 'contains'})

    by_stem = {f.stem.lower(): f for f in fs}
    by_name = {rel(root, f): f for f in fs}; by_name.update({f.name: f for f in fs})
    for f in fs:
        rp = rel(root, f); nid = '@file:' + rp; folder = '/'.join(rp.split('/')[:-1]) or '.'
        nodes[nid] = {'id': nid, 'label': f.name, 'language': f.suffix.lower(), 'kind': 'file', 'path': rp, 'lines': len(contents[f].splitlines())}
        e = ('@folder:' + folder, nid)
        if e not in seen:
            seen.add(e); edges.append({'source': e[0], 'target': e[1], 'kind': 'contains'})
        for token in import_tokens(contents[f], f):
            target = resolve_import(token, f, root, by_stem, by_name)
            if target and target != f:
                e = (nid, '@file:' + rel(root, target))
                if e not in seen:
                    seen.add(e); edges.append({'source': e[0], 'target': e[1], 'kind': 'import', 'token': token})

    edges.extend(_semantic_edges(root, fs, contents, nodes, seen))
    rank, positions = _layered_positions(list(nodes.values()), edges)
    for n in nodes:
        nodes[n].update(positions.get(n, {'x': 110, 'y': 40}), rank=rank.get(n, 0))
    return list(nodes.values()), edges


def graph_metrics(nodes, edges):
    deg = Counter(); imports = neural = 0
    for e in edges:
        if e['kind'] in ('import', 'neural'):
            deg[e['source']] += 1; deg[e['target']] += 1
        imports += e['kind'] == 'import'; neural += e['kind'] == 'neural'
    for n in nodes: n['degree'] = deg[n['id']]
    return {'nodes': len(nodes), 'edges': len(edges), 'dependencies': imports, 'neural_links': neural, 'density': round((2 * len(edges)) / max(1, len(nodes) * (len(nodes) - 1)), 4)}
