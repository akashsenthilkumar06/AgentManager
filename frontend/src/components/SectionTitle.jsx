export default function SectionTitle({ eyebrow, title, children }) {
  return <div className="section-title"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{children}</div>;
}

