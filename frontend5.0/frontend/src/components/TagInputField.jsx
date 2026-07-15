import { useState } from 'react'

function TagInputField({ items, onChange, placeholder, suggestions = [] }) {
  const [draft, setDraft] = useState('')

  function addItem(rawValue) {
    const value = rawValue.trim()
    if (!value || items.includes(value)) {
      setDraft('')
      return
    }

    onChange([...items, value])
    setDraft('')
  }

  function removeItem(item) {
    onChange(items.filter((current) => current !== item))
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      addItem(draft)
    }

    if (event.key === 'Backspace' && !draft && items.length > 0) {
      removeItem(items[items.length - 1])
    }
  }

  return (
    <div className="tag-editor">
      <div className="tag-input-box">
        <div className="tag-list">
          {items.map((item) => (
            <span key={item} className="tag-chip">
              {item}
              <button type="button" className="tag-remove" onClick={() => removeItem(item)}>
                ×
              </button>
            </span>
          ))}
          <input
            className="tag-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => addItem(draft)}
            placeholder={placeholder}
          />
        </div>
      </div>
      <div className="suggestion-row">
        {suggestions.map((item) => (
          <button
            key={item}
            type="button"
            className="suggestion-button"
            onClick={() => addItem(item)}
          >
            + {item}
          </button>
        ))}
      </div>
    </div>
  )
}

export default TagInputField
