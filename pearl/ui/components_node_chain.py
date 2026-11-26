from __future__ import annotations

import html
import json
from typing import Any

from history.node_models import NodeRecord


# HTML_TEMPLATE = """
# <div class='chain-root'>
#   {{{value}}}
# </div>
# """


CSS_TEMPLATE = """
.chain-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 12px;
  background: #f7f8fb;
  border-radius: 12px;
  min-height: 240px;
}

.chain-round {
  border: 1px solid #cfd7e3;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
}

.chain-round-current {
  border-color: #7ca6e8;
  box-shadow: 0 0 0 1px rgba(66, 113, 214, 0.16) inset;
}

.chain-round-past {
  border-color: #d9dee8;
  background: #fafbfc;
}

.chain-round-summary {
  list-style: none;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
  user-select: none;
}

.chain-round-summary::-webkit-details-marker {
  display: none;
}

.chain-round-summary-left,
.chain-round-summary-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chain-round-summary-left {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.chain-round-summary-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chain-round-summary-meta {
  color: #5a6983;
  font-size: 12px;
}

.chain-round-label {
  font-weight: 700;
  color: #20304a;
}

.chain-round-id {
  color: #67758d;
  font-family: monospace;
  font-size: 12px;
}

.chain-round-pill {
  padding: 2px 8px;
  border-radius: 999px;
  background: #e8f1ff;
  color: #2257a0;
  font-size: 11px;
  font-weight: 700;
}

.chain-round-count {
  color: #6d7687;
  font-size: 12px;
}

.chain-round-body {
  padding: 12px 14px 14px;
}

.chain-round-selected {
  margin-bottom: 10px;
  color: #5b6678;
  font-size: 12px;
}

.chain-round-nodes {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chain-node {
  border: 1px solid #d8dfeb;
  background: #ffffff;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: 120ms ease;
}

.chain-node:hover {
  border-color: #4271d6;
  box-shadow: 0 2px 12px rgba(27, 55, 141, 0.16);
  transform: translateX(2px);
}

.chain-node-normal {
  border-color: #d7deea;
  background: #ffffff;
}

.chain-node-exec-sql {
  border-color: #1f8b63;
  background: linear-gradient(180deg, #ffffff 0%, #f4fff9 100%);
}

.chain-node-sql-gen {
  border-color: #1f8b63;
  background: linear-gradient(180deg, #ffffff 0%, #f4fff9 100%);
}

.chain-node-cand-gen {
  border-color: #7b5cd6;
  background: linear-gradient(180deg, #ffffff 0%, #faf6ff 100%);
}

.chain-node-ambi-detect {
  border-color: #e28b26;
  background: linear-gradient(180deg, #ffffff 0%, #fff8ef 100%);
}

.chain-node-ambi-eval {
  border-color: #b94f8a;
  background: linear-gradient(180deg, #ffffff 0%, #fff5fb 100%);
}

.chain-node-exec-sql-issue {
  border-color: #ca3d3d;
  background: linear-gradient(180deg, #ffffff 0%, #fff5f5 100%);
}

.chain-node-mixture {
  border-color: #8e63d5;
  background: linear-gradient(180deg, #ffffff 0%, #faf6ff 100%);
}

.chain-node-manager {
  border-color: #d5dbe6;
  background: #ffffff;
}

.chain-node-compact-summary {
  border-color: #d5dbe6;
  background: #ffffff;
  opacity: 0.92;
}

.chain-node-selected {
  border-color: #1565c0;
  box-shadow: 0 2px 12px rgba(21, 101, 192, 0.20);
}

.chain-node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.chain-node-title {
  font-weight: 700;
  color: #1f2838;
}

.chain-node-id {
  color: #657088;
  font-family: monospace;
  font-size: 12px;
}

.chain-node-id-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chain-node-pill {
  padding: 1px 7px;
  border-radius: 999px;
  background: #e8f1ff;
  color: #2257a0;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.chain-node-summary {
  margin-top: 4px;
  color: #38445d;
  font-size: 13px;
  white-space: pre-line;
}

.chain-node-issue {
  margin-top: 6px;
  color: #50607c;
  font-size: 12px;
  font-style: italic;
  white-space: pre-line;
}

.chain-node-hover-details {
  display: none;
  margin-top: 7px;
  padding-top: 6px;
  border-top: 1px dashed #c8d1e0;
  color: #4d5972;
  font-size: 12px;
  white-space: normal;
}

.chain-node:hover .chain-node-hover-details {
  display: grid;
  gap: 10px;
}

.detail-block {
  border: 1px solid #dde5f0;
  border-radius: 8px;
  background: #fbfdff;
  padding: 8px;
}

.detail-label {
  font-size: 11px;
  font-weight: 700;
  color: #314666;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 4px;
}

.detail-text {
  font-size: 12px;
  color: #40506c;
  white-space: pre-wrap;
}

.detail-block pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.sql-block {
  background: #f4f7fb;
  border-radius: 6px;
  padding: 8px;
}

.result-table-wrap {
  max-height: 220px;
  overflow: auto;
  border: 1px solid #dce4ef;
  border-radius: 6px;
  background: #fff;
}

.result-table-wrap table {
  border-collapse: collapse;
  width: 100%;
  font-size: 12px;
}

.result-table-wrap th,
.result-table-wrap td {
  border: 1px solid #e3e9f3;
  padding: 4px 6px;
}

.detail-list {
  margin: 0;
  padding-left: 18px;
}

.detail-list li {
  margin: 2px 0;
  overflow-wrap: anywhere;
}

.retrieved-options {
  display: grid;
  gap: 10px;
}

.retrieved-option-group {
  display: grid;
  gap: 4px;
  padding: 8px;
  border: 1px solid #dce4ef;
  border-radius: 8px;
  background: #fff;
}

.retrieved-option-group .detail-label {
  margin-bottom: 0;
}

/* ============================================================
   GRAPH TOGGLE + SECTION
   ============================================================ */
.graph-toggle-bar {
  margin-bottom: 10px;
}
.graph-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border: 1px solid #cfd7e3;
  border-radius: 8px;
  background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
  color: #2a405c;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: 140ms ease;
  user-select: none;
}
.graph-toggle-btn:hover {
  border-color: #7ca6e8;
  background: linear-gradient(180deg, #ffffff 0%, #e8f1ff 100%);
  box-shadow: 0 2px 8px rgba(66, 113, 214, 0.12);
}
.graph-toggle-icon {
  font-size: 12px;
  transition: transform 200ms ease;
}
.graph-toggle-btn.active .graph-toggle-icon {
  transform: rotate(90deg);
}

.node-graph-section {
  border: 1px solid #cfd7e3;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
  margin-bottom: 14px;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  background: #f7faff;
  border-bottom: 1px solid #e3e9f3;
}
.graph-title {
  font-weight: 700;
  color: #20304a;
  font-size: 14px;
}
.graph-hint {
  color: #67758d;
  font-size: 11px;
  font-style: italic;
}

.graph-svg-wrap {
  padding: 12px;
  overflow-x: auto;
}
#nodeGraphSvg {
  display: block;
}

.graph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 8px 14px 10px;
  border-top: 1px solid #e3e9f3;
  background: #fafbfc;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #4d5972;
}
.legend-swatch {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.12);
}
.legend-round-swatch {
  background: #e8f1ff;
  border-color: #4271d6;
}
.legend-normal-swatch {
  background: #f5f7fa;
  border-color: #bbb;
}
.legend-issue-swatch {
  background: #fff0f0;
  border-color: #ca3d3d;
}
.legend-sql-swatch {
  background: #f0fff4;
  border-color: #1f8b63;
}
.legend-line-swatch,
.legend-line-dashed-swatch,
.legend-line-attended-swatch {
  display: inline-block;
  width: 20px;
  height: 2px;
  border-radius: 1px;
}
.legend-line-swatch {
  background: #999;
}
.legend-line-dashed-swatch {
  background: transparent;
  border-top: 2px dashed #999;
}
.legend-line-attended-swatch {
  background: transparent;
  border-top: 2px dashed #ca3d3d;
}

/* Tooltip for ambiguity evaluator nodes */
.graph-tooltip {
  position: fixed;
  z-index: 9999;
  background: #ffffff;
  border: 1px solid #d6dfec;
  padding: 8px 10px;
  border-radius: 6px;
  box-shadow: 0 6px 20px rgba(30,50,93,0.12);
  font-size: 12px;
  color: #243449;
  max-width: 360px;
}
.graph-tooltip table { border-collapse: collapse; width: 100%; }
.graph-tooltip th, .graph-tooltip td { padding: 4px 6px; border-bottom: 1px solid #eef3fa; text-align: left; }
.graph-tooltip th { font-weight: 700; font-size: 12px; }

/* ============================================================
   ATTENDED LINK STYLES
   ============================================================ */
.attended-link {
  color: #2257a0;
  text-decoration: underline;
  text-decoration-style: dotted;
  cursor: pointer;
  font-family: monospace;
  font-size: 12px;
  padding: 1px 4px;
  border-radius: 4px;
  transition: 120ms ease;
  font-weight: 600;
}
.attended-link:hover {
  background: #e8f1ff;
  color: #174282;
  text-decoration-style: solid;
}
.attended-link:active {
  background: #d0e2ff;
}
.attended-empty {
  color: #8a96a8;
  font-style: italic;
}

/* ============================================================
   BLINK HIGHLIGHT ANIMATION
   ============================================================ */
@keyframes node-blink {
  0%, 100% {
    outline: 3px solid transparent;
    box-shadow: none;
  }
  25% {
    outline: 3px solid #ff5252;
    box-shadow: 0 0 16px rgba(255, 82, 82, 0.5), inset 0 0 8px rgba(255, 82, 82, 0.1);
  }
  50% {
    outline: 3px solid transparent;
    box-shadow: none;
  }
  75% {
    outline: 3px solid #ff5252;
    box-shadow: 0 0 16px rgba(255, 82, 82, 0.5), inset 0 0 8px rgba(255, 82, 82, 0.1);
  }
}
.node-blink {
  animation: node-blink 0.9s ease-in-out 2;
  border-radius: 10px;
}

/* ============================================================
   SVG GRAPH ELEMENT STYLES
   ============================================================ */
.graph-step-node {
  cursor: pointer;
  transition: opacity 120ms ease;
}
.graph-step-node:hover {
  opacity: 0.85;
}
.graph-step-node rect {
  rx: 6;
  ry: 6;
}
.graph-step-node text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  fill: #1f2838;
  pointer-events: none;
  text-anchor: middle;
  dominant-baseline: central;
}
.graph-round-node {
  cursor: pointer;
  transition: opacity 120ms ease;
}
.graph-round-node:hover {
  opacity: 0.85;
}
.graph-round-node text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 700;
  fill: #20304a;
  pointer-events: none;
  text-anchor: middle;
  dominant-baseline: central;
}
.graph-edge {
  fill: none;
  stroke-width: 1.5;
}
.graph-edge-sequential {
  stroke: #999;
  stroke-width: 1.5;
}
.graph-edge-belong {
  stroke: #999;
  stroke-width: 1.5;
  stroke-dasharray: 5 3;
}
.graph-edge-attended {
  stroke: #ca3d3d;
  stroke-width: 2;
  stroke-dasharray: 6 4;
}

/* Specification answer cards */
.detail-specification {
  padding: 8px 4px;
}
.spec-answer-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  background: #fafcff;
}
.spec-answer-card:last-child {
  margin-bottom: 0;
}
.spec-answer-qid {
  display: inline-block;
  font-weight: 700;
  font-size: 12px;
  color: #1d3f6e;
  background: #e8edf8;
  padding: 2px 8px;
  border-radius: 4px;
  margin-bottom: 6px;
}
.spec-answer-question {
  font-size: 13px;
  color: #2d3a54;
  margin-bottom: 8px;
  line-height: 1.5;
}
.spec-answer-choices {
  margin-bottom: 6px;
}
.spec-answer-choice {
  font-size: 13px;
  color: #2d3a54;
  padding: 2px 0;
}
.spec-answer-choice.selected {
  color: #1b5e20;
  font-weight: 600;
}
.spec-answer-note {
  font-size: 13px;
  color: #546680;
  margin-top: 4px;
  padding: 4px 8px;
  background: #f5f8fc;
  border-radius: 4px;
}
.spec-answer-label {
  font-weight: 600;
  font-size: 12px;
  color: #1d3f6e;
}
.spec-answer-rationale {
  margin-top: 8px;
  border-top: 1px dashed #d6dfec;
  padding-top: 6px;
  font-size: 12px;
}
.spec-answer-rationale summary {
  cursor: pointer;
  font-weight: 600;
  color: #1d3f6e;
  font-size: 12px;
}
.spec-answer-rationale[open] .spec-answer-rationale-text {
  margin-top: 6px;
  color: #546680;
  line-height: 1.5;
  padding: 6px;
  background: #f5f8ff;
  border-radius: 4px;
}

/* ============================================================
   MARKDOWN RENDERED CONTENT
   ============================================================ */
.markdown-rendered {
  line-height: 1.6;
  color: #2d3a54;
  font-size: 13px;
}

.markdown-rendered h1,
.markdown-rendered h2,
.markdown-rendered h3,
.markdown-rendered h4,
.markdown-rendered h5,
.markdown-rendered h6 {
  margin: 12px 0 8px 0;
  font-weight: 600;
  color: #1a2540;
}

.markdown-rendered h1 { font-size: 1.4em; margin-top: 16px; }
.markdown-rendered h2 { font-size: 1.25em; margin-top: 14px; }
.markdown-rendered h3 { font-size: 1.1em; }
.markdown-rendered h4,
.markdown-rendered h5,
.markdown-rendered h6 { font-size: 1em; }

.markdown-rendered p {
  margin: 8px 0;
  overflow-wrap: break-word;
}

.markdown-rendered ul,
.markdown-rendered ol {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-rendered li {
  margin: 4px 0;
  overflow-wrap: break-word;
}

.markdown-rendered ul ul,
.markdown-rendered ul ol,
.markdown-rendered ol ul,
.markdown-rendered ol ol {
  margin: 4px 0;
}

.markdown-rendered code {
  background: #f5f7fa;
  border: 1px solid #e3e9f3;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
  color: #ca3d3d;
}

.markdown-rendered pre {
  background: #2d3a54;
  color: #e8eaed;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.9em;
  line-height: 1.4;
}

.markdown-rendered pre code {
  background: transparent;
  border: none;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

.markdown-rendered blockquote {
  margin: 8px 0;
  padding-left: 16px;
  border-left: 4px solid #d6dfec;
  color: #546680;
  font-style: italic;
}

.markdown-rendered strong {
  font-weight: 700;
  color: #1a2540;
}

.markdown-rendered em {
  font-style: italic;
  color: #2d3a54;
}

.markdown-rendered a {
  color: #2257a0;
  text-decoration: underline;
  cursor: pointer;
}

.markdown-rendered a:hover {
  color: #174282;
  text-decoration-style: solid;
}

.markdown-rendered table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 0.95em;
}

.markdown-rendered table th,
.markdown-rendered table td {
  border: 1px solid #d6dfec;
  padding: 8px 12px;
  text-align: left;
}

.markdown-rendered table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #1a2540;
}

.markdown-rendered table tr:nth-child(even) {
  background: #fafbfc;
}

.markdown-rendered hr {
  margin: 12px 0;
  border: none;
  border-top: 1px solid #d6dfec;
}

/* Syntax highlighting for code blocks */
.markdown-rendered .highlight {
  background: #2d3a54;
  border-radius: 4px;
  overflow-x: auto;
}

/* Fallback for markdown rendering errors */
.markdown-rendered.markdown-fallback pre {
  background: #f5f7fa;
  color: #2d3a54;
  border: 1px solid #e3e9f3;
}
"""


JS_ON_LOAD = """
(function() {
  if (window.__nl2sqlChainNavBound) return;
  window.__nl2sqlChainNavBound = true;

  // ==================== EVENT DELEGATION ====================
  document.addEventListener('click', function(event) {
    // 1. Node selection for Gradio backend (existing behavior)
    var node = event.target.closest('.chain-node');
    if (node) {
      var selectedId = node.dataset.nodeId;
      if (selectedId) {
        trigger('select', { index: selectedId, value: selectedId, selected: true });
      }
      return;
    }

    // 2. Attended link navigation
    var attendedLink = event.target.closest('.attended-link');
    if (attendedLink) {
      event.preventDefault();
      var nid = attendedLink.getAttribute('data-attended-id');
      if (nid) { navigateToNode(nid); }
      return;
    }

    // 3. Graph toggle button
    if (event.target.closest('#graphToggleBtn')) {
      toggleGraph();
      return;
    }

    // 4. Graph SVG step node
    var graphNode = event.target.closest('.graph-step-node');
    if (graphNode) {
      var gid = graphNode.getAttribute('data-node-id');
      if (gid) { navigateToNode(gid); }
      return;
    }

    // 5. Graph SVG round node
    var graphRound = event.target.closest('.graph-round-node');
    if (graphRound) {
      var rid = graphRound.getAttribute('data-round-id');
      if (rid) { navigateToRound(rid); }
      return;
    }
  });

  // ==================== CONSTANTS ====================
  var ROW_HEIGHT = 120;
  var TOP_PAD = 30;
  var ROUND_CX = 70;
  var ROUND_R = 22;
  var NODE_START_X = 160;
  var NODE_WIDTH = 140;
  var NODE_HEIGHT = 44;
  var NODE_GAP = 32;
  var NODE_SPACING = NODE_WIDTH + NODE_GAP;
  var COLOR_MAP = {
    'compact-summary':{ fill: '#f5f7fa', stroke: '#bbb',   text: '#1f2838' },
    'normal':         { fill: '#f5f7fa', stroke: '#bbb',   text: '#1f2838' },
    'sql-gen':        { fill: '#f0fff4', stroke: '#1f8b63', text: '#1f2838' },
    'cand-gen':       { fill: '#faf6ff', stroke: '#7b5cd6', text: '#1f2838' },
    'ambi-detect':    { fill: '#fff8ef', stroke: '#e28b26', text: '#1f2838' },
    'ambi-eval':      { fill: '#fff5fb', stroke: '#b94f8a', text: '#1f2838' },
    'exec-sql-issue': { fill: '#fff0f0', stroke: '#ca3d3d', text: '#ca3d3d' },
    'exec-sql':       { fill: '#f0fff4', stroke: '#1f8b63', text: '#1f2838' },
    'mixture':        { fill: '#faf6ff', stroke: '#8e63d5', text: '#1f2838' },
    'ambi-detail-fixed': { fill: '#e8f5e9', stroke: '#2e7d32', text: '#1f2838' },
    'ambi-detail-user-fixed': { fill: '#e3f2fd', stroke: '#1976d2', text: '#1f2838' },
    'ambi-detail-skipped': { fill: '#f5f5f5', stroke: '#616161', text: '#1f2838' },
  };

  // ==================== DATA EXTRACTION ====================
  function extractRoundData() {
    var rounds = [];
    document.querySelectorAll('.chain-round').forEach(function(roundEl) {
      var roundIdEl = roundEl.querySelector('.chain-round-id');
      var roundId = roundIdEl ? roundIdEl.textContent.trim() : '';
      var roundLabelEl = roundEl.querySelector('.chain-round-label');
      var roundLabel = roundLabelEl ? roundLabelEl.textContent.trim() : '';

      // Attended IDs from server-rendered <a> links
      var metaEl = roundEl.querySelector('.chain-round-summary-meta');
      var attended = [];
      if (metaEl) {
        metaEl.querySelectorAll('.attended-link').forEach(function(link) {
          var id = link.getAttribute('data-attended-id');
          if (id) attended.push(id);
        });
      }

      var nodes = [];
      roundEl.querySelectorAll('.chain-node').forEach(function(nodeEl) {
        var nodeId = nodeEl.getAttribute('data-node-id') || '';
        var titleEl = nodeEl.querySelector('.chain-node-title');
        var title = titleEl ? titleEl.textContent.trim() : nodeId;
        var cls = 'normal';
        if (nodeEl.classList.contains('chain-node-sql-gen')) cls = 'sql-gen';
        else if (nodeEl.classList.contains('chain-node-cand-gen')) cls = 'cand-gen';
        else if (nodeEl.classList.contains('chain-node-ambi-detect')) cls = 'ambi-detect';
        else if (nodeEl.classList.contains('chain-node-ambi-eval')) cls = 'ambi-eval';
        if (nodeEl.classList.contains('chain-node-exec-sql-issue')) cls = 'exec-sql-issue';
        else if (nodeEl.classList.contains('chain-node-exec-sql')) cls = 'exec-sql';
        else if (nodeEl.classList.contains('chain-node-mixture')) cls = 'mixture';
        
        // Extract detail records if present
        var detailRecordsAttr = nodeEl.getAttribute('data-detail-records');
        var parentsAttr = nodeEl.getAttribute('data-parents');
        var detailRecords = detailRecordsAttr ? JSON.parse(detailRecordsAttr) : [];
        var parents = parentsAttr ? JSON.parse(parentsAttr) : [];
        
        nodes.push({ id: nodeId, title: title, cls: cls, el: nodeEl, detailRecords: detailRecords, parents: parents });
        
        // Create synthetic child nodes for each detail record
        detailRecords.forEach(function(record) {
          var detailId = record.detail_id || '';
          var detailTitle = record.context_preview || record.ambiguity_context || 'Detail: ' + detailId;
          var detailCls = 'ambi-detail-skipped';
          if (record.is_fixed && record.fixed_by) {
            detailCls = record.fixed_by === 'user' ? 'ambi-detail-user-fixed' : 'ambi-detail-fixed';
          }
          var selCount = 0;
          if (typeof record.selected_choice_count === 'number') selCount = record.selected_choice_count;
          else if (Array.isArray(record.preselect_option_idxs)) selCount = record.preselect_option_idxs.length;
          else selCount = (record.is_fixed ? 1 : 0);
          nodes.push({
            id: nodeId + '.detail.' + detailId,
            title: detailTitle,
            cls: detailCls,
            el: null,
            parent_node_id: nodeId,
            detail_id: detailId,
            is_detail: true,
            is_fixed: !!record.is_fixed,
            fixed_by: record.fixed_by || '',
            selected_choice_count: selCount,
            context_preview: detailTitle
          });
        });
      });

      var isCurrent = roundEl.classList.contains('chain-round-current');
      rounds.push({ id: roundId, label: roundLabel, attended: attended, nodes: nodes, isCurrent: isCurrent, el: roundEl });
    });
    return rounds;
  }

  function findNodeById(rounds, nodeId) {
    for (var i = 0; i < rounds.length; i++) {
      for (var j = 0; j < rounds[i].nodes.length; j++) {
        if (rounds[i].nodes[j].id === nodeId) return { roundIdx: i, nodeIdx: j, data: rounds[i].nodes[j] };
      }
    }
    return null;
  }

  function findFinalAnswerNode(rounds, roundIdx) {
    return null; // disable
    if (roundIdx < 0 || roundIdx >= rounds.length) return null;
    for (var j = 0; j < rounds[roundIdx].nodes.length; j++) {
      if (rounds[roundIdx].nodes[j].title === 'Final Answer') return { roundIdx: roundIdx, nodeIdx: j, data: rounds[roundIdx].nodes[j] };
    }
    return null;
  }

  // ==================== POSITION HELPERS ====================
  function getRoundCenter(roundIdx) {
    return { x: ROUND_CX, y: roundIdx * ROW_HEIGHT + TOP_PAD + ROW_HEIGHT / 2 };
  }

  function getNodeCenter(roundIdx, nodeIdx) {
    return { x: NODE_START_X + nodeIdx * NODE_SPACING + NODE_WIDTH / 2, y: roundIdx * ROW_HEIGHT + TOP_PAD + ROW_HEIGHT / 2 };
  }

  function getCircleEdgePoint(cx, cy, targetX, targetY) {
    var dx = targetX - cx, dy = targetY - cy;
    var dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 0.001) return { x: cx + ROUND_R, y: cy };
    return { x: cx + ROUND_R * dx / dist, y: cy + ROUND_R * dy / dist };
  }

  function getRectEdgePoint(centerX, centerY, targetX, targetY, w, h) {
    var dx = targetX - centerX, dy = targetY - centerY;
    if (Math.abs(dx) < 0.001 && Math.abs(dy) < 0.001) return { x: centerX - w / 2, y: centerY };
    var hw = w / 2, hh = h / 2;
    var sx = dx !== 0 ? Math.abs(hw / dx) : Infinity;
    var sy = dy !== 0 ? Math.abs(hh / dy) : Infinity;
    var scale = Math.min(sx, sy);
    return { x: centerX + dx * scale * 0.92, y: centerY + dy * scale * 0.92 };
  }

  // ==================== SVG HELPERS ====================
  function createSvg(tag, attrs) {
    var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (var k in attrs) { if (attrs.hasOwnProperty(k)) el.setAttribute(k, attrs[k]); }
    return el;
  }

  function addArrowDef(svg, id, color) {
    var defs = svg.querySelector('defs');
    if (!defs) { defs = createSvg('defs', {}); svg.insertBefore(defs, svg.firstChild); }
    var marker = createSvg('marker', {
      id: id, markerWidth: 8, markerHeight: 6, refX: 7, refY: 3,
      orient: 'auto', markerUnits: 'strokeWidth'
    });
    marker.appendChild(createSvg('path', { d: 'M0,0 L8,3 L0,6 Z', fill: color }));
    defs.appendChild(marker);
  }

  // Tooltip helpers for ambi-eval nodes
  function ensureTooltip() {
    var t = document.getElementById('graphTooltip');
    if (!t) {
      t = document.createElement('div');
      t.id = 'graphTooltip';
      t.className = 'graph-tooltip';
      t.style.display = 'none';
      document.body.appendChild(t);
    }
    return t;
  }

  function showAmbiTooltip(evt, nodeId) {
    try {
      var tooltip = ensureTooltip();
      var scopeRounds = window.__roundsData || [];
      var nodeDataWrapper = findNodeById(scopeRounds, nodeId) || null;
      var details = nodeDataWrapper && nodeDataWrapper.data && nodeDataWrapper.data.detailRecords ? nodeDataWrapper.data.detailRecords : [];
      if (!details || details.length === 0) {
        tooltip.style.display = 'none';
        return;
      }
      var totalChoices = 0;
      var selectedChoices = 0;
      var rows = [];
      details.forEach(function(rec) {
        var ctx = rec.ambiguity_context || rec.context_preview || rec.ambiguity_context_descrip || '';
        var opts = rec.options || rec.Options || rec.ambi_options || [];
        var optCount = Array.isArray(opts) ? opts.length : 0;
        totalChoices += optCount;
        var sel = 0;
        if (typeof rec.selected_choice_count === 'number') sel = rec.selected_choice_count;
        else if (Array.isArray(rec.preselect_option_idxs)) sel = rec.preselect_option_idxs.length;
        else if (rec.is_fixed && rec.preselect_option_idxs && rec.preselect_option_idxs.length) sel = rec.preselect_option_idxs.length;
        else sel = (rec.is_fixed ? 1 : 0);
        selectedChoices += sel;
        rows.push({ctx: ctx, opts: optCount, sel: sel});
      });

      var html = '<div style="font-weight:700;margin-bottom:6px">Ambiguity details</div>';
      html += '<table><thead><tr><th>Context</th><th style="width:70px">Choices</th><th style="width:70px">Selected</th></tr></thead><tbody>';
      rows.forEach(function(r){ html += '<tr><td>' + (r.ctx ? r.ctx : '&mdash;') + '</td><td>' + r.opts + '</td><td>' + r.sel + '</td></tr>'; });
      html += '<tr style="font-weight:700"><td>Total</td><td>' + totalChoices + '</td><td>' + selectedChoices + '</td></tr>';
      html += '</tbody></table>';

      tooltip.innerHTML = html;
      tooltip.style.display = 'block';
      var x = evt.pageX + 12;
      var y = evt.pageY + 12;
      var winW = window.innerWidth || document.documentElement.clientWidth;
      var winH = window.innerHeight || document.documentElement.clientHeight;
      var rect = tooltip.getBoundingClientRect();
      if (x + rect.width > winW - 8) x = winW - rect.width - 12;
      if (y + rect.height > winH - 8) y = winH - rect.height - 12;
      tooltip.style.left = x + 'px';
      tooltip.style.top = y + 'px';
    } catch (e) { console.error('showAmbiTooltip error', e); }
  }

  function hideAmbiTooltip() {
    var t = document.getElementById('graphTooltip');
    if (t) t.style.display = 'none';
  }

  // ==================== GRAPH BUILDING ====================
  function buildGraph(rounds) {
    var svg = document.getElementById('nodeGraphSvg');
    if (!svg) return;
    // Hide any floating tooltip before rebuilding
    hideAmbiTooltip();
    svg.innerHTML = '';

    var maxNodes = 0;
    rounds.forEach(function(r) { if (r.nodes.length > maxNodes) maxNodes = r.nodes.length; });

    var svgW = Math.max(NODE_START_X + maxNodes * NODE_SPACING + 40, 500);
    var svgH = rounds.length * ROW_HEIGHT + TOP_PAD + 30;
    svg.setAttribute('width', svgW);
    svg.setAttribute('height', svgH);
    svg.setAttribute('viewBox', '0 0 ' + svgW + ' ' + svgH);
    svg.style.minHeight = svgH + 'px';

    addArrowDef(svg, 'arrow-seq', '#999');
    addArrowDef(svg, 'arrow-attended', '#ca3d3d');

    // 1. Belonging edges
    rounds.forEach(function(r, i) {
      if (r.nodes.length === 0) return;
      var nc = getNodeCenter(i, 0);
      var rc = getRoundCenter(i);
      var from = getRectEdgePoint(nc.x, nc.y, rc.x, rc.y, NODE_WIDTH, NODE_HEIGHT);
      var to = getCircleEdgePoint(rc.x, rc.y, nc.x, nc.y);
      svg.appendChild(createSvg('path', {
        d: 'M' + from.x + ',' + from.y + ' L' + to.x + ',' + to.y,
        class: 'graph-edge graph-edge-belong'
      }));
    });

    // 2. Sequential edges
    rounds.forEach(function(r, i) {
      for (var j = 0; j < r.nodes.length - 1; j++) {
        var fromN = getNodeCenter(i, j);
        var toN = getNodeCenter(i, j + 1);
        var from = getRectEdgePoint(fromN.x, fromN.y, toN.x, toN.y, NODE_WIDTH, NODE_HEIGHT);
        var to = getRectEdgePoint(toN.x, toN.y, fromN.x, fromN.y, NODE_WIDTH, NODE_HEIGHT);
        svg.appendChild(createSvg('path', {
          d: 'M' + from.x + ',' + from.y + ' L' + to.x + ',' + to.y,
          class: 'graph-edge graph-edge-sequential',
          'marker-end': 'url(#arrow-seq)'
        }));
      }
    });

    // 3. Attended edges (orthogonal elbow, bottom-edge entry)
    rounds.forEach(function(r, i) {
      var attendedIds = r.attended;
      if ((!attendedIds || attendedIds.length === 0) && i > 0) {
        var prevFinal = findFinalAnswerNode(rounds, i - 1);
        if (prevFinal) attendedIds = [prevFinal.data.id];
      }
      if (!attendedIds || attendedIds.length === 0) return;

      var rc = getRoundCenter(i);
      attendedIds.forEach(function(aid) {
        var target = findNodeById(rounds, aid);
        if (!target) return;
        // If the attended target is a detail-record node and it is not fixed (unanswered), skip
        if (target.data && target.data.is_detail && !target.data.is_fixed) return;
        var tn = getNodeCenter(target.roundIdx, target.nodeIdx);

        if (target.roundIdx !== i) {
          // Elbow entering target from BOTTOM edge
          var exitX = ROUND_CX + ROUND_R;
          var sourceCY = rc.y;
          var targetBottomY = target.roundIdx * ROW_HEIGHT + TOP_PAD
                              + (ROW_HEIGHT - NODE_HEIGHT) / 2 + NODE_HEIGHT;
          var laneY = (target.roundIdx + 1) * ROW_HEIGHT + TOP_PAD;
          var targetCenterX = NODE_START_X + target.nodeIdx * NODE_SPACING + NODE_WIDTH / 2;
          var elbowOffset = 28;
          var midX = exitX + elbowOffset;
          var d = 'M' + exitX + ',' + sourceCY +
                  ' L' + midX + ',' + sourceCY +
                  ' L' + midX + ',' + laneY +
                  ' L' + targetCenterX + ',' + laneY +
                  ' L' + targetCenterX + ',' + targetBottomY;
          svg.appendChild(createSvg('path', {
            d: d, class: 'graph-edge graph-edge-attended',
            'marker-end': 'url(#arrow-attended)', fill: 'none'
          }));
        } else {
          var from = getCircleEdgePoint(rc.x, rc.y, tn.x, tn.y);
          var to = getRectEdgePoint(tn.x, tn.y, rc.x, rc.y, NODE_WIDTH, NODE_HEIGHT);
          svg.appendChild(createSvg('path', {
            d: 'M' + from.x + ',' + from.y + ' L' + to.x + ',' + to.y,
            class: 'graph-edge graph-edge-attended',
            'marker-end': 'url(#arrow-attended)'
          }));
        }
      });
    });

    // 4b. Parent-link edges (for nodes with data-parents)
    rounds.forEach(function(r, i) {
      r.nodes.forEach(function(n, j) {
        if (!n.parents || n.parents.length === 0) return;
        var fromN = getNodeCenter(i, j);
        n.parents.forEach(function(parentId) {
          var parentNode = findNodeById(rounds, parentId);
          if (!parentNode) return;
          var toN = getNodeCenter(parentNode.roundIdx, parentNode.nodeIdx);
          var from = getRectEdgePoint(fromN.x, fromN.y, toN.x, toN.y, NODE_WIDTH, NODE_HEIGHT);
          var to = getRectEdgePoint(toN.x, toN.y, fromN.x, fromN.y, NODE_WIDTH, NODE_HEIGHT);
          svg.appendChild(createSvg('path', {
            d: 'M' + from.x + ',' + from.y + ' L' + to.x + ',' + to.y,
            class: 'graph-edge graph-edge-parent-link',
            stroke: '#9575cd', 'stroke-dasharray': '5,3', 'stroke-width': 1.2
          }));
        });
      });
    });

    // 4. Round circles
    rounds.forEach(function(r, i) {
      var rc = getRoundCenter(i);
      var g = createSvg('g', { class: 'graph-round-node', 'data-round-id': r.id });
      g.appendChild(createSvg('circle', {
        cx: rc.x, cy: rc.y, r: ROUND_R,
        fill: r.isCurrent ? '#dceaff' : '#e8f1ff',
        stroke: '#4271d6', 'stroke-width': 2
      }));
      var label = r.label.length > 10 ? r.label.slice(0, 9) + '...' : r.label;
      var text = createSvg('text', { x: rc.x, y: rc.y + 1 });
      text.textContent = label;
      g.appendChild(text);
      var title = createSvg('title', {});
      title.textContent = r.label + ' (' + r.id + ') - Click to navigate';
      g.appendChild(title);
      svg.appendChild(g);
    });

    // 5. Step nodes (rectangles)
    rounds.forEach(function(r, i) {
      r.nodes.forEach(function(n, j) {
        if (n.is_detail) return; // Skip detail nodes, render in step 6
        var nc = getNodeCenter(i, j);
        var colors = COLOR_MAP[n.cls] || COLOR_MAP['normal'];
        var g = createSvg('g', { class: 'graph-step-node', 'data-node-id': n.id, 'data-round-id': r.id });
        var x = nc.x - NODE_WIDTH / 2, y = nc.y - NODE_HEIGHT / 2;
        g.appendChild(createSvg('rect', {
          x: x, y: y, width: NODE_WIDTH, height: NODE_HEIGHT,
          fill: colors.fill, stroke: colors.stroke, 'stroke-width': 1.5
        }));
        var displayText = n.title.length > 16 ? n.title.slice(0, 14) + '...' : n.title;
        var text = createSvg('text', { x: nc.x, y: nc.y + 1, fill: colors.text });
        text.textContent = displayText;
        g.appendChild(text);
        var tipEl = createSvg('title', {});
        tipEl.textContent = n.title + ' (' + n.id + ')\\nClick to navigate & highlight';
        g.appendChild(tipEl);

        // Attach hover tooltip for ambi-eval nodes
        if (n.cls === 'ambi-eval') {
          (function(nodeId){
            g.addEventListener('mouseenter', function(evt){ showAmbiTooltip(evt, nodeId); });
            g.addEventListener('mousemove', function(evt){ showAmbiTooltip(evt, nodeId); });
            g.addEventListener('mouseleave', function(){ hideAmbiTooltip(); });
          })(n.id);
        }
        svg.appendChild(g);
      });
    });

    // 6. Detail-record nodes and edges
    rounds.forEach(function(r, i) {
      var detailNodeCount = {};
      r.nodes.forEach(function(n, j) {
        if (!n.is_detail) return;
        var parentId = n.parent_node_id;
        if (!detailNodeCount[parentId]) detailNodeCount[parentId] = 0;
        detailNodeCount[parentId]++;
        
        // Find parent node index for positioning
        var parentNodeIdx = -1;
        for (var pj = 0; pj < r.nodes.length; pj++) {
          if (!r.nodes[pj].is_detail && r.nodes[pj].id === parentId) {
            parentNodeIdx = pj;
            break;
          }
        }
        if (parentNodeIdx < 0) return;
        
        var parentCenter = getNodeCenter(i, parentNodeIdx);
        var detailOffsetX = 100;
        var detailOffsetY = 60 + (detailNodeCount[parentId] - 1) * 50;
        var detailCenterX = parentCenter.x + detailOffsetX;
        var detailCenterY = parentCenter.y + detailOffsetY;
        
        // Draw parent-to-detail edge (soft curved line)
        var from = getRectEdgePoint(parentCenter.x, parentCenter.y, detailCenterX, detailCenterY, NODE_WIDTH, NODE_HEIGHT);
        var to = { x: detailCenterX - 70, y: detailCenterY - 22 };
        svg.appendChild(createSvg('path', {
          d: 'M' + from.x + ',' + from.y + ' Q' + (from.x + detailOffsetX / 2) + ',' + (from.y + detailOffsetY / 2) + ' ' + to.x + ',' + to.y,
          class: 'graph-edge graph-edge-detail-parent',
          stroke: '#a1887f', 'stroke-width': 1.2, fill: 'none'
        }));
        
        // Render detail node rectangle (use foreignObject to allow wrapping)
        var colors = COLOR_MAP[n.cls] || COLOR_MAP['ambi-detail-skipped'];
        var g = createSvg('g', { class: 'graph-detail-node', 'data-node-id': n.id });
        var x = detailCenterX - 70, y = detailCenterY - 22;
        g.appendChild(createSvg('rect', {
          x: x, y: y, width: 140, height: 44,
          fill: colors.fill, stroke: colors.stroke, 'stroke-width': 1.5, rx: 4
        }));
        var fo = createSvg('foreignObject', { x: x, y: y, width: 140, height: 44 });
        var div = document.createElement('div');
        div.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml');
        div.style.cssText = 'font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:11px; color:' + (colors.text || '#1f2838') + '; display:flex; align-items:center; justify-content:center; text-align:center; padding:4px; word-wrap:break-word; overflow:hidden; line-height:1.1;';
        div.textContent = n.title;
        fo.appendChild(div);
        g.appendChild(fo);
        var tipEl = createSvg('title', {});
        tipEl.textContent = n.title + ' (Detail: ' + n.detail_id + ')';
        g.appendChild(tipEl);
        svg.appendChild(g);
      });
    });
  }

  // ==================== NAVIGATION ====================
  function navigateToNode(nodeId) {
    var nodeEl = document.querySelector('.chain-node[data-node-id="' + nodeId + '"]');
    if (!nodeEl) return;
    var roundEl = nodeEl.closest('.chain-round');
    if (roundEl && !roundEl.open) { roundEl.open = true; }
    nodeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    nodeEl.classList.remove('node-blink');
    void nodeEl.offsetWidth;
    nodeEl.classList.add('node-blink');
  }

  function navigateToRound(roundId) {
    var allRounds = document.querySelectorAll('.chain-round');
    var target = null;
    allRounds.forEach(function(r) {
      var idEl = r.querySelector('.chain-round-id');
      if (idEl && idEl.textContent.trim() === roundId) target = r;
    });
    if (!target) return;
    if (!target.open) target.open = true;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    var summary = target.querySelector('.chain-round-summary');
    if (summary) {
      summary.classList.remove('node-blink');
      void summary.offsetWidth;
      summary.classList.add('node-blink');
    }
  }

  // ==================== TOGGLE GRAPH ====================
  function toggleGraph() {
    var section = document.getElementById('nodeGraphSection');
    var btn = document.getElementById('graphToggleBtn');
    if (!section || !btn) return;

    if (section.style.display === 'none') {
      section.style.display = 'block';
      btn.classList.add('active');
      var label = btn.querySelector('.graph-toggle-label');
      if (label) label.textContent = 'Hide Node Graph';
      window.__graphVisible = true;
      window.__roundsData = extractRoundData();
      if (window.__roundsData) { buildGraph(window.__roundsData); window.__graphBuilt = true; }
    } else {
      section.style.display = 'none';
      btn.classList.remove('active');
      var label = btn.querySelector('.graph-toggle-label');
      if (label) label.textContent = 'Show Node Graph';
      window.__graphVisible = false;
    }
  }

  // ==================== MUTATION OBSERVER ====================
  function setupMutationObserver() {
    var root = document.querySelector('.chain-navigate-root');
    if (!root) return;
    var parent = root.parentElement;
    if (!parent) return;

    var observer = new MutationObserver(function() {
      requestAnimationFrame(function() {
        window.__roundsData = extractRoundData();
        window.__graphBuilt = false;
        if (window.__graphVisible) {
          var section = document.getElementById('nodeGraphSection');
          if (section) {
            section.style.display = 'block';
            buildGraph(window.__roundsData);
            window.__graphBuilt = true;
          }
        }
      });
    });
    observer.observe(parent, { childList: true });
  }

  // ==================== INIT ====================
  function init() {
    window.__roundsData = extractRoundData();
    window.__graphBuilt = false;
    window.__graphVisible = false;
    setupMutationObserver();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
"""


def _render_attended_links(ids: list) -> str:
    if not ids:
        return "Attended nodes when entered: <span class='attended-empty'>(none)</span>"
    parts = ", ".join(
        f"<a class='attended-link' href='javascript:void(0)' "
        f"data-attended-id='{html.escape(str(nid), quote=True)}'>"
        f"{html.escape(str(nid))}</a>"
        for nid in ids
    )
    return f"Attended nodes when entered: {parts}"


def render_round_html(round_group: dict[str, Any], mode: str = "tech") -> str:
    nodes = round_group.get("nodes") or []
    selected_ids = set(round_group.get("selected_ids") or [])
    current_round_cls = "chain-round-current" if round_group.get("is_current_round") else "chain-round-past"
    open_attr = " open" if round_group.get("is_open") else ""

    node_html = "".join(
        node.render_html(mode=mode, is_selected=node.node_id in selected_ids)
        for node in nodes
        if isinstance(node, NodeRecord)
    )

    round_label = str(round_group.get("round_label") or "Round")
    round_id = str(round_group.get("round_id") or "")
    selected_ids_text = str(round_group.get("selected_ids_text") or "(none)")
    attended_when_enter = round_group.get("attended_when_enter", [])
    current_badge = "<span class='chain-round-pill'>Current</span>" if round_group.get("is_current_round") else ""

    return (
        f"<details class='chain-round {current_round_cls}'{open_attr}>"
        "<summary class='chain-round-summary'>"
        "<div class='chain-round-summary-left'>"
        "<div class='chain-round-summary-top'>"
        f"<span class='chain-round-label'>{round_label}</span>"
        f"<span class='chain-round-id'>{round_id}</span>"
        "</div>"
        f"<div class='chain-round-summary-meta'>{_render_attended_links(attended_when_enter)}</div>"
        "</div>"
        "<div class='chain-round-summary-right'>"
        f"{current_badge}"
        f"<span class='chain-round-count'>{len(nodes)} nodes</span>"
        "</div>"
        "</summary>"
        "<div class='chain-round-body'>"
        f"<div class='chain-round-selected'>Selected nodes: {selected_ids_text}</div>"
        "<div class='chain-round-nodes'>"
        f"{node_html}"
        "</div></div></details>"
    )


GRAPH_TOGGLE_BTN = """\
<div class="graph-toggle-bar">
  <button class="graph-toggle-btn" id="graphToggleBtn" title="Toggle the node relationship graph">
    <span class="graph-toggle-icon">&#9670;</span>
    <span class="graph-toggle-label">Show Node Graph</span>
  </button>
</div>"""

GRAPH_SECTION = """\
<div id="nodeGraphSection" class="node-graph-section" style="display:none;">
  <div class="graph-toolbar">
    <span class="graph-title">Node Relationship Graph</span>
    <span class="graph-hint">Click any node to navigate &amp; highlight it in the chain below</span>
  </div>
  <div class="graph-svg-wrap">
    <svg id="nodeGraphSvg" width="100%" height="400" style="min-height:400px;"></svg>
  </div>
  <div class="graph-legend">
    <span class="legend-item"><span class="legend-swatch legend-round-swatch"></span> Round</span>
    <span class="legend-item"><span class="legend-swatch legend-normal-swatch"></span> Normal</span>
    <span class="legend-item"><span class="legend-swatch legend-issue-swatch"></span> Has Issue</span>
    <span class="legend-item"><span class="legend-swatch legend-sql-swatch"></span> SQL (clean)</span>
    <span class="legend-item"><span class="legend-line-swatch"></span> Sequential</span>
    <span class="legend-item"><span class="legend-line-dashed-swatch"></span> Belongs to</span>
    <span class="legend-item"><span class="legend-line-attended-swatch"></span> Attended</span>
  </div>
</div>"""


def render_allrounds_html(groups: list[dict[str, Any]], mode: str = "tech") -> str:
    if not groups:
        inner = "<div class='chain-round-selected'>(No nodes yet)</div>"
    else:
        rendered = "".join(render_round_html(group, mode=mode) for group in groups)
        inner = f"<div class='chain-root'>{rendered}</div>"

    return (
        '<div class="chain-navigate-root">'
        + GRAPH_TOGGLE_BTN
        + GRAPH_SECTION
        + inner
        + "</div>"
    )


def to_render_nodes(nodes: list[NodeRecord], selected_ids: list[str], mode: str = "tech") -> list[dict[str, Any]]:
    selected_set = set(selected_ids or [])
    return [node.get_payload(mode=mode, is_selected=node.node_id in selected_set) for node in nodes]


def toggle_selection(selected_node_id: str, ordered_node_ids: list[str], selected_ids: list[str]):
    selected_set = set(selected_ids or [])
    if selected_node_id:
        if selected_node_id in selected_set:
            selected_set.remove(selected_node_id)
        else:
            selected_set.add(selected_node_id)
    ordered_selected = [node_id for node_id in ordered_node_ids if node_id in selected_set]
    return ordered_selected


def selected_ids_to_json(selected_ids: list[str]) -> str:
    return json.dumps(selected_ids or [], ensure_ascii=False, indent=2)
