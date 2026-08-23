/** 对话页（核心）：X Bubble.List + Sender + Attachments + SSE 流式。
 *  移动端以「快门」为主入口：空态大按钮直接调相机，发送自动等待照片上传完成。 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  App as AntApp,
  Button,
  Grid,
  Image,
  Tag,
  Typography,
  Upload,
} from 'antd';
import {
  CameraOutlined,
  LoadingOutlined,
  PictureOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Attachments, Bubble, Sender } from '@ant-design/x';
import type { BubbleListProps } from '@ant-design/x/es/bubble/interface';
import type { UploadFile, UploadProps } from 'antd';
import * as api from '../../api';
import { useBusinessStore, useConversationStore } from '../../stores';
import type {
  ChatMessage,
  ChatSSEEvent,
  PhotoUploadResult,
  ThoughtNode,
  VisionDonePayload,
} from '../../types';
import PlanCard from './PlanCard';
import ThoughtPanel from './ThoughtPanel';
import MarkdownBody from './MarkdownBody';

const { Text } = Typography;

const TOOL_TITLES: Record<string, string> = {
  save_items: '物品入库',
  judge_items: '三层筛子评估',
  create_plan: '生成整理计划',
  create_tasks: '拆解任务清单',
  query_items: '查询物品',
  update_task_status: '更新任务',
};

const MESSINESS_LABEL: Record<string, { text: string; color: string }> = {
  low: { text: '整洁', color: 'green' },
  medium: { text: '有些乱', color: 'orange' },
  high: { text: '混乱', color: 'red' },
};

let msgSeq = 0;
const nextId = () => `local-${Date.now()}-${msgSeq++}`;

function pathToUrl(path: string): string {
  const rel = path.startsWith('photos/') ? path.slice('photos/'.length) : path;
  return `/api/photos/${rel}`;
}

export default function ChatPage({ onGoTasks }: { onGoTasks: () => void }) {
  const { message: antdMessage } = AntApp.useApp();
  const activeId = useConversationStore((s) => s.activeId);
  const bumpVersion = useBusinessStore((s) => s.bumpVersion);
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [generating, setGenerating] = useState(false);
  const [awaitingPhotos, setAwaitingPhotos] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [flashKey, setFlashKey] = useState(0);
  const fileMapRef = useRef<Map<string, File>>(new Map());
  // 进行中的上传 promise：发送前等它们落地，避免照片被静默漏发
  const pendingRef = useRef<Map<string, Promise<void>>>(new Map());
  const waitTokenRef = useRef<{ cancelled: boolean } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Wake Lock：生成期间保持屏幕常亮，避免 iOS 锁屏掐断 SSE
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const albumInputRef = useRef<HTMLInputElement>(null);
  // fileList 的 ref 镜像：await 上传后再读最新状态，避免闭包过期
  const fileListRef = useRef<UploadFile[]>([]);

  useEffect(() => {
    fileListRef.current = fileList;
  }, [fileList]);

  // 切换会话时加载历史
  useEffect(() => {
    let alive = true;
    setMessages([]);
    if (!activeId) return;
    api
      .getConversation(activeId)
      .then((detail) => {
        if (!alive) return;
        setMessages(
          detail.messages
            .filter((m) => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({
              id: m.id,
              role: m.role as 'user' | 'assistant',
              content: m.content,
              thoughts: [],
              status: 'done' as const,
              photos:
                m.role === 'user'
                  ? m.attachments.map((a) => ({ photoId: a.photoId, url: pathToUrl(a.path) }))
                  : undefined,
            })),
        );
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [activeId]);

  // ---------- 上传（压缩 → /api/upload → photoId）----------

  const uploadOne = useCallback(async (uid: string, file: File) => {
    const task = (async () => {
      try {
        const compressed = await api.compressImage(file);
        const [res] = await api.uploadPhotos([compressed]);
        setFileList((fl) =>
          fl.map((x) =>
            x.uid === uid
              ? { ...x, status: 'done' as const, thumbUrl: res.url, response: res as unknown as UploadFile['response'] }
              : x,
          ),
        );
      } catch (e) {
        setFileList((fl) => fl.map((x) => (x.uid === uid ? { ...x, status: 'error' as const } : x)));
        antdMessage.error(`上传失败：${e instanceof Error ? e.message : e}`);
      }
    })();
    pendingRef.current.set(uid, task);
    await task.finally(() => pendingRef.current.delete(uid));
  }, []);

  const addFiles = useCallback(
    (rawFiles: File[]) => {
      const files = rawFiles.filter((f) => f.type.startsWith('image/'));
      if (!files.length) return;
      const remain = 4 - fileList.length;
      if (remain <= 0) {
        antdMessage.warning('一次最多携带 4 张照片');
        return;
      }
      setFlashKey((k) => k + 1); // 快门闪光：照片进入的一瞬
      for (const f of files.slice(0, remain)) {
        const uid = `up-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        fileMapRef.current.set(uid, f);
        setFileList((fl) => [...fl, { uid, name: f.name, status: 'uploading' }]);
        void uploadOne(uid, f);
      }
    },
    [fileList.length, uploadOne],
  );

  const retryFailed = useCallback(() => {
    fileList
      .filter((f) => f.status === 'error')
      .forEach((f) => {
        const file = fileMapRef.current.get(f.uid);
        if (file) {
          setFileList((fl) => fl.map((x) => (x.uid === f.uid ? { ...x, status: 'uploading' as const } : x)));
          void uploadOne(f.uid, file);
        }
      });
  }, [fileList, uploadOne]);

  const beforeUpload: UploadProps['beforeUpload'] = (file) => {
    void addFiles([file as unknown as File]);
    return Upload.LIST_IGNORE;
  };

  // ---------- SSE 发送 ----------

  const patchAssistant = useCallback(
    (id: string, patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) => {
      setMessages((ms) =>
        ms.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)),
      );
    },
    [],
  );

  const handleEvent = useCallback(
    (assistantId: string, ev: ChatSSEEvent) => {
      switch (ev.event) {
        case 'vision_start':
          patchAssistant(assistantId, (m) => ({
            thoughts: [
              ...m.thoughts,
              { key: 'vision', title: '识别照片', status: 'loading' as const },
            ],
          }));
          break;
        case 'vision_done': {
          const v: VisionDonePayload = ev.data;
          patchAssistant(assistantId, (m) => ({
            thoughts: m.thoughts.map((t) =>
              t.key === 'vision'
                ? {
                    ...t,
                    status: 'success' as const,
                    description: `区域：${v.room} · ${v.items.length} 类物品`,
                  }
                : t,
            ),
            vision: [...(m.vision ?? []), v],
          }));
          break;
        }
        case 'thought':
          patchAssistant(assistantId, (m) => ({
            thoughts: [...m.thoughts, { key: `thought-${m.thoughts.length}`, title: ev.data.node, status: 'success' as const }],
          }));
          break;
        case 'tool_call': {
          const title = TOOL_TITLES[ev.data.name] ?? ev.data.name;
          patchAssistant(assistantId, (m) => ({
            thoughts: [
              ...m.thoughts,
              { key: `tool-${ev.data.name}-${m.thoughts.length}`, title, status: 'loading' as const },
            ],
          }));
          break;
        }
        case 'tool_result': {
          patchAssistant(assistantId, (m) => {
            let updated = false;
            const thoughts = m.thoughts.map((t: ThoughtNode) => {
              if (!updated && t.status === 'loading') {
                updated = true;
                return { ...t, status: ev.data.ok ? ('success' as const) : ('error' as const), description: ev.data.summary };
              }
              return t;
            });
            return { thoughts };
          });
          break;
        }
        case 'message_delta':
          patchAssistant(assistantId, (m) => ({ content: m.content + ev.data.delta, status: 'streaming' }));
          break;
        case 'plan_created':
          patchAssistant(assistantId, { plan: ev.data });
          bumpVersion();
          break;
        case 'done':
          patchAssistant(assistantId, { status: 'done' });
          break;
        case 'error':
          patchAssistant(assistantId, { status: 'error', error: ev.data.message });
          break;
      }
    },
    [bumpVersion, patchAssistant],
  );

  const send = useCallback(
    async (text: string) => {
      if (!activeId) return;
      // 有照片还在上传：等它们落地再发送（局域网很快），修复「抢跑漏发照片」
      if (pendingRef.current.size > 0) {
        setAwaitingPhotos(true);
        const token = { cancelled: false };
        waitTokenRef.current = token;
        await Promise.allSettled(Array.from(pendingRef.current.values()));
        waitTokenRef.current = null;
        setAwaitingPhotos(false);
        if (token.cancelled) return;
      }
      const fl = fileListRef.current;
      const photoIds = fl
        .filter((f) => f.status === 'done')
        .map((f) => (f.response as unknown as PhotoUploadResult)?.photoId)
        .filter((x): x is number => typeof x === 'number');
      // 纯照片发送：未输入文字时补默认提示词，后端要求 message 非空
      const finalText = text.trim() || (photoIds.length ? '请根据照片帮我按断舍离的方法整理' : '');
      if (!finalText) return;

      const assistantId = nextId();
      setMessages((ms) => [
        ...ms,
        {
          id: nextId(),
          role: 'user',
          content: finalText,
          thoughts: [],
          status: 'done',
          photos: fl
            .filter((f) => f.status === 'done')
            .map((f) => {
              const res = f.response as unknown as PhotoUploadResult;
              return { photoId: res.photoId, url: res.url };
            }),
        },
        { id: assistantId, role: 'assistant', content: '', thoughts: [], status: 'loading' },
      ]);
      setInputValue('');
      setFileList([]);
      fileMapRef.current.clear();
      setGenerating(true);

      // 尝试申请屏幕常亮（iOS 16.4+ / 不支持时静默忽略）
      try {
        const nav = navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } };
        wakeLockRef.current = (await nav.wakeLock?.request('screen')) ?? null;
      } catch {
        /* 不支持则忽略 */
      }

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await api.streamChat({
          conversationId: activeId,
          message: finalText,
          photoIds,
          signal: controller.signal,
          onEvent: (ev) => handleEvent(assistantId, ev),
        });
        patchAssistant(assistantId, (m) => (m.status === 'loading' || m.status === 'streaming' ? { status: 'done' } : {}));
      } catch (e) {
        if (controller.signal.aborted) {
          patchAssistant(assistantId, (m) => ({ status: 'stopped' as const, content: m.content }));
        } else {
          patchAssistant(assistantId, { status: 'error', error: e instanceof Error ? e.message : String(e) });
        }
      } finally {
        setGenerating(false);
        abortRef.current = null;
        try {
          await wakeLockRef.current?.release();
        } catch {
          /* 忽略 */
        }
        wakeLockRef.current = null;
      }
    },
    [activeId, handleEvent, patchAssistant],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    if (waitTokenRef.current) waitTokenRef.current.cancelled = true;
  }, []);

  // ---------- 渲染 ----------

  const renderMessage = (m: ChatMessage) => {
    if (m.role === 'user') {
      return (
        <div>
          {m.photos?.length ? (
            <div style={{ display: 'flex', gap: 6, marginBottom: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {m.photos.map((p) => (
                <Image key={p.photoId} src={p.url} alt="用户上传照片" width={72} height={72} style={{ objectFit: 'cover', borderRadius: 10 }} />
              ))}
            </div>
          ) : null}
          <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
        </div>
      );
    }
    // assistant
    return (
      <div style={{ maxWidth: 420 }}>
        <ThoughtPanel nodes={m.thoughts} />
        {m.vision?.map((v) => (
          <div key={v.photoId} style={{ marginBottom: 8 }}>
            <Tag color={MESSINESS_LABEL[v.messiness]?.color ?? 'default'}>
              {v.room} · {MESSINESS_LABEL[v.messiness]?.text ?? v.messiness}
            </Tag>
            {v.items.map((it) => (
              <Tag key={it.name} style={{ marginTop: 4 }}>
                {it.name}×{it.quantity}
              </Tag>
            ))}
          </div>
        ))}
        {m.plan && <PlanCard plan={m.plan} onGoTasks={onGoTasks} />}
        {m.content ? (
          <MarkdownBody content={m.content} finished={m.status === 'done' || m.status === 'stopped'} />
        ) : m.status === 'loading' ? (
          <Text type="secondary">
            <LoadingOutlined /> 正在整理思路…
          </Text>
        ) : null}
        {m.status === 'stopped' && (
          <div>
            <Tag icon={<StopOutlined />}>已停止生成</Tag>
          </div>
        )}
        {m.status === 'error' && m.error && <Alert type="error" showIcon title={m.error} style={{ marginTop: 8 }} />}
      </div>
    );
  };

  const bubbleItems: BubbleListProps['items'] = messages.map((m) => ({
    key: m.id,
    role: m.role,
    content: m,
    contentRender: (content: unknown) => renderMessage(content as ChatMessage),
    styles: {
      content: { maxWidth: '88%' },
    },
  }));

  const hasFailed = fileList.some((f) => f.status === 'error');
  const uploadingCount = fileList.filter((f) => f.status === 'uploading').length;
  const doneCount = fileList.filter((f) => f.status === 'done').length;
  const showHeader = !isMobile || fileList.length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      {flashKey > 0 && <span key={flashKey} className="shutter-flash" aria-hidden="true" />}
      <div style={{ flex: 1, minHeight: 0, padding: '12px 8px' }}>
        {messages.length ? (
          <Bubble.List
            items={bubbleItems}
            autoScroll
            role={{
              user: { placement: 'end' },
              assistant: { placement: 'start' },
            }}
          />
        ) : (
          <div className="chat-empty">
            <div className="chat-empty-greeting">今天，想放下什么？</div>
            <button
              type="button"
              className="shutter-btn"
              onClick={() => cameraInputRef.current?.click()}
              aria-label="拍照开始整理"
            >
              <span className="shutter-btn-inner" />
            </button>
            <div className="chat-empty-hint">对准衣柜或杂物堆，按下快门</div>
            <Button type="link" size="small" onClick={() => albumInputRef.current?.click()}>
              从相册选择
            </Button>
            {!isMobile && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                也可以把照片拖进输入框，或直接粘贴
              </Text>
            )}
          </div>
        )}
      </div>

      {/* 吸底输入区（sticky，iPhone 键盘不遮挡） */}
      <div className="chat-input-area">
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: 'none' }}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = '';
            if (files.length) addFiles(files);
          }}
        />
        <input
          ref={albumInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = '';
            if (files.length) addFiles(files);
          }}
        />
        <Sender
          value={inputValue}
          onChange={setInputValue}
          loading={generating || awaitingPhotos}
          onCancel={stop}
          onSubmit={send}
          onPasteFile={(files) => addFiles(Array.from(files))}
          placeholder="描述你的整理需求，如：帮我按断舍离整理这个衣柜"
          prefix={
            <>
              <Button
                type="text"
                className="chat-tool-btn"
                icon={<CameraOutlined />}
                onClick={() => cameraInputRef.current?.click()}
                aria-label="拍照"
                title="拍照"
              />
              <Button
                type="text"
                className="chat-tool-btn"
                icon={<PictureOutlined />}
                onClick={() => albumInputRef.current?.click()}
                aria-label="从相册选择"
                title="从相册选择"
              />
            </>
          }
          header={
            showHeader ? (
              <>
                <Attachments
                  accept="image/*"
                  multiple
                  items={fileList}
                  beforeUpload={beforeUpload}
                  onChange={({ fileList: fl }) => {
                    // 移除时同步清理
                    setFileList(fl.filter((f) => f.status !== 'removed'));
                  }}
                  placeholder={{ icon: <PictureOutlined />, title: '添加照片（点击或拖拽）' }}
                />
                {uploadingCount > 0 && (
                  <Text type="secondary" style={{ fontSize: 12, marginTop: 2, display: 'block' }}>
                    照片上传中 {doneCount}/{fileList.length}…
                  </Text>
                )}
                {hasFailed && (
                  <Button size="small" icon={<ReloadOutlined />} onClick={retryFailed} style={{ marginTop: 4 }}>
                    重试失败照片
                  </Button>
                )}
              </>
            ) : false
          }
        />
      </div>
    </div>
  );
}
