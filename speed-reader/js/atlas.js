// atlas.js — minimal radial renderer for the library's Atlas tab.
// v1: single concept ring. Topic-center-disc, cardinals, rotor ticks,
// and the full orrery polish from mockups/mindmap-radial.html come later
// (phase 2) once user-supplied tags gain topic metadata.
//
// Exported function: render(svgSelector, { concepts, sources, onConceptClick })
// Shape-gracefully handles malformed/missing input.

/**
 * @typedef {Object} Concept
 * @property {string} id
 * @property {string} label
 * @property {string[]} source_ids
 */

/**
 * @typedef {Object} Source
 * @property {string} id
 * @property {string} title
 */

/**
 * Render a minimal radial atlas into an SVG element.
 * @param {string} svgSelector
 * @param {{ concepts: Concept[], sources: Source[], onConceptClick?: (id: string) => void }} data
 */
export function render(svgSelector, data) {
  const svgEl = typeof svgSelector === 'string'
    ? document.querySelector(svgSelector)
    : svgSelector;
  if (!svgEl) {
    console.warn('atlas: svg element not found', svgSelector);
    return;
  }
  if (typeof window.d3 === 'undefined') {
    console.warn('atlas: d3 not loaded');
    return;
  }
  const d3 = window.d3;

  // normalize input
  const rawConcepts = Array.isArray(data && data.concepts) ? data.concepts : [];
  const rawSources = Array.isArray(data && data.sources) ? data.sources : [];
  const onConceptClick = typeof (data && data.onConceptClick) === 'function'
    ? data.onConceptClick
    : () => {};

  const validConcepts = rawConcepts
    .filter(c => c && typeof c.id === 'string' && typeof c.label === 'string')
    .map(c => ({
      id: c.id,
      label: c.label,
      source_ids: Array.isArray(c.source_ids) ? c.source_ids.slice() : [],
    }));

  if (!validConcepts.length) {
    // nothing to draw — leave an empty message
    const svg = d3.select(svgEl);
    svg.selectAll('*').remove();
    const r = svgEl.getBoundingClientRect();
    svg.attr('viewBox', `0 0 ${r.width} ${r.height}`);
    svg.append('text')
      .attr('x', r.width / 2)
      .attr('y', r.height / 2)
      .attr('text-anchor', 'middle')
      .attr('fill', 'var(--ink-mute)')
      .attr('font-family', 'JetBrains Mono, ui-monospace, monospace')
      .attr('font-size', 11)
      .attr('letter-spacing', '0.2em')
      .text('NO CONCEPTS YET');
    return;
  }

  // take top N=min(12, concepts.length) by count
  const N = Math.min(12, validConcepts.length);
  const topConcepts = validConcepts
    .slice()
    .sort((a, b) => b.source_ids.length - a.source_ids.length)
    .slice(0, N);

  // build co-occurrence edges: concepts that share a source_id
  // map source_id -> concepts that tag it
  const sourceToConcepts = new Map();
  topConcepts.forEach(c => {
    c.source_ids.forEach(sid => {
      if (!sourceToConcepts.has(sid)) sourceToConcepts.set(sid, []);
      sourceToConcepts.get(sid).push(c.id);
    });
  });
  const edgeSet = new Map(); // key -> { source, target, weight }
  sourceToConcepts.forEach(ids => {
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = ids[i], b = ids[j];
        const key = a < b ? `${a}__${b}` : `${b}__${a}`;
        const existing = edgeSet.get(key);
        if (existing) {
          existing.weight += 1;
        } else {
          edgeSet.set(key, { source: a, target: b, weight: 1 });
        }
      }
    }
  });
  const edges = Array.from(edgeSet.values());

  // --- draw ---
  const svg = d3.select(svgEl);
  svg.selectAll('*').remove();
  const rect = svgEl.getBoundingClientRect();
  const W = rect.width || 800;
  const H = rect.height || 600;
  const cx = W / 2;
  const cy = H / 2;
  svg.attr('viewBox', `0 0 ${W} ${H}`);

  const maxR = Math.min(W, H) * 0.42;
  const ringR = maxR * 0.72;

  // node sizing: scale by count
  const maxCount = Math.max(1, ...topConcepts.map(c => c.source_ids.length));
  const nodeR = d3.scaleLinear().domain([0, maxCount]).range([7, 16]);

  // concept node positions
  const nodes = topConcepts.map((c, i) => {
    const angle = (i / topConcepts.length) * Math.PI * 2 - Math.PI / 2;
    return {
      id: c.id,
      label: c.label,
      count: c.source_ids.length,
      angle,
      x: cx + Math.cos(angle) * ringR,
      y: cy + Math.sin(angle) * ringR,
      r: nodeR(c.source_ids.length),
    };
  });
  const nodeById = new Map(nodes.map(n => [n.id, n]));

  // layers
  const gPlate = svg.append('g').attr('class', 'plate-layer');
  const gLinks = svg.append('g').attr('class', 'links');
  const gNodes = svg.append('g').attr('class', 'concepts');

  // decorative outer plate + dashed inner ring (echo of the radial mockup)
  gPlate.append('circle')
    .attr('class', 'plate')
    .attr('cx', cx).attr('cy', cy).attr('r', maxR);
  gPlate.append('circle')
    .attr('class', 'plate dashed')
    .attr('cx', cx).attr('cy', cy).attr('r', ringR);

  // edges as gentle curves pulled toward the center
  function arc(x1, y1, x2, y2) {
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const dx = cx - mx;
    const dy = cy - my;
    const pull = 0.18;
    const qx = mx + dx * pull;
    const qy = my + dy * pull;
    return `M${x1},${y1} Q${qx},${qy} ${x2},${y2}`;
  }

  gLinks.selectAll('path.link')
    .data(edges.filter(e => nodeById.has(e.source) && nodeById.has(e.target)))
    .enter()
    .append('path')
    .attr('class', 'link')
    .attr('data-source', d => d.source)
    .attr('data-target', d => d.target)
    .attr('d', d => {
      const a = nodeById.get(d.source);
      const b = nodeById.get(d.target);
      return arc(a.x, a.y, b.x, b.y);
    })
    .style('stroke-width', d => Math.min(2, 0.8 + d.weight * 0.25));

  // nodes
  const nodeSel = gNodes.selectAll('g.node-concept')
    .data(nodes, d => d.id)
    .enter()
    .append('g')
    .attr('class', 'node node-concept')
    .attr('data-action', 'concept')
    .attr('data-concept-id', d => d.id)
    .attr('transform', d => `translate(${d.x},${d.y})`)
    .attr('tabindex', 0)
    .attr('role', 'button')
    .attr('aria-label', d => `${d.label} — ${d.count} source${d.count === 1 ? '' : 's'}`);

  nodeSel.append('circle').attr('r', d => d.r);

  // labels: push outward from node, orient based on angle
  nodeSel.append('text')
    .attr('class', 'concept-label')
    .attr('text-anchor', d => {
      const cosA = Math.cos(d.angle);
      if (cosA > 0.25) return 'start';
      if (cosA < -0.25) return 'end';
      return 'middle';
    })
    .attr('dy', d => {
      const sinA = Math.sin(d.angle);
      if (sinA > 0.6) return '1em';
      if (sinA < -0.6) return '-0.3em';
      return '0.35em';
    })
    .attr('x', d => Math.cos(d.angle) * (d.r + 8))
    .attr('y', d => Math.sin(d.angle) * (d.r + 8))
    .text(d => d.label);

  // click handlers
  nodeSel.on('click', (event, d) => {
    event.stopPropagation();
    onConceptClick(d.id);
  });
  nodeSel.on('keydown', (event, d) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onConceptClick(d.id);
    }
  });
}
