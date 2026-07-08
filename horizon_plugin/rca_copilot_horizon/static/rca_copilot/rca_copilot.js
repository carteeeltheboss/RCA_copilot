(function () {
  function levelClass(level) {
    level = String(level || '').toUpperCase();
    if (level === 'ERROR' || level === 'CRITICAL') return 'error';
    if (level === 'WARNING' || level === 'WARN') return 'warn';
    if (level === 'DEBUG') return 'debug';
    return 'info';
  }
  function renderGraph(container) {
    var data = {};
    try { data = JSON.parse(container.getAttribute('data-graph') || '{}'); } catch (e) { data = {}; }
    var nodes = data.nodes || [];
    var edges = data.edges || [];
    if (!nodes.length) {
      container.innerHTML = '<div class="rca-empty">Graph unavailable.</div>';
      return;
    }
    var rect = container.getBoundingClientRect();
    var width = Math.max(rect.width || 600, 320);
    var height = Math.max(rect.height || 420, 280);
    var radius = Math.min(width, height) * 0.35;
    var centerX = width / 2;
    var centerY = height / 2;
    var positions = {};
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'rca-edge-layer');
    container.appendChild(svg);
    nodes.forEach(function (node, index) {
      var angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1);
      var x = centerX + Math.cos(angle) * radius - 27;
      var y = centerY + Math.sin(angle) * radius - 27;
      positions[node.id] = { x: x + 27, y: y + 27 };
      var el = document.createElement('div');
      el.className = 'rca-node ' + levelClass(node.level) + (node.seed ? ' seed' : '');
      el.style.left = x + 'px';
      el.style.top = y + 'px';
      el.title = (node.service || 'event') + ': ' + (node.message || '');
      el.textContent = node.service || 'event';
      el.setAttribute('data-node', JSON.stringify(node));
      el.onclick = function () { selectNode(node); };
      container.appendChild(el);
    });
    edges.forEach(function (edge) {
      var source = positions[edge.source];
      var target = positions[edge.target];
      if (!source || !target) return;
      var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', source.x);
      line.setAttribute('y1', source.y);
      line.setAttribute('x2', target.x);
      line.setAttribute('y2', target.y);
      line.setAttribute('stroke', edge.reason === 'same_request_id' ? '#6f42c1' : '#00897b');
      line.setAttribute('stroke-width', '2');
      svg.appendChild(line);
    });
  }
  function selectNode(node) {
    var target = document.getElementById('rca-event-details');
    if (target) target.textContent = JSON.stringify(node, null, 2);
  }
  document.addEventListener('DOMContentLoaded', function () {
    var graph = document.getElementById('rca-graph');
    if (graph) renderGraph(graph);
    Array.prototype.forEach.call(document.querySelectorAll('.rca-timeline-row'), function (row) {
      row.onclick = function () { selectNode({ id: row.getAttribute('data-event-id'), text: row.innerText }); };
    });
  });
}());
