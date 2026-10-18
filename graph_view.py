"""
graph_view.py - draw the company mind-map on screen
===================================================
FalkorDB stores the map. This file paints it so a judge can SEE connections.

New in this version:
- click a node and everything not connected to it fades out
- a legend and a small info line inside the picture
- `highlight` makes matching nodes bigger with a white ring
"""

import json

from db import get_connection

COLORS = {
    "Person": "#F2B84B",
    "Project": "#4FD1C5",
    "System": "#F28C52",
    "Document": "#B8A9FF",
    "Decision": "#7DB7FF",
    "Incident": "#FF5C8A",
}


def fetch_company_edges():
    """
    Ask FalkorDB for every useful line in the company brain.
    We skip Session/Memory so the picture stays about the org, not the chat log.
    """
    graph = get_connection()
    result = graph.query(
        """
        MATCH (a)-[r]->(b)
        WHERE NOT a:Session AND NOT b:Session
          AND NOT a:Memory AND NOT b:Memory
          AND NOT a:Blackboard AND NOT b:Blackboard
          AND NOT a:AgentNote AND NOT b:AgentNote
        RETURN labels(a)[0], coalesce(a.name, a.title, a.id),
               type(r),
               labels(b)[0], coalesce(b.name, b.title, b.id)
        """
    )
    return result.result_set or []


_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    html, body { margin: 0; height: 100%; background: transparent; font-family: 'IBM Plex Sans', system-ui, sans-serif; }
    #net { height: __HEIGHT__px; background: #14213D; border-radius: 14px; }
    #legend { position: absolute; top: 14px; left: 16px; display: flex; gap: 14px; flex-wrap: wrap;
              font-size: 12px; color: #C9D6E2; max-width: 80%; }
    #legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
    #info { position: absolute; bottom: 14px; left: 16px; font-size: 13px; color: #F3F6F8;
            background: rgba(20,33,61,0.85); padding: 6px 10px; border-radius: 8px; }
  </style>
</head>
<body>
  <div id="net"></div>
  <div id="legend">__LEGEND__</div>
  <div id="info">Click a node to follow its connections. Drag to rearrange.</div>
  <script>
    const RAW_NODES = __NODES__;
    const RAW_EDGES = __EDGES__;
    const DIM = 'rgba(120,134,160,0.28)';
    const nodes = new vis.DataSet(RAW_NODES);
    const edges = new vis.DataSet(RAW_EDGES);
    const info = document.getElementById('info');
    const HINT = info.textContent;

    const network = new vis.Network(
      document.getElementById('net'),
      { nodes, edges },
      {
        physics: {
          barnesHut: { gravitationalConstant: -9000, springLength: 130, damping: 0.5 },
          stabilization: { iterations: 220 }
        },
        nodes: { shape: 'dot', borderWidth: 2, font: { color: '#F3F6F8', size: 13 } },
        edges: {
          color: { color: '#3A4C75' }, width: 1, smooth: { type: 'dynamic' },
          font: { size: 9, color: '#8FA3B8', strokeWidth: 0 }
        },
        interaction: { hover: true, tooltipDelay: 80 }
      }
    );
    network.once('stabilizationIterationsDone', () => network.fit({ animation: true }));

    function focusOn(id) {
      const near = new Set(network.getConnectedNodes(id)); near.add(id);
      const nearEdges = new Set(network.getConnectedEdges(id));
      nodes.update(RAW_NODES.map(n => ({
        id: n.id,
        color: near.has(n.id) ? n.base : DIM,
        font: { color: near.has(n.id) ? '#F3F6F8' : 'rgba(243,246,248,0.25)' }
      })));
      edges.update(edges.getIds().map(eid => ({
        id: eid,
        color: { color: nearEdges.has(eid) ? '#F2B84B' : '#26365A' },
        width: nearEdges.has(eid) ? 2 : 1,
        font: { color: nearEdges.has(eid) ? '#C9D6E2' : 'rgba(143,163,184,0.15)' }
      })));
      const n = nodes.get(id);
      info.textContent = n.group + ': ' + n.label + ' has ' + (near.size - 1) + ' direct connections';
    }

    function reset() {
      nodes.update(RAW_NODES.map(n => ({ id: n.id, color: n.base, font: { color: '#F3F6F8' } })));
      edges.update(edges.getIds().map(eid => ({
        id: eid, color: { color: '#3A4C75' }, width: 1, font: { color: '#8FA3B8' }
      })));
      info.textContent = HINT;
    }

    network.on('click', params => {
      if (params.nodes.length) focusOn(params.nodes[0]); else reset();
    });
  </script>
</body>
</html>
"""


def vis_html(edges, highlight=None, height=640):
    """
    Build the vis-network picture.
    highlight = optional text; nodes whose name contains it get bigger with a white ring.
    """
    highlight = (highlight or "").strip().lower()
    nodes = {}
    vis_edges = []
    for left_kind, left_name, rel, right_kind, right_name in edges:
        left_id = f"{left_kind}:{left_name}"
        right_id = f"{right_kind}:{right_name}"
        nodes[left_id] = (left_kind, str(left_name))
        nodes[right_id] = (right_kind, str(right_name))
        vis_edges.append({"from": left_id, "to": right_id, "label": rel, "arrows": "to"})

    node_list = []
    kinds_present = []
    for node_id, (kind, name) in nodes.items():
        color = COLORS.get(kind, "#888888")
        if kind not in kinds_present:
            kinds_present.append(kind)
        matched = bool(highlight) and highlight in name.lower()
        node_list.append(
            {
                "id": node_id,
                "label": name,
                "group": kind,
                "base": color,
                "color": {"background": color, "border": "#FFFFFF" if matched else color},
                "size": 30 if matched else 18,
                "borderWidth": 4 if matched else 2,
                "title": f"{kind}: {name}",
            }
        )
    # Keep the "base" colour as a plain string for the JS reset, vis colour object for drawing
    for n in node_list:
        n["base"] = n["color"]["background"]

    legend = "".join(
        f'<span><i style="background:{COLORS.get(k, "#888")}"></i>{k}</span>'
        for k in kinds_present
    )

    return (
        _TEMPLATE.replace("__HEIGHT__", str(int(height)))
        .replace("__LEGEND__", legend)
        .replace("__NODES__", json.dumps(node_list))
        .replace("__EDGES__", json.dumps(vis_edges))
    )