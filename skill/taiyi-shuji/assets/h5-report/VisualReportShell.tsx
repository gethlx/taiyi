import { useEffect, type ReactNode } from "react";
import "./taiyi-visual-report.css";

export type LinkKind = "primary" | "conditional" | "unknown";

export type H5ReportViewModel = {
  schemaVersion: "1.0";
  identity: {
    runId: string;
    resultId: string;
    taskType: string;
    resultIdentity: string;
    projectionSchemaVersion: string;
    projectionSha256: string;
  };
  header: {
    title: string;
    scopeLabel: string;
    brandSignature: string;
    heroVisual: string;
    heroAlt: string;
    flow: string[];
    linkKinds?: LinkKind[];
  };
  overview: {
    summary: string;
    nodes: Array<{ label: string; detail: string }>;
    links: Array<{ from: number; to: number; kind: LinkKind }>;
  };
  facts: { confirmed: string[]; unknown: string[] };
  professional: {
    r0Excerpt: string;
    r0Explanation: string;
    r1Label?: string;
    r1Excerpt?: string;
    r1Explanation?: string;
    scope: string;
  };
  mechanism: { steps: string[] };
  treatment?: {
    centerLabel: string;
    items: Array<{ title: string; detail: string }>;
  };
  formula?: {
    lead: string;
    centerLabel: string;
    visual?: string;
    groups: Array<{ title: string; detail: string }>;
    ingredients: string[];
    executionFacts: string[];
  };
  observation?: {
    premise: string;
    stages: Array<{ label: string; positive: string; contrary: string }>;
  };
  boundaries: {
    supported: string[];
    questions: string[];
    auditTitle?: string;
    auditSummary?: string;
  };
};

const sectionNumerals = ["壹", "贰", "叁", "肆", "伍", "陆", "柒"];

function polarPoints(count: number, cx: number, cy: number, radius: number) {
  return Array.from({ length: count }, (_, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count;
    return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
  });
}

function short(value: string, length = 10) {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function Section({ id, index, eyebrow, title, children }: {
  id: string;
  index: number;
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="taiyi-section">
      <div className="taiyi-chapter-stud" aria-hidden="true">
        <span>{sectionNumerals[index - 1]}</span>
      </div>
      <div className="taiyi-section-heading">
        <p>{String(index).padStart(2, "0")} · {eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Legend() {
  return (
    <figcaption className="taiyi-legend" aria-label="关系图例">
      <span><i className="taiyi-line taiyi-line--primary" />主要关系</span>
      <span><i className="taiyi-line taiyi-line--conditional" />条件关系</span>
      <span><i className="taiyi-line taiyi-line--unknown" />待确认</span>
    </figcaption>
  );
}

function HeaderFlow({ labels, kinds = [] }: { labels: string[]; kinds?: LinkKind[] }) {
  const shown = labels.slice(0, 4);
  const gap = 256 / Math.max(1, shown.length - 1);
  const positions = shown.map((_, index) => 32 + index * gap);
  return (
    <figure className="taiyi-header-flow">
      <svg viewBox="0 0 320 72" role="img" aria-label="报告核心关系">
        <defs>
          <marker id="taiyi-header-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0 0 L8 4 L0 8 Z" fill="context-stroke" />
          </marker>
        </defs>
        {positions.slice(0, -1).map((x, index) => (
          <line key={x} x1={x + 26} y1="35" x2={positions[index + 1] - 26} y2="35"
            className={`taiyi-header-link taiyi-header-link--${kinds[index] ?? "primary"}`}
            markerEnd="url(#taiyi-header-arrow)" />
        ))}
        {shown.map((label, index) => (
          <g key={`${label}-${index}`} className={`taiyi-header-node ${index === Math.floor(shown.length / 2) ? "is-center" : ""}`}
            transform={`translate(${positions[index]} 35)`}>
            <circle r={index === Math.floor(shown.length / 2) ? 29 : 24} />
            <text textAnchor="middle" y="3">{short(label, 6)}</text>
          </g>
        ))}
      </svg>
      <Legend />
    </figure>
  );
}

function RelationMap({ model }: { model: H5ReportViewModel["overview"] }) {
  const points = polarPoints(model.nodes.length, 160, 124, model.nodes.length <= 4 ? 84 : 92);
  return (
    <figure className="taiyi-diagram taiyi-relation-map">
      <svg viewBox="0 0 320 248" role="img" aria-label="核心关系图">
        <defs>
          <marker id="taiyi-relation-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 Z" fill="context-stroke" />
          </marker>
        </defs>
        {model.links.map((link, index) => {
          const from = points[link.from];
          const to = points[link.to];
          if (!from || !to) return null;
          return <line key={index} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            className={`taiyi-diagram-link taiyi-diagram-link--${link.kind}`}
            markerEnd="url(#taiyi-relation-arrow)" />;
        })}
        {model.nodes.map((node, index) => (
          <g key={`${node.label}-${index}`} className={`taiyi-diagram-node taiyi-diagram-node--${index % 5 + 1}`}
            transform={`translate(${points[index].x} ${points[index].y})`}>
            <circle r={model.nodes.length > 4 ? 31 : 38} />
            <text textAnchor="middle" y="-2">{short(node.label, 7)}</text>
            <text className="taiyi-node-detail" textAnchor="middle" y="14">{short(node.detail, 8)}</text>
          </g>
        ))}
      </svg>
      <Legend />
    </figure>
  );
}

function EvidenceMap({ facts }: { facts: string[] }) {
  const shown = facts.slice(0, 4);
  return (
    <figure className="taiyi-diagram taiyi-evidence-map">
      <svg viewBox="0 0 320 210" role="img" aria-label="事实依据汇入当前判断">
        <defs>
          <marker id="taiyi-evidence-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 Z" fill="context-stroke" />
          </marker>
        </defs>
        {shown.map((fact, index) => {
          const y = 30 + index * 48;
          return <g key={`${fact}-${index}`}><rect x="8" y={y - 17} width="178" height="34" rx="17" />
            <text x="20" y={y + 4}>{short(fact, 13)}</text>
            <path d={`M188 ${y} C220 ${y}, 218 105, 245 105`} markerEnd="url(#taiyi-evidence-arrow)" /></g>;
        })}
        <circle cx="272" cy="105" r="38" />
        <text x="272" y="109" textAnchor="middle">当前判断</text>
      </svg>
    </figure>
  );
}

function PathDiagram({ steps }: { steps: string[] }) {
  const shown = steps.slice(0, 5);
  const gap = 272 / Math.max(1, shown.length - 1);
  const points = shown.map((_, index) => 24 + index * gap);
  return (
    <figure className="taiyi-diagram taiyi-path-diagram">
      <svg viewBox="0 0 320 136" role="img" aria-label="核心证机路径">
        <defs><marker id="taiyi-path-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L8 4 L0 8 Z" fill="context-stroke" /></marker></defs>
        {points.slice(0, -1).map((x, index) => <line key={x} x1={x + 19} y1="48" x2={points[index + 1] - 19} y2="48" markerEnd="url(#taiyi-path-arrow)" />)}
        {shown.map((step, index) => <g key={`${step}-${index}`} transform={`translate(${points[index]} 48)`}>
          <circle r="19" /><text className="taiyi-path-index" y="4" textAnchor="middle">{index + 1}</text>
          <text className="taiyi-path-label" y="39" textAnchor="middle">{short(step, 7)}</text>
        </g>)}
      </svg>
    </figure>
  );
}

function RadialModel({ label, items, image }: {
  label: string;
  items: Array<{ title: string; detail: string }>;
  image?: string;
}) {
  const shown = items.slice(0, 6);
  const points = polarPoints(shown.length, 160, 145, shown.length <= 4 ? 100 : 106);
  return (
    <figure className="taiyi-diagram taiyi-radial-model">
      <svg viewBox="0 0 320 290" role="img" aria-label={`${label}协同结构`}>
        {image && <image href={image} x="0" y="0" width="320" height="290" preserveAspectRatio="xMidYMid slice" />}
        <circle className="taiyi-radial-halo" cx="160" cy="145" r="59" />
        {shown.map((item, index) => <g key={`${item.title}-${index}`}>
          <line x1="160" y1="145" x2={points[index].x} y2={points[index].y} />
          <circle className={`taiyi-radial-node taiyi-radial-node--${index % 5 + 1}`} cx={points[index].x} cy={points[index].y} r="31" />
          <text x={points[index].x} y={points[index].y + 4} textAnchor="middle">{short(item.title, 6)}</text>
        </g>)}
        <circle className="taiyi-radial-center" cx="160" cy="145" r="36" />
        <text className="taiyi-radial-center-text" x="160" y="149" textAnchor="middle">{short(label, 7)}</text>
      </svg>
      <div className="taiyi-note-grid">{shown.map((item) => <p key={item.title}><strong>{item.title}</strong><span>{item.detail}</span></p>)}</div>
    </figure>
  );
}

function ObservationChart({ stages }: { stages: NonNullable<H5ReportViewModel["observation"]>["stages"] }) {
  const shown = stages.slice(0, 5);
  const gap = 250 / Math.max(1, shown.length - 1);
  const xs = shown.map((_, index) => 35 + index * gap);
  const positive = xs.map((x, i) => `${i ? "L" : "M"}${x} ${72 - i * 8}`).join(" ");
  const negative = xs.map((x, i) => `${i ? "L" : "M"}${x} ${122 + (i % 2) * 5}`).join(" ");
  return (
    <figure className="taiyi-diagram taiyi-observation">
      <svg viewBox="0 0 320 166" role="img" aria-label="观察信号双轨图">
        <path className="taiyi-positive-path" d={positive} /><path className="taiyi-negative-path" d={negative} />
        {xs.map((x, index) => <g key={x}><line className="taiyi-observation-guide" x1={x} y1="24" x2={x} y2="143" />
          <circle className="taiyi-positive-dot" cx={x} cy={72 - index * 8} r="6" />
          <circle className="taiyi-negative-dot" cx={x} cy={122 + (index % 2) * 5} r="5" />
          <text x={x} y="16" textAnchor="middle">{shown[index].label}</text></g>)}
        <text className="taiyi-positive-label" x="8" y="54">正向变化</text>
        <text className="taiyi-negative-label" x="8" y="150">反向信号</text>
      </svg>
      <div className="taiyi-observation-notes">{shown.map((stage) => <div key={stage.label}><h3>{stage.label}</h3>
        <p><i className="taiyi-signal is-positive" />{stage.positive}</p><p><i className="taiyi-signal is-negative" />{stage.contrary}</p></div>)}</div>
    </figure>
  );
}

function BoundaryDiagram({ supported, questions }: { supported: string[]; questions: string[] }) {
  return <figure className="taiyi-diagram taiyi-boundary-diagram"><svg viewBox="0 0 320 174" role="img" aria-label="结论边界">
    <ellipse className="is-supported" cx="118" cy="84" rx="92" ry="60" />
    <ellipse className="is-unknown" cx="202" cy="84" rx="92" ry="60" />
    <text x="84" y="62" textAnchor="middle">当前支持</text><text x="236" y="62" textAnchor="middle">仍待确认</text>
    <text className="taiyi-boundary-center" x="160" y="92" textAnchor="middle">结论边界</text>
    <text className="taiyi-boundary-small" x="82" y="111" textAnchor="middle">{short(supported[0] ?? "", 8)}</text>
    <text className="taiyi-boundary-small" x="238" y="111" textAnchor="middle">{short(questions[0] ?? "", 8)}</text>
  </svg></figure>;
}

function BulletList({ items }: { items: string[] }) {
  return <ul className="taiyi-bullets">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

export function VisualReportShell({ report }: { report: H5ReportViewModel }) {
  useEffect(() => { document.title = `${report.header.title}｜${report.header.brandSignature}`; }, [report.header]);
  const sections = ["overview", "facts", "mechanism", report.treatment && "treatment", report.formula && "formula", report.observation && "observation", "boundaries"].filter(Boolean) as string[];
  const labels: Record<string, string> = { overview: "总览", facts: "依据", mechanism: "证机", treatment: "治法", formula: "方药", observation: "观察", boundaries: "边界" };
  let index = 0;
  return (
    <main className="taiyi-report" data-run-id={report.identity.runId} data-result-id={report.identity.resultId}>
      <div className="taiyi-report-content">
        <header className="taiyi-hero" style={{ backgroundImage: `url(${report.header.heroVisual})` }} aria-label={report.header.heroAlt}>
          <div className="taiyi-hero-title"><h1>{report.header.title}</h1></div>
          <HeaderFlow labels={report.header.flow} kinds={report.header.linkKinds} />
          <div className="taiyi-hero-brand"><span>{report.header.scopeLabel}</span><span>{report.header.brandSignature}</span></div>
        </header>
        <nav className="taiyi-nav" aria-label="报告章节">{sections.map((id) => <a key={id} href={`#${id}`}>{labels[id]}</a>)}</nav>
        <div className="taiyi-sections">
          <Section id="overview" index={++index} eyebrow="报告结论" title="作用总览"><p className="taiyi-lead">{report.overview.summary}</p><RelationMap model={report.overview} /></Section>
          <Section id="facts" index={++index} eyebrow="分析基础" title="事实依据"><EvidenceMap facts={report.facts.confirmed} /><BulletList items={report.facts.confirmed} />
            {report.facts.unknown.length > 0 && <details className="taiyi-disclosure"><summary>待确认事实</summary><BulletList items={report.facts.unknown} /></details>}</Section>
          <Section id="mechanism" index={++index} eyebrow={report.identity.taskType === "classic_interpretation" ? "关系释义" : "关系转译"} title={report.identity.taskType === "classic_interpretation" ? "经典关系解释" : "核心证机关系"}>{report.mechanism.steps.length > 0 && <PathDiagram steps={report.mechanism.steps} />}
            <div className="taiyi-professional"><article><span>总体关系判断</span><blockquote>{report.professional.r0Excerpt}</blockquote><p>{report.professional.r0Explanation}</p></article>
              {report.professional.r1Label && report.professional.r1Excerpt && report.professional.r1Explanation && <><b aria-hidden="true">↓</b><article><span>{report.professional.r1Label}</span><blockquote>{report.professional.r1Excerpt}</blockquote><p>{report.professional.r1Explanation}</p></article></>}</div>
            <p className="taiyi-scope-note">{report.professional.scope}</p></Section>
          {report.treatment && <Section id="treatment" index={++index} eyebrow="治疗方向" title="治法结构"><RadialModel label={report.treatment.centerLabel} items={report.treatment.items} /></Section>}
          {report.formula && <Section id="formula" index={++index} eyebrow="配伍关系" title="方药协同"><p className="taiyi-lead">{report.formula.lead}</p>
            <RadialModel label={report.formula.centerLabel} items={report.formula.groups.map((item) => ({ title: item.title, detail: item.detail }))} image={report.formula.visual} />
            <details className="taiyi-disclosure"><summary>完整药味（{report.formula.ingredients.length} 味）</summary><div className="taiyi-ingredients">{report.formula.ingredients.map((item) => <span key={item}>{item}</span>)}</div></details>
            {report.formula.executionFacts.length > 0 && <div className="taiyi-execution"><strong>煎服信息</strong>{report.formula.executionFacts.map((item) => <span key={item}>{item}</span>)}</div>}</Section>}
          {report.observation && <Section id="observation" index={++index} eyebrow="服后回验" title="观察要点"><p className="taiyi-scope-note">{report.observation.premise}</p><ObservationChart stages={report.observation.stages} /></Section>}
          <Section id="boundaries" index={++index} eyebrow="结论边界" title="适用边界与待确认信息"><BoundaryDiagram supported={report.boundaries.supported} questions={report.boundaries.questions} />
            <div className="taiyi-boundary-columns"><div><h3>适用边界</h3><BulletList items={report.boundaries.supported} /></div><div><h3>待确认信息</h3><BulletList items={report.boundaries.questions} /></div></div>
            {report.boundaries.auditTitle && report.boundaries.auditSummary && <aside className="taiyi-review"><strong>{report.boundaries.auditTitle}</strong><p>{report.boundaries.auditSummary}</p></aside>}</Section>
        </div>
        <footer className="taiyi-footer"><span>{report.header.brandSignature}</span><p>专业判断的患者向可视化表达</p></footer>
      </div>
    </main>
  );
}
