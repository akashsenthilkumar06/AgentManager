export default function EmptyResults({ onClear, message = "No items match these filters." }) {
  return <div className="empty-results"><span>⌕</span><strong>Nothing to show</strong><p>{message}</p>{onClear && <button onClick={onClear}>Clear filters</button>}</div>;
}

