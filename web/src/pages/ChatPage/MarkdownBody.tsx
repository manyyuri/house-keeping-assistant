/** 助手回复的 markdown 渲染 + 长文折叠（手机阅读优化）。
 *
 * - react-markdown + remark-gfm：标题/列表/表格/加粗正确呈现
 * - 中文长文排版：15px / 1.75 行高，标题按聊天气泡分级缩小
 * - 完成后超过阈值的长回复折叠为预览 + 「展开全文」；流式输出中始终展开
 */

import { memo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** 超过该字符数的已完成回复才折叠（中文约 500 字 ≈ 手机 25 行） */
const COLLAPSE_THRESHOLD = 500;

interface Props {
  content: string;
  /** 消息完成（非流式）才可能折叠 */
  finished: boolean;
}

function MarkdownBody({ content, finished }: Props) {
  const [expanded, setExpanded] = useState(false);
  const collapsible = finished && content.length > COLLAPSE_THRESHOLD;
  const collapsed = collapsible && !expanded;

  return (
    <div className={`md-collapse-wrapper${collapsed ? ' md-collapsed' : ''}`}>
      <div className="md-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      {collapsible && (
        <button
          type="button"
          className={`md-expand-btn${collapsed ? '' : ' md-collapse-mode'}`}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {collapsed ? `展开全文（${content.length} 字）` : '收起'}
        </button>
      )}
    </div>
  );
}

export default memo(MarkdownBody);
