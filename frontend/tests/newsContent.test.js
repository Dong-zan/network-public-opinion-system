import test from 'node:test'
import assert from 'node:assert/strict'

import {
  NEWS_CONTENT_PREVIEW_LENGTH,
  buildNewsContentPresentation,
} from '../src/utils/newsContent.js'

test('short news content stays fully visible without an expand control', () => {
  const content = '  这是一段不足五百字的新闻正文。\n'
  const result = buildNewsContentPresentation(content)

  assert.equal(result.displayContent, content)
  assert.equal(result.isLong, false)
})

test('long news content defaults to the first 500 characters', () => {
  const content = '新'.repeat(NEWS_CONTENT_PREVIEW_LENGTH + 1)
  const result = buildNewsContentPresentation(content)

  assert.equal(result.displayContent, `${'新'.repeat(NEWS_CONTENT_PREVIEW_LENGTH)}…`)
  assert.equal(result.isLong, true)
})

test('expanded long news content shows the complete text', () => {
  const content = '原文'.repeat(NEWS_CONTENT_PREVIEW_LENGTH)
  const result = buildNewsContentPresentation(content, true)

  assert.equal(result.displayContent, content)
  assert.equal(result.isLong, true)
})

test('preview length counts unicode characters without splitting emoji', () => {
  const content = `${'闻'.repeat(NEWS_CONTENT_PREVIEW_LENGTH - 1)}😀结尾`
  const result = buildNewsContentPresentation(content)

  assert.equal(result.displayContent, `${'闻'.repeat(NEWS_CONTENT_PREVIEW_LENGTH - 1)}😀…`)
})
