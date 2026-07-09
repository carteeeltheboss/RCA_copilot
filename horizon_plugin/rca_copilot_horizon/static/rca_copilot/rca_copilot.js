(function () {
  function readGraphData() {
    var script = document.getElementById('rca-graph-data');
    if (!script) return {};
    try { return JSON.parse(script.textContent || '{}'); } catch (e) { return {}; }
  }

  function nodeClass(level) {
    level = String(level || '').toUpperCase();
    if (level === 'ERROR' || level === 'CRITICAL') return 'error';
    if (level === 'WARNING' || level === 'WARN') return 'warning';
    if (level === 'DEBUG') return 'debug';
    return 'info';
  }

  function edgeClass(reason) {
    reason = String(reason || '');
    if (reason === 'same_request_id') return 'same-request';
    if (reason === 'shared_resource_id') return 'shared-resource';
    return 'other-correlation';
  }

  function text(value) {
    if (value === null || value === undefined || value === '') return '-';
    if (Array.isArray(value)) return value.join(', ') || '-';
    return String(value);
  }

  function detailHtml(title, rows) {
    var html = '<h4>' + escapeHtml(title) + '</h4><dl class="dl-horizontal">';
    rows.forEach(function (row) {
      html += '<dt>' + escapeHtml(row[0]) + '</dt><dd>' + escapeHtml(text(row[1])) + '</dd>';
    });
    return html + '</dl>';
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char];
    });
  }

  function setDetails(html) {
    var target = document.getElementById('rca-event-details');
    if (target) target.innerHTML = html;
  }

  function csrfToken() {
    var input = document.querySelector('#rca-ai-panel input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function asList(value) {
    if (value === null || value === undefined || value === '') return [];
    return Array.isArray(value) ? value : [value];
  }

  function listHtml(title, value) {
    var items = asList(value);
    if (!items.length) return '<h4>' + escapeHtml(title) + '</h4><p>-</p>';
    return '<h4>' + escapeHtml(title) + '</h4><ul>' + items.map(function (item) {
      return '<li>' + escapeHtml(text(item)) + '</li>';
    }).join('') + '</ul>';
  }

  function renderAnswer(result) {
    var target = document.getElementById('rca-ai-result');
    if (!target) return;
    if (!result || typeof result !== 'object') throw new Error('malformed response');
    var answer = result.answer || {};
    var provider = result.provider || {};
    var html = '<p><strong>Provider:</strong> ' + escapeHtml(text(provider.provider_kind)) +
      ' &middot; <strong>Model:</strong> ' + escapeHtml(text(provider.model_name)) + '</p>';
    if (answer.answer_text) {
      html += '<p>' + escapeHtml(answer.answer_text) + '</p>';
    } else {
      html += '<dl class="dl-horizontal">' +
        '<dt>Summary</dt><dd>' + escapeHtml(text(answer.summary)) + '</dd>' +
        '<dt>Likely failure area</dt><dd>' + escapeHtml(text(answer.likely_failure_area)) + '</dd>' +
        '<dt>Confidence</dt><dd>' + escapeHtml(text(answer.confidence)) + '</dd>' +
        '<dt>Limitations</dt><dd>' + escapeHtml(text(answer.limitations)) + '</dd>' +
        '</dl><div class="row">' +
        '<div class="col-md-4">' + listHtml('Evidence', answer.evidence) + '</div>' +
        '<div class="col-md-4">' + listHtml('Hypotheses', answer.hypotheses) + '</div>' +
        '<div class="col-md-4">' + listHtml('Recommended next checks', answer.recommended_next_checks) + '</div>' +
        '</div>';
    }
    target.innerHTML = html;
  }

  function setExplainState(loading, error) {
    var button = document.getElementById('rca-explain-button');
    var loadingEl = document.getElementById('rca-ai-loading');
    var errorEl = document.getElementById('rca-ai-error');
    if (button) {
      button.disabled = loading;
      button.textContent = loading ? 'Generating...' : 'Explain incident';
    }
    if (loadingEl) loadingEl.hidden = !loading;
    if (errorEl) {
      errorEl.hidden = !error;
      errorEl.textContent = error || '';
    }
  }

  function bindExplainButton() {
    var panel = document.getElementById('rca-ai-panel');
    var button = document.getElementById('rca-explain-button');
    if (!panel || !button) return;
    button.onclick = function () {
      var url = panel.getAttribute('data-explain-url');
      if (!url) {
        setExplainState(false, 'AI explanation failed. Backend returned: missing Horizon endpoint');
        return;
      }
      setExplainState(true, '');
      var target = document.getElementById('rca-ai-result');
      if (target) target.innerHTML = '<div class="rca-empty">Generating explanation...</div>';
      window.fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Accept': 'application/json',
          'X-CSRFToken': csrfToken()
        }
      }).then(function (response) {
        return response.text().then(function (body) {
          var data = {};
          try { data = body ? JSON.parse(body) : {}; } catch (e) { data = { error: body || 'malformed response' }; }
          if (!response.ok) {
            throw new Error(data.error || data.detail || ('HTTP ' + response.status));
          }
          return data;
        });
      }).then(function (data) {
        renderAnswer(data);
        setExplainState(false, '');
      }).catch(function (error) {
        setExplainState(false, 'AI explanation failed. Backend returned: ' + (error && error.message ? error.message : 'network failure'));
      });
    };
  }

  function selectTimelineRow(id) {
    Array.prototype.forEach.call(document.querySelectorAll('.rca-timeline-row'), function (row) {
      row.classList.toggle('selected', row.getAttribute('data-event-id') === id);
    });
  }

  function renderGraph() {
    var container = document.getElementById('rca-graph');
    if (!container) return;
    var graph = readGraphData();
    var nodes = graph.nodes || [];
    var edges = graph.edges || [];
    if (!nodes.length || typeof window.cytoscape !== 'function') {
      container.innerHTML = '<div class="rca-empty">Correlation graph unavailable.</div>';
      return;
    }

    var elements = [];
    nodes.forEach(function (node) {
      elements.push({
        group: 'nodes',
        data: {
          id: String(node.id),
          label: node.service || node.label || 'event',
          level: node.level,
          service: node.service,
          message: node.message,
          seed: Boolean(node.seed),
          raw: node
        },
        classes: nodeClass(node.level) + (node.seed ? ' seed' : '')
      });
    });
    edges.forEach(function (edge) {
      elements.push({
        group: 'edges',
        data: {
          id: String(edge.id),
          source: String(edge.source),
          target: String(edge.target),
          reason: edge.reason,
          confidence: edge.confidence,
          raw: edge
        },
        classes: edgeClass(edge.reason)
      });
    });

    var cy = window.cytoscape({
      container: container,
      elements: elements,
      layout: { name: 'cose', animate: false, fit: true, padding: 35 },
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.2,
      style: [
        { selector: 'node', style: {
          'background-color': '#2779bd',
          'border-color': '#55708f',
          'border-width': 2,
          'color': '#263238',
          'font-size': 10,
          'label': 'data(label)',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.85,
          'text-background-padding': 2,
          'text-valign': 'bottom',
          'text-wrap': 'wrap',
          'text-max-width': 80,
          'width': 36,
          'height': 36
        }},
        { selector: 'node.error', style: { 'background-color': '#c0392b' }},
        { selector: 'node.warning', style: { 'background-color': '#c98200' }},
        { selector: 'node.info', style: { 'background-color': '#2779bd' }},
        { selector: 'node.debug', style: { 'background-color': '#697386' }},
        { selector: 'node.seed', style: { 'border-color': '#263238', 'border-width': 5 }},
        { selector: 'node:selected, node.rca-selected', style: { 'border-color': '#111827', 'border-width': 6 }},
        { selector: 'edge', style: {
          'curve-style': 'bezier',
          'line-color': '#9aa6b2',
          'target-arrow-color': '#9aa6b2',
          'target-arrow-shape': 'triangle',
          'width': 2,
          'opacity': 0.85
        }},
        { selector: 'edge.same-request', style: { 'line-color': '#6f42c1', 'target-arrow-color': '#6f42c1' }},
        { selector: 'edge.shared-resource', style: { 'line-color': '#00897b', 'target-arrow-color': '#00897b' }},
        { selector: 'edge:selected, edge.rca-selected', style: { 'width': 5, 'opacity': 1 }}
      ]
    });

    function showNode(node) {
      cy.elements().removeClass('rca-selected');
      node.addClass('rca-selected');
      selectTimelineRow(node.id());
      var data = node.data('raw') || {};
      setDetails(detailHtml('Selected event', [
        ['Event ID', node.id()],
        ['Level', data.level],
        ['Service', data.service || data.label],
        ['Seed', data.seed ? 'yes' : 'no'],
        ['Message', data.message]
      ]));
      cy.animate({ center: { eles: node }, duration: 150 });
    }

    cy.on('tap', 'node', function (event) { showNode(event.target); });
    cy.on('tap', 'edge', function (event) {
      var edge = event.target;
      cy.elements().removeClass('rca-selected');
      edge.addClass('rca-selected');
      setDetails(detailHtml('Selected correlation edge', [
        ['Edge ID', edge.id()],
        ['Source', edge.data('source')],
        ['Target', edge.data('target')],
        ['Reason', edge.data('reason')],
        ['Confidence', edge.data('confidence')]
      ]));
    });

    Array.prototype.forEach.call(document.querySelectorAll('.rca-timeline-row'), function (row) {
      row.onclick = function () {
        var id = row.getAttribute('data-event-id');
        var node = cy.getElementById(id);
        if (node && node.length) showNode(node);
      };
    });

    Array.prototype.forEach.call(document.querySelectorAll('[data-graph-action]'), function (button) {
      button.onclick = function () {
        var action = button.getAttribute('data-graph-action');
        if (action === 'fit') cy.fit(undefined, 35);
        if (action === 'zoom-in') cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: container.clientWidth / 2, y: container.clientHeight / 2 } });
        if (action === 'zoom-out') cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: container.clientWidth / 2, y: container.clientHeight / 2 } });
      };
    });

    window.rcaCorrelationGraph = cy;
  }

  document.addEventListener('DOMContentLoaded', function () {
    renderGraph();
    bindExplainButton();
  });
}());
