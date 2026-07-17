export function SearchField({ value, onChange, placeholder = "Search…" }) {
  return <label className="search-field"><span>⌕</span><input type="search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></label>;
}

export function FilterChips({ options, value, onChange, label = "Filter" }) {
  return <div className="filter-chips" aria-label={label}>{options.map((option) => { const id = typeof option === "string" ? option : option.id; const text = typeof option === "string" ? option : option.label; const count = typeof option === "string" ? null : option.count; return <button key={id} className={value === id ? "active" : ""} onClick={() => onChange(id)}>{text}{count !== null && count !== undefined && <span>{count}</span>}</button>; })}</div>;
}

export function ViewToggle({ value, onChange, options }) {
  return <div className="view-toggle" aria-label="View style">{options.map(([id, icon, label]) => <button key={id} className={value === id ? "active" : ""} onClick={() => onChange(id)} title={label} aria-label={label}>{icon}</button>)}</div>;
}

export default function FilterBar({ children, resultCount, onClear, hasFilters = false }) {
  return <div className="filter-bar"><div className="filter-controls">{children}</div><div className="filter-meta"><span>{resultCount} result{resultCount === 1 ? "" : "s"}</span>{hasFilters && <button onClick={onClear}>Clear filters</button>}</div></div>;
}

