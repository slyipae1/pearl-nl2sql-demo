from __future__ import annotations


INTRO_HTML = """
<div class="intro-section" style="max-width:75%;margin:0 auto;font-family:system-ui,-apple-system,sans-serif;color:#24324a">
<style>
  .intro-section a{color:#4a7ab5;text-decoration:none}
  .intro-section a:hover{text-decoration:underline}
  .intro-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
  .intro-head svg{flex-shrink:0}
  .intro-head span{font-size:20px;font-weight:700;color:#1e2e4a}
  .intro-desc{font-size:14px;line-height:1.6;color:#3f567c;margin:0 0 20px 0}
  .intro-subtitle{font-size:15px;font-weight:700;color:#1e2e4a;margin:22px 0 12px 0;display:inline-block;background:#eef4ff;padding:3px 14px;border-radius:14px}
  .intro-features{list-style:none;padding:0;margin:0 0 6px 0;display:grid;grid-template-columns:1fr 1fr;gap:8px 24px}
  .intro-features li{display:flex;align-items:flex-start;gap:8px;font-size:13px;line-height:1.5;color:#3f567c;padding:4px 0}
  .intro-features svg{flex-shrink:0;margin-top:2px}
  .intro-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin:8px 0 6px 0}
  .intro-card{background:#ffffff;border:1px solid #d5dce8;border-radius:10px;padding:14px 14px 12px 14px;border-left:3px solid #4a7ab5;transition:box-shadow 0.15s}
  .intro-card:hover{box-shadow:0 2px 10px rgba(0,0,0,0.06)}
  .intro-card-icon{display:flex;align-items:center;gap:8px;margin-bottom:4px}
  .intro-card-icon svg{color:#4a7ab5}
  .intro-card-title{font-size:13px;font-weight:700;color:#1e2e4a}
  .intro-card-text{font-size:12px;line-height:1.5;color:#4f6588;margin-top:3px}
  .intro-steps{list-style:none;counter-reset:step;padding:0;margin:0 0 16px 0;display:grid;grid-template-columns:1fr 1fr;gap:6px 30px}
  .intro-steps li{counter-increment:step;display:flex;align-items:flex-start;gap:8px;font-size:13px;line-height:1.5;color:#3f567c;padding:3px 0}
  .intro-steps li::before{content:counter(step);display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#eef4ff;color:#2f4f8f;font-size:11px;font-weight:700;flex-shrink:0;margin-top:1px}
  .intro-footnote{font-size:13px;color:#4f6588;margin:10px 0 18px 0;padding:8px 16px;background:#f6f9ff;border-radius:8px;border:1px solid #d5dce8}
  @media(max-width:900px){.intro-grid{grid-template-columns:1fr 1fr}.intro-features{grid-template-columns:1fr}.intro-steps{grid-template-columns:1fr}}
</style>

<div class="intro-head">
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="10" stroke="#2f4f8f" stroke-width="1.8"/>
    <path d="M12 9v1m0 3v3" stroke="#2f4f8f" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="12" cy="6.5" r="0.8" fill="#2f4f8f"/>
  </svg>
  <span>Introduction</span>
</div>

<p class="intro-desc">
  This app demonstrates an agentic NL2SQL workflow with explicit session-state tracking across rounds.
  Six core components cooperate to interpret natural-language questions, execute SQL over a selected database,
  detect and resolve ambiguity, compact conversation memory, and render traceable node histories.
</p>

<div class="intro-subtitle">What You Can Do</div>
<ul class="intro-features">
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <circle cx="9" cy="9" r="7" stroke="#4a7ab5" stroke-width="1.4"/>
      <path d="M6.5 7a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5" stroke="#4a7ab5" stroke-width="1.4" stroke-linecap="round"/>
      <circle cx="9" cy="13.2" r="0.8" fill="#4a7ab5"/>
    </svg>
    Ask a natural-language question over a selected SQLite database.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M1 9s2.5-6 8-6 8 6 8 6-2.5 6-8 6-8-6-8-6z" stroke="#4a7ab5" stroke-width="1.3"/>
      <circle cx="9" cy="9" r="2.5" stroke="#4a7ab5" stroke-width="1.3"/>
    </svg>
    Watch how agent steps are tracked as round-based nodes with detailed traces.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M3 9l4 4 8-8" stroke="#4a7ab5" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    Select one or more node IDs to mark them as attended context for follow-up rounds.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="1.5" y="3" width="6" height="12" rx="1" stroke="#4a7ab5" stroke-width="1.3"/>
      <rect x="10.5" y="3" width="6" height="12" rx="1" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M4.5 3v12M13.5 3v12" stroke="#4a7ab5" stroke-width="1"/>
    </svg>
    Compare tech and non-tech views of the same conversation state.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <ellipse cx="9" cy="4" rx="7" ry="2.5" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M2 4v10c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V4" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M2 9c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" stroke="#4a7ab5" stroke-width="1.3"/>
    </svg>
    Inspect schema, table stats, sampled rows, and execute ad-hoc SQL in DB Inspector.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="3" y="8" width="5" height="7" rx="1" stroke="#4a7ab5" stroke-width="1.3"/>
      <rect x="10" y="4" width="5" height="7" rx="1" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M9 7L7.5 5h3z" fill="#4a7ab5"/>
    </svg>
    Compact conversation memory and extract ambiguity preferences via the Compactor.
  </li>
</ul>

<div class="intro-subtitle">Core Components</div>
<div class="intro-grid">
  <div class="intro-card">
    <div class="intro-card-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="3" stroke="#2f4f8f" stroke-width="1.5"/>
        <path d="M10 2v2m0 12v2M2 10h2m12 0h2M4.3 4.3l1.4 1.4m8.6 8.6l1.4 1.4M4.3 15.7l1.4-1.4m8.6-8.6l1.4-1.4" stroke="#2f4f8f" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span class="intro-card-title">Manager</span>
    </div>
    <div class="intro-card-text">Rewrites and enriches prompts. Detects topic switches. Checks stored ambiguity preferences. Sets attended node IDs. Summarizes each round.</div>
  </div>
  <div class="intro-card">
    <div class="intro-card-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M4 5l5 5-5 5M10 15h7" stroke="#2f4f8f" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="intro-card-title">NL2SQL Worker</span>
    </div>
    <div class="intro-card-text">Runs the tool-calling agent loop. Inspects database schema. Executes SQL queries. Returns the final answer.</div>
  </div>
  <div class="intro-card">
    <div class="intro-card-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M10 16V4m0 0l3 3m-3-3L7 7m3 9l3-3m-3 3l-3-3" stroke="#2f4f8f" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="intro-card-title">Compactor</span>
    </div>
    <div class="intro-card-text">Extracts user ambiguity preferences into a dynamically updated graph. Summarizes conversation history. Compacts old nodes. Resets agent memory with compressed context.</div>
  </div>
  <div class="intro-card">
    <div class="intro-card-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="8" cy="8" r="5" stroke="#2f4f8f" stroke-width="1.5"/>
        <path d="M11.5 11.5l5 5" stroke="#2f4f8f" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
      <span class="intro-card-title">Issue Detector</span>
    </div>
    <div class="intro-card-text">Parses SQL for columns, literals, and functions. Retrieves confusing DB options via LSH indices. Detects ambiguity and generates alternative SQL.</div>
  </div>
  <div class="intro-card">
    <div class="intro-card-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M2 5l8-4 8 4-8 4-8-4z" stroke="#2f4f8f" stroke-width="1.4"/>
        <path d="M2 10l8 4 8-4" stroke="#2f4f8f" stroke-width="1.4" stroke-linejoin="round"/>
        <path d="M2 15l8 4 8-4" stroke="#2f4f8f" stroke-width="1.4" stroke-linejoin="round"/>
      </svg>
      <span class="intro-card-title">SystemState</span>
    </div>
    <div class="intro-card-text">Shared source of truth for rounds, nodes, selected IDs, attended IDs, pending statuses, and round snapshots.</div>
  </div>
  <div class="intro-card">
    <div class="intro-card-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <rect x="2" y="3" width="16" height="13" rx="2" stroke="#2f4f8f" stroke-width="1.5"/>
        <path d="M2 6.5h16" stroke="#2f4f8f" stroke-width="1.5"/>
        <circle cx="4.5" cy="4.5" r="0.5" fill="#2f4f8f"/>
        <circle cx="6.5" cy="4.5" r="0.5" fill="#2f4f8f"/>
      </svg>
      <span class="intro-card-title">UI (Gradio)</span>
    </div>
    <div class="intro-card-text">Conversation panel, node chain display, DB Inspector tab. Tech and non-tech rendering modes. Compact trigger button and preference confirmation.</div>
  </div>
</div>

<div class="intro-subtitle">How To Use</div>
<ol class="intro-steps">
  <li>Select a database from the top dropdown.</li>
  <li>Choose tech or non-tech mode.</li>
  <li>Open the Conversation tab and ask a question.</li>
  <li>Review the node chain: reasoning steps, SQL traces, and issue highlights.</li>
  <li>Click nodes to mark them as attended context for follow-up rounds.</li>
  <li>Ask a follow-up question &mdash; selected IDs are carried forward as attended IDs.</li>
  <li>Compact to compress history and extract ambiguity preference.</li>
</ol>

<p class="intro-footnote">The architecture figure below shows runtime dataflow and concurrency points.</p>
</div>
""".strip()


INTRO_ARCHITECTURE_HTML = """
<div class='intro-arch-root'>
  <style>
    .intro-arch-root {
      border: 1px solid #d5dce8;
      border-radius: 12px;
      background: #fbfcfe;
      padding: 12px;
      margin-top: 8px;
      overflow-x: auto;
    }
    .intro-arch-title {
      font-size: 14px;
      font-weight: 700;
      color: #24324a;
      margin-bottom: 8px;
    }
    .intro-arch-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 10px;
      font-size: 12px;
      color: #4a5a76;
    }
    .intro-arch-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .intro-arch-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      border: 1px solid rgba(0, 0, 0, 0.15);
      display: inline-block;
    }
    .intro-note {
      margin-top: 8px;
      font-size: 12px;
      color: #5a6882;
    }
  </style>

  <div class='intro-arch-title'>Architecture and Conversation Lifecycle</div>

  <svg viewBox='0 0 1120 580' width='100%' height='auto' role='img' aria-label='Agent architecture'>
    <defs>
      <marker id='arrowMain' markerWidth='8' markerHeight='8' refX='7' refY='4' orient='auto'>
        <path d='M0,0 L8,4 L0,8 z' fill='#2f4f8f'></path>
      </marker>
      <marker id='arrowSide' markerWidth='8' markerHeight='8' refX='7' refY='4' orient='auto'>
        <path d='M0,0 L8,4 L0,8 z' fill='#6a7a95'></path>
      </marker>
      <marker id='arrowExt' markerWidth='8' markerHeight='8' refX='7' refY='4' orient='auto'>
        <path d='M0,0 L8,4 L0,8 z' fill='#c58e49'></path>
      </marker>
    </defs>

    <rect x='20' y='20' width='1080' height='540' rx='16' fill='#f6f9ff' stroke='#d5dce8' />

    <!-- Row 1: Main Flow -->
    <rect x='60' y='75' width='150' height='65' rx='12' fill='#ffffff' stroke='#8096bc' />
    <text x='135' y='104' text-anchor='middle' font-size='14' fill='#23324a' font-weight='700'>User</text>
    <text x='135' y='122' text-anchor='middle' font-size='10' fill='#4f5f7a'>ask questions; select nodes</text>

    <rect x='255' y='60' width='235' height='90' rx='12' fill='#eef4ff' stroke='#5f7fb9' />
    <text x='372' y='92' text-anchor='middle' font-size='14' fill='#20365e' font-weight='700'>Manager</text>
    <text x='372' y='110' text-anchor='middle' font-size='10' fill='#3f547a'>rewrite prompts; detect topic switch</text>
    <text x='372' y='126' text-anchor='middle' font-size='10' fill='#3f547a'>check preferences; set attended IDs</text>
    <text x='372' y='142' text-anchor='middle' font-size='10' fill='#3f547a'>summarize round</text>

    <rect x='530' y='60' width='240' height='90' rx='12' fill='#ecfff7' stroke='#4a9a78' />
    <text x='650' y='92' text-anchor='middle' font-size='14' fill='#1d4c3a' font-weight='700'>NL2SQL Worker</text>
    <text x='650' y='110' text-anchor='middle' font-size='10' fill='#2c6450'>tool-calling loop</text>
    <text x='650' y='126' text-anchor='middle' font-size='10' fill='#2c6450'>inspect schema; execute SQL</text>
    <text x='650' y='142' text-anchor='middle' font-size='10' fill='#2c6450'>return answer</text>

    <rect x='810' y='55' width='240' height='100' rx='12' fill='#fff7ec' stroke='#c58e49' />
    <text x='930' y='87' text-anchor='middle' font-size='14' fill='#654620' font-weight='700'>Database + Tools</text>
    <text x='930' y='107' text-anchor='middle' font-size='10' fill='#7d6037'>SQLite schema; SQL execution</text>
    <text x='930' y='124' text-anchor='middle' font-size='10' fill='#7d6037'>result tables</text>

    <!-- Row 2: Analysis, Compaction, State -->
    <rect x='60' y='215' width='285' height='95' rx='12' fill='#fff1f1' stroke='#c56a6a' />
    <text x='202' y='246' text-anchor='middle' font-size='14' fill='#6d2c2c' font-weight='700'>Issue Detector</text>
    <text x='202' y='265' text-anchor='middle' font-size='10' fill='#8a4343'>parse SQL; retrieve confusing options</text>
    <text x='202' y='281' text-anchor='middle' font-size='10' fill='#8a4343'>detect ambiguity; generate alternatives</text>

    <rect x='380' y='215' width='260' height='95' rx='12' fill='#f5f0ff' stroke='#9a7acc' />
    <text x='510' y='246' text-anchor='middle' font-size='14' fill='#4a2d7a' font-weight='700'>Compactor</text>
    <text x='510' y='265' text-anchor='middle' font-size='10' fill='#5d3d8a'>extract ambiguity preferences</text>
    <text x='510' y='281' text-anchor='middle' font-size='10' fill='#5d3d8a'>summarize conversation; compact nodes</text>
    <text x='510' y='297' text-anchor='middle' font-size='10' fill='#5d3d8a'>reset agent memory</text>

    <rect x='730' y='215' width='310' height='95' rx='12' fill='#ffffff' stroke='#7392bf' />
    <text x='885' y='246' text-anchor='middle' font-size='14' fill='#243b60' font-weight='700'>SystemState</text>
    <text x='885' y='265' text-anchor='middle' font-size='10' fill='#3f567c'>rounds, nodes, selected IDs</text>
    <text x='885' y='281' text-anchor='middle' font-size='10' fill='#3f567c'>per-round attended IDs</text>
    <text x='885' y='297' text-anchor='middle' font-size='10' fill='#3f567c'>pending summary tracker</text>

    <!-- Row 3: UI -->
    <rect x='60' y='365' width='980' height='110' rx='12' fill='#ffffff' stroke='#7392bf' />
    <text x='550' y='398' text-anchor='middle' font-size='14' fill='#243b60' font-weight='700'>UI (Gradio)</text>
    <text x='550' y='418' text-anchor='middle' font-size='11' fill='#3f567c'>conversation panel, node chain, DB inspector</text>
    <text x='550' y='436' text-anchor='middle' font-size='11' fill='#3f567c'>tech and non-tech rendering modes</text>
    <text x='550' y='454' text-anchor='middle' font-size='11' fill='#3f567c'>compact button and preference confirmation dialog</text>
    <text x='550' y='472' text-anchor='middle' font-size='11' fill='#3f567c'>selected IDs carried to next round as attended IDs</text>

    <!-- Main cycle arrows (solid blue) -->
    <line x1='210' y1='107' x2='255' y2='107' stroke='#2f4f8f' stroke-width='2' marker-end='url(#arrowMain)' />
    <text x='232' y='101' text-anchor='middle' font-size='10' fill='#2f4f8f'>ask question</text>

    <line x1='490' y1='105' x2='530' y2='105' stroke='#2f4f8f' stroke-width='2' marker-end='url(#arrowMain)' />
    <text x='510' y='99' text-anchor='middle' font-size='10' fill='#2f4f8f'>enhanced prompt</text>

    <path d='M650 150 L650 190 L202 190 L202 215' fill='none' stroke='#2f4f8f' stroke-width='2' marker-end='url(#arrowMain)' />
    <text x='426' y='184' text-anchor='middle' font-size='10' fill='#2f4f8f'>step callback</text>

    <line x1='345' y1='262' x2='730' y2='262' stroke='#2f4f8f' stroke-width='2' marker-end='url(#arrowMain)' />
    <text x='537' y='256' text-anchor='middle' font-size='10' fill='#2f4f8f'>return issues</text>

    <line x1='940' y1='310' x2='940' y2='365' stroke='#2f4f8f' stroke-width='2' marker-end='url(#arrowMain)' />
    <text x='950' y='341' text-anchor='middle' font-size='10' fill='#2f4f8f'>render state</text>

    <!-- Sub-cycle arrows (dashed gray) -->
    <path d='M255 85 Q232 68 210 85' fill='none' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='232' y='64' text-anchor='middle' font-size='9' fill='#4f5f7a'>check preference / detect topic</text>

    <path d='M135 140 L135 175 L380 175 L380 215' fill='none' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='257' y='169' text-anchor='middle' font-size='9' fill='#4f5f7a'>trigger compact</text>

    <path d='M372 150 L372 200 L730 200 L730 215' fill='none' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='551' y='194' text-anchor='middle' font-size='9' fill='#4f5f7a'>set attended IDs</text>

    <path d='M800 215 L800 195 L490 195 L490 150' fill='none' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='645' y='189' text-anchor='middle' font-size='9' fill='#4f5f7a'>attended IDs (next round)</text>

    <path d='M135 140 L135 170 L360 170 L360 365' fill='none' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='247' y='164' text-anchor='middle' font-size='9' fill='#4f5f7a'>select nodes</text>

    <line x1='810' y1='365' x2='810' y2='310' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='820' y='341' text-anchor='middle' font-size='9' fill='#4f5f7a'>selected IDs</text>

    <line x1='640' y1='262' x2='730' y2='262' stroke='#6a7a95' stroke-width='2' stroke-dasharray='5 4' marker-end='url(#arrowSide)' />
    <text x='685' y='256' text-anchor='middle' font-size='9' fill='#4f5f7a'>summary</text>

    <!-- External interaction arrows (amber) -->
    <line x1='770' y1='85' x2='810' y2='85' stroke='#c58e49' stroke-width='2' marker-end='url(#arrowExt)' />
    <text x='790' y='79' text-anchor='middle' font-size='9' fill='#7d6037'>exec SQL</text>

    <line x1='810' y1='115' x2='770' y2='115' stroke='#c58e49' stroke-width='2' marker-end='url(#arrowExt)' />
    <text x='790' y='121' text-anchor='middle' font-size='9' fill='#7d6037'>schema</text>

    <path d='M202 310 L202 345 L930 345 L930 155' fill='none' stroke='#c58e49' stroke-width='2' marker-end='url(#arrowExt)' />
    <text x='566' y='339' text-anchor='middle' font-size='9' fill='#7d6037'>retrieve confusing options</text>

    <!-- Compactor to Ambiguity Preference Graph -->
    <line x1='510' y1='310' x2='510' y2='335' stroke='#c58e49' stroke-width='2' marker-end='url(#arrowExt)' />
    <text x='520' y='329' text-anchor='start' font-size='9' fill='#7d6037'>user preference</text>
    <rect x='450' y='340' width='120' height='18' rx='4' fill='#fdf6ec' stroke='#d5dce8' />
    <text x='510' y='353' text-anchor='middle' font-size='9' fill='#7d6037'>Ambiguity Pref Graph</text>

    <text x='40' y='540' font-size='12' fill='#3f567c' font-weight='700'>Round lifecycle: user asks &rarr; manager enriches &rarr; worker executes &rarr; detector analyses &rarr; compactor compacts &rarr; manager summarizes &rarr; user selects nodes &rarr; next round focuses on attended IDs &rarr; ...</text>
  </svg>

  <div class='intro-arch-legend'>
    <span class='intro-arch-pill'><span class='intro-arch-dot' style='background:#eef4ff'></span>Manager + prompt enrichment</span>
    <span class='intro-arch-pill'><span class='intro-arch-dot' style='background:#ecfff7'></span>NL2SQL execution</span>
    <span class='intro-arch-pill'><span class='intro-arch-dot' style='background:#fff1f1'></span>Issue analysis</span>
    <span class='intro-arch-pill'><span class='intro-arch-dot' style='background:#f5f0ff'></span>Memory compaction</span>
    <span class='intro-arch-pill'><span class='intro-arch-dot' style='background:#ffffff'></span>Shared state and UI</span>
  </div>

  <div class='intro-note'>
    Solid blue arrows: main cycle. Dashed gray arrows: sub-cycles and interactions. Amber arrows: external resource interactions. The History Node Maintainer runs as an internal thread spawned per action step (not shown as a separate box).
  </div>
</div>
""".strip()

from pathlib import Path
import base64

def _load_architecture_svg_html() -> str:
    svg_path = Path(__file__).with_name("systemOverview.svg")
    if not svg_path.exists():
        return "<p>Architecture SVG not found: ui/systemOverview.svg</p>"

    svg_raw = svg_path.read_text(encoding="utf-8")
    svg_b64 = base64.b64encode(svg_raw.encode("utf-8")).decode("ascii")

    return f"""
    <div class='intro-arch-root'>
      <style>
        .intro-arch-root {{
          border: 1px solid #d5dce8;
          border-radius: 12px;
          background: #fbfcfe;
          padding: 12px;
          margin-top: 8px;
          overflow-x: auto;
        }}
        .intro-arch-title {{
          font-size: 18px;
          font-weight: 700;
          color: #24324a;
          margin-bottom: 8px;
        }}
        .intro-arch-img {{
          width: 100%;
          height: auto;
          display: block;
        }}
      </style>

      <div class='intro-arch-title'>Architecture and Conversation Lifecycle</div>
      <img class='intro-arch-img' src='data:image/svg+xml;base64,{svg_b64}' alt='Architecture Diagram' />
    </div>
    """.strip()

INTRO_ARCHITECTURE_HTML = _load_architecture_svg_html()


# -----------------------------------------------------------------------------
# Current intro content override
# Keep this block last so the app uses the latest wording and diagram.
# -----------------------------------------------------------------------------

INTRO_HTML = """
<div class="intro-section" style="max-width:78%;margin:0 auto;font-family:system-ui,-apple-system,sans-serif;color:#24324a">
<style>
  .intro-section a{color:#4a7ab5;text-decoration:none}
  .intro-section a:hover{text-decoration:underline}
  .intro-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
  .intro-head svg{flex-shrink:0}
  .intro-head span{font-size:20px;font-weight:700;color:#1e2e4a}
  .intro-desc{font-size:14px;line-height:1.65;color:#3f567c;margin:0 0 18px 0}
  .intro-subtitle{font-size:15px;font-weight:700;color:#1e2e4a;margin:22px 0 12px 0;display:inline-block;background:#eef4ff;padding:3px 14px;border-radius:14px}
  .intro-features{list-style:none;padding:0;margin:0 0 6px 0;display:grid;grid-template-columns:1fr 1fr;gap:8px 18px}
  .intro-features li{display:flex;align-items:flex-start;gap:8px;font-size:13px;line-height:1.5;color:#3f567c;padding:4px 0}
  .intro-features svg{flex-shrink:0;margin-top:2px}
  .intro-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:8px 0 6px 0}
  .intro-card{background:#ffffff;border:1px solid #d5dce8;border-radius:10px;padding:14px 14px 12px 14px;border-left:3px solid #4a7ab5;transition:box-shadow 0.15s}
  .intro-card:hover{box-shadow:0 2px 10px rgba(0,0,0,0.06)}
  .intro-card-icon{display:flex;align-items:center;gap:8px;margin-bottom:4px}
  .intro-card-title{font-size:13px;font-weight:700;color:#1e2e4a}
  .intro-card-text{font-size:12px;line-height:1.5;color:#4f6588;margin-top:3px}
  .intro-steps{list-style:none;counter-reset:step;padding:0;margin:0 0 16px 0;display:grid;grid-template-columns:1fr 1fr;gap:6px 24px}
  .intro-steps li{counter-increment:step;display:flex;align-items:flex-start;gap:8px;font-size:13px;line-height:1.5;color:#3f567c;padding:3px 0}
  .intro-steps li::before{content:counter(step);display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#eef4ff;color:#2f4f8f;font-size:11px;font-weight:700;flex-shrink:0;margin-top:1px}
  .intro-footnote{font-size:13px;color:#4f6588;margin:10px 0 18px 0;padding:8px 16px;background:#f6f9ff;border-radius:8px;border:1px solid #d5dce8}
  .intro-callout{font-size:13px;line-height:1.55;color:#4f6588;margin:0 0 12px 0;padding:10px 14px;background:#fbfdff;border:1px solid #dfe6f0;border-radius:10px}
  @media(max-width:980px){.intro-grid{grid-template-columns:1fr 1fr}.intro-features{grid-template-columns:1fr}.intro-steps{grid-template-columns:1fr}}
  @media(max-width:640px){.intro-grid{grid-template-columns:1fr}}
</style>

<div class="intro-head">
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="10" stroke="#2f4f8f" stroke-width="1.8"/>
    <path d="M12 9v1m0 3v3" stroke="#2f4f8f" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="12" cy="6.5" r="0.8" fill="#2f4f8f"/>
  </svg>
  <span>Introduction</span>
</div>

<p class="intro-desc">
  PEARL is an agentic NL2SQL demo for executing natural-language questions over SQLite databases while exposing the full round history.
  The current app uses a manager-led workflow, single-turn SQL generation, execution-grounded ambiguity analysis, explicit clarification questions, preference base updates, and summary-only compaction.
</p>

<div class="intro-callout">
  Current round flow: user question → manager prompt rewrite → SQL generation → candidate exploration → pairwise ambiguity detection → option evaluation → clarification questions / auto-fix → final answer and round summary.
</div>

<div class="intro-subtitle">What You Can Do</div>
<ul class="intro-features">
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="7" stroke="#4a7ab5" stroke-width="1.4"/>
      <path d="M6.5 7a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5" stroke="#4a7ab5" stroke-width="1.4" stroke-linecap="round"/>
      <circle cx="9" cy="13.2" r="0.8" fill="#4a7ab5"/>
    </svg>
    Ask a question over a selected SQLite database and get an answer with execution evidence.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M1 9s2.5-6 8-6 8 6 8 6-2.5 6-8 6-8-6-8-6z" stroke="#4a7ab5" stroke-width="1.3"/>
      <circle cx="9" cy="9" r="2.5" stroke="#4a7ab5" stroke-width="1.3"/>
    </svg>
    Inspect the node chain to review SQL generation, candidate exploration, ambiguity detection, and evaluation.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M3 9l4 4 8-8" stroke="#4a7ab5" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    Select node IDs to carry context into the next round as attended IDs.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M4 3h10v12H4z" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M4 7h10" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M7 5.2h4" stroke="#4a7ab5" stroke-width="1.3" stroke-linecap="round"/>
    </svg>
    Compare tech and non-tech views of the same conversation state.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <ellipse cx="9" cy="4" rx="7" ry="2.5" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M2 4v10c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V4" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M2 9c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" stroke="#4a7ab5" stroke-width="1.3"/>
    </svg>
    Inspect schema, table stats, samples, and run ad-hoc SQL in DB Inspector.
  </li>
  <li>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <rect x="3" y="8" width="5" height="7" rx="1" stroke="#4a7ab5" stroke-width="1.3"/>
      <rect x="10" y="4" width="5" height="7" rx="1" stroke="#4a7ab5" stroke-width="1.3"/>
      <path d="M9 7L7.5 5h3z" fill="#4a7ab5"/>
    </svg>
    Compact older rounds to summarize history and preserve only the compressed context.
  </li>
</ul>

<div class="intro-subtitle">Core Components</div>
<div class="intro-grid">
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">Manager</span></div><div class="intro-card-text">Rewrites the user request, selects the workflow, asks clarification questions, auto-fixes one-hot ambiguity, and summarizes each round.</div></div>
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">NL2SQL Worker</span></div><div class="intro-card-text">Generates one SQL per question with an LLM, then returns the final execution-grounded answer.</div></div>
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">Issue Detector</span></div><div class="intro-card-text">Finds confusing DB elements, generates candidate SQL, compares execution clusters, and extracts ambiguity contexts.</div></div>
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">Evaluator</span></div><div class="intro-card-text">Merges overlapping ambiguity entries, filters invalid ones, and scores options with execution-grounded justification.</div></div>
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">Preference Learner</span></div><div class="intro-card-text">Maintains the ambiguity preference base and reuses prior clarification decisions in later rounds.</div></div>
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">Compactor</span></div><div class="intro-card-text">Summarizes old rounds only and resets manager memory with compressed context.</div></div>
  <div class="intro-card"><div class="intro-card-icon"><span class="intro-card-title">SystemState + UI</span></div><div class="intro-card-text">Keeps rounds, nodes, attended IDs, specification questions, and the node-chain / clarification-panel / DB-inspector layout in sync.</div></div>
</div>

<div class="intro-subtitle">How To Use</div>
<ol class="intro-steps">
  <li>Select a database from the top dropdown.</li>
  <li>Choose tech or non-tech mode.</li>
  <li>Ask a question in the Conversation tab.</li>
  <li>Review SQL generation, candidate clusters, ambiguity entries, and scored options in the node chain.</li>
  <li>Answer clarification questions when they appear; the UI can preselect suggested options.</li>
  <li>Select node IDs to carry context into the next round as attended IDs.</li>
  <li>Use Compact to compress older rounds and reset the manager context.</li>
</ol>

<p class="intro-footnote">The architecture figure below matches the current manager-led workflow, clarification flow, preference base, and round-based node history.</p>
</div>
""".strip()


# def _build_current_architecture_html() -> str:
#     svg = """
# <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1180 720" width="100%" height="auto" role="img" aria-label="PEARL architecture diagram">
#   <defs>
#     <marker id="arrowBlue" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
#       <path d="M0,0 L8,4 L0,8 z" fill="#2f4f8f"/>
#     </marker>
#     <marker id="arrowGray" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
#       <path d="M0,0 L8,4 L0,8 z" fill="#6a7a95"/>
#     </marker>
#     <marker id="arrowAmber" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
#       <path d="M0,0 L8,4 L0,8 z" fill="#c58e49"/>
#     </marker>
#     <style>
#       .box{rx:14;ry:14;stroke-width:2}
#       .title{font:700 17px system-ui,-apple-system,sans-serif; fill:#20304a}
#       .sub{font:12px system-ui,-apple-system,sans-serif; fill:#4b5f7d}
#       .label{font:12px system-ui,-apple-system,sans-serif; fill:#334e77}
#       .small{font:11px system-ui,-apple-system,sans-serif; fill:#54657f}
#       .legend{font:12px system-ui,-apple-system,sans-serif; fill:#42536d}
#     </style>
#   </defs>

#   <rect x="20" y="20" width="1140" height="680" rx="18" fill="#f6f9ff" stroke="#d5dce8"/>

#   <rect class="box" x="40" y="60" width="150" height="70" fill="#ffffff" stroke="#8096bc"/>
#   <text x="115" y="92" text-anchor="middle" class="title">User</text>
#   <text x="115" y="112" text-anchor="middle" class="small">ask questions</text>

#   <rect class="box" x="230" y="48" width="250" height="92" fill="#eef4ff" stroke="#5f7fb9"/>
#   <text x="355" y="80" text-anchor="middle" class="title">Manager</text>
#   <text x="355" y="102" text-anchor="middle" class="sub">rewrite prompt · detect topic switch</text>
#   <text x="355" y="120" text-anchor="middle" class="sub">prepare clarification questions · summarize round</text>

#   <rect class="box" x="530" y="48" width="245" height="92" fill="#ecfff7" stroke="#4a9a78"/>
#   <text x="652" y="80" text-anchor="middle" class="title">NL2SQL Worker</text>
#   <text x="652" y="102" text-anchor="middle" class="sub">single-turn SQL generation</text>
#   <text x="652" y="120" text-anchor="middle" class="sub">inspect schema · execute SQL · return answer</text>

#   <rect class="box" x="830" y="42" width="285" height="104" fill="#fff7ec" stroke="#c58e49"/>
#   <text x="973" y="75" text-anchor="middle" class="title">Database + Tools</text>
#   <text x="973" y="97" text-anchor="middle" class="sub">SQLite schema</text>
#   <text x="973" y="114" text-anchor="middle" class="sub">SQL execution · result tables</text>

#   <rect class="box" x="40" y="195" width="285" height="100" fill="#fff1f1" stroke="#c56a6a"/>
#   <text x="182" y="227" text-anchor="middle" class="title">Issue Detector</text>
#   <text x="182" y="250" text-anchor="middle" class="sub">candidate generation</text>
#   <text x="182" y="268" text-anchor="middle" class="sub">pairwise ambiguity detection</text>

#   <rect class="box" x="370" y="195" width="260" height="100" fill="#f5f0ff" stroke="#9a7acc"/>
#   <text x="500" y="227" text-anchor="middle" class="title">Evaluator</text>
#   <text x="500" y="250" text-anchor="middle" class="sub">merge overlapping ambiguity entries</text>
#   <text x="500" y="268" text-anchor="middle" class="sub">score options with execution evidence</text>

#   <rect class="box" x="690" y="195" width="250" height="100" fill="#fffdf5" stroke="#d4b34a"/>
#   <text x="815" y="227" text-anchor="middle" class="title">Preference Learner</text>
#   <text x="815" y="250" text-anchor="middle" class="sub">base.json preference store</text>
#   <text x="815" y="268" text-anchor="middle" class="sub">retrieve prior clarification decisions</text>

#   <rect class="box" x="40" y="340" width="290" height="95" fill="#f5fbff" stroke="#7392bf"/>
#   <text x="185" y="372" text-anchor="middle" class="title">SystemState + UI</text>
#   <text x="185" y="394" text-anchor="middle" class="sub">rounds · nodes · attended IDs</text>
#   <text x="185" y="412" text-anchor="middle" class="sub">node chain · clarification panel · DB inspector</text>

#   <rect class="box" x="375" y="340" width="250" height="95" fill="#f8f1ff" stroke="#b48ad6"/>
#   <text x="500" y="372" text-anchor="middle" class="title">Compactor</text>
#   <text x="500" y="394" text-anchor="middle" class="sub">summarize old rounds only</text>
#   <text x="500" y="412" text-anchor="middle" class="sub">reset manager memory with compressed context</text>

#   <rect class="box" x="675" y="340" width="300" height="95" fill="#ffffff" stroke="#7392bf"/>
#   <text x="825" y="372" text-anchor="middle" class="title">Clarification Questions</text>
#   <text x="825" y="394" text-anchor="middle" class="sub">preselected suggestions + user choices</text>
#   <text x="825" y="412" text-anchor="middle" class="sub">updates future rounds and preference base</text>

#   <rect class="box" x="40" y="500" width="1120" height="130" fill="#ffffff" stroke="#7392bf"/>
#   <text x="600" y="533" text-anchor="middle" class="title">Node history and round lifecycle</text>
#   <text x="600" y="555" text-anchor="middle" class="sub">SQL_GEN · CAND_GEN · AMBI_DETECT · AMBI_EVAL · PREFERENCE_SAVE · COMPACT_SUMMARY</text>
#   <text x="600" y="577" text-anchor="middle" class="sub">attended IDs connect the next round; user-selected clarification answers feed the preference base</text>
#   <text x="600" y="599" text-anchor="middle" class="sub">tech mode shows detailed traces; non-tech mode keeps the user-facing summary concise</text>

#   <line x1="190" y1="95" x2="230" y2="95" stroke="#2f4f8f" stroke-width="2.5" marker-end="url(#arrowBlue)"/>
#   <text x="208" y="86" text-anchor="middle" class="label">ask question</text>

#   <line x1="480" y1="95" x2="530" y2="95" stroke="#2f4f8f" stroke-width="2.5" marker-end="url(#arrowBlue)"/>
#   <text x="505" y="86" text-anchor="middle" class="label">enhanced prompt</text>

#   <line x1="775" y1="95" x2="830" y2="95" stroke="#c58e49" stroke-width="2.5" marker-end="url(#arrowAmber)"/>
#   <text x="801" y="86" text-anchor="middle" class="label">exec SQL / get schema</text>

#   <line x1="830" y1="122" x2="775" y2="122" stroke="#c58e49" stroke-width="2.2" marker-end="url(#arrowAmber)"/>
#   <text x="801" y="137" text-anchor="middle" class="label">schema info / exec result</text>

#   <line x1="652" y1="140" x2="652" y2="195" stroke="#2f4f8f" stroke-width="2.5" marker-end="url(#arrowBlue)"/>
#   <text x="664" y="174" class="label">step callback</text>

#   <line x1="305" y1="245" x2="370" y2="245" stroke="#2f4f8f" stroke-width="2.5" marker-end="url(#arrowBlue)"/>
#   <text x="337" y="235" text-anchor="middle" class="label">return issues</text>

#   <line x1="630" y1="245" x2="690" y2="245" stroke="#2f4f8f" stroke-width="2.5" marker-end="url(#arrowBlue)"/>
#   <text x="660" y="235" text-anchor="middle" class="label">score options</text>

#   <line x1="812" y1="295" x2="812" y2="340" stroke="#6a7a95" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrowGray)"/>
#   <text x="823" y="324" class="small">prepared questions</text>

#   <line x1="355" y1="140" x2="355" y2="195" stroke="#6a7a95" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrowGray)"/>
#   <text x="366" y="174" class="small">manager chooses flow</text>

#   <line x1="185" y1="340" x2="185" y2="295" stroke="#6a7a95" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrowGray)"/>
#   <text x="196" y="322" class="small">selected nodes</text>

#   <line x1="500" y1="295" x2="500" y2="340" stroke="#c58e49" stroke-width="2.2" marker-end="url(#arrowAmber)"/>
#   <text x="512" y="324" class="small">persist / summarize</text>

#   <line x1="500" y1="435" x2="500" y2="500" stroke="#c58e49" stroke-width="2.2" marker-end="url(#arrowAmber)"/>
#   <text x="512" y="469" class="small">old rounds compacted</text>

#   <line x1="815" y1="295" x2="815" y2="500" stroke="#6a7a95" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrowGray)"/>
#   <text x="826" y="470" class="small">answered clarifications</text>

#   <line x1="185" y1="435" x2="185" y2="500" stroke="#6a7a95" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrowGray)"/>
#   <text x="196" y="469" class="small">round headers + attended IDs</text>

#   <line x1="355" y1="435" x2="355" y2="500" stroke="#6a7a95" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrowGray)"/>
#   <text x="366" y="469" class="small">manager summary</text>

#   <text x="48" y="676" class="legend">Blue arrows: main workflow. Gray dashed arrows: state / clarification / selection flow. Amber arrows: database and persistence interactions.</text>
# </svg>
# """.strip()

#     svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
#     return f"""
#     <div class='intro-arch-root'>
#       <style>
#         .intro-arch-root {{
#           border: 1px solid #d5dce8;
#           border-radius: 12px;
#           background: #fbfcfe;
#           padding: 12px;
#           margin-top: 8px;
#           overflow-x: auto;
#         }}
#         .intro-arch-title {{
#           font-size: 16px;
#           font-weight: 700;
#           color: #24324a;
#           margin-bottom: 8px;
#         }}
#         .intro-arch-img {{
#           width: 100%;
#           height: auto;
#           display: block;
#         }}
#       </style>
#       <div class='intro-arch-title'>Architecture and Conversation Lifecycle</div>
#       <img class='intro-arch-img' src='data:image/svg+xml;base64,{svg_b64}' alt='PEARL architecture diagram' />
#     </div>
#     """.strip()


# INTRO_ARCHITECTURE_HTML = _build_current_architecture_html()
  