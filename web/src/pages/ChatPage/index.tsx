/** 对话页（核心）：X Bubble.List + Sender + Attachments + SSE 流式。 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  App as AntApp,
  Button,
  Empty,
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
import type { AttachmentsRef } from '@ant-design/x/es/attachments';
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

const { Text } = Typography;
const { message: antdMessage } = AntApp.useApp();

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
  const activeId = useConversationStore((s) => s.activeId);
  const bumpVersion = useBusinessStore((s) => s.bumpVersion);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [generating, setGenerating] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const fileMapRef = useRef<Map<string, File>>(new Map());
  const abortRef = useRef<AbortController | null>(null);
  const attRef = useRef<AttachmentsRef>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

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
  }, []);

  const addFiles = useCallback(
    async (files: File[]) => {
      const remain = 4 - fileList.length;
      if (remain <= 0) {
        antdMessage.warning('一次最多携带 4 张照片');
        return;
      }
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
      if (!activeId || !text.trim()) return;
      const photoIds = fileList
        .filter((f) => f.status === 'done')
        .map((f) => (f.response as unknown as PhotoUploadResult)?.photoId)
        .filter((x): x is number => typeof x === 'number');

      const assistantId = nextId();
      setMessages((ms) => [
        ...ms,
        {
          id: nextId(),
          role: 'user',
          content: text,
          thoughts: [],
          status: 'done',
          photos: fileList
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

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await api.streamChat({
          conversationId: activeId,
          message: text,
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
      }
    },
    [activeId, fileList, handleEvent, patchAssistant],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // ---------- 渲染 ----------

  const renderMessage = (m: ChatMessage) => {
    if (m.role === 'user') {
      return (
        <div>
          {m.photos?.length ? (
            <div style={{ display: 'flex', gap: 6, marginBottom: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {m.photos.map((p) => (
                <Image key={p.photoId} src={p.url} alt="用户上传照片" width={64} height={64} style={{ objectFit: 'cover', borderRadius: 8 }} />
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
          <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
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
          <Empty
            style={{ marginTop: 64 }}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span>
                拍一张衣柜、杂物堆或房间角落的照片
                <br />
                <Text type="secondary">我来按断舍离帮你评估物品、生成整理计划</Text>
              </span>
            }
          />
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
            if (files.length) void addFiles(files);
          }}
        />
        <Sender
          value={inputValue}
          onChange={setInputValue}
          loading={generating}
          onCancel={stop}
          onSubmit={send}
          placeholder="描述你的整理需求，如：帮我按断舍离整理这个衣柜"
          prefix={
            <Button
              type="text"
              icon={<CameraOutlined />}
              onClick={() => cameraInputRef.current?.click()}
              title="拍照上传"
            />
          }
          header={
            <>
              <Attachments
                ref={attRef}
                accept="image/*"
                multiple
                items={fileList}
                beforeUpload={beforeUpload}
                onChange={({ fileList: fl }) => {
                  // 移除时同步清理
                  setFileList(fl.filter((f) => f.status !== 'removed'));
                }}
                placeholder={{ icon: <PictureOutlined />, title: '添加照片（相册）' }}
              />
              {hasFailed && (
                <Button size="small" icon={<ReloadOutlined />} onClick={retryFailed} style={{ marginTop: 4 }}>
                  重试失败照片
                </Button>
              )}
            </>
          }
        />
      </div>
    </div>
  );
}
