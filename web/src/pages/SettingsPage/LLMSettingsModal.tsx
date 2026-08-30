/** 模型设置弹窗：视觉/Agent 双端点独立配置（本地 Ollama / 云端 OpenAI 兼容 API）。 */

import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App as AntApp,
  AutoComplete,
  Button,
  Divider,
  Form,
  Input,
  Modal,
  Radio,
  Space,
  Tooltip,
  Typography,
} from 'antd';
import * as api from '../../api';
import type { LLMProviderPreset, LLMSettingsView } from '../../types';

const { Text } = Typography;

type Scope = 'vision' | 'agent';

const SECTION_TITLES: Record<Scope, string> = {
  vision: '视觉模型（看图）',
  agent: 'Agent 模型（整理顾问）',
};

const TEST_LABELS: Record<Scope, string> = { vision: '视觉', agent: 'Agent' };

const PROVIDER_OPTIONS = [
  { value: 'ollama', label: '本地 Ollama（免费离线）' },
  { value: 'openai', label: '云端 API（OpenAI 兼容）' },
];

/** readonly 字段：disabled + Tooltip 说明 */
function LockedField({ locked, children }: { locked: boolean; children: React.ReactNode }) {
  if (!locked) return <>{children}</>;
  return (
    <Tooltip title="由环境变量锁定">
      <span style={{ display: 'block', width: '100%' }}>{children}</span>
    </Tooltip>
  );
}

function EndpointFields({
  scope,
  view,
  form,
}: {
  scope: Scope;
  view: LLMSettingsView | null;
  form: ReturnType<typeof Form.useForm>[0];
}) {
  const provider = Form.useWatch([scope, 'provider'], form) ?? 'ollama';
  const baseUrl = Form.useWatch([scope, 'base_url'], form) ?? '';
  const ro = (field: string) => Boolean(view?.readonly?.[`${scope}.${field}`]);
  const masked = view?.[scope]?.api_key_masked || '';
  const presets: LLMProviderPreset[] = view?.provider_options ?? [];
  const presetOptions = useMemo(
    () =>
      presets.map((p) => ({
        value: p.base_url,
        label: `${p.label}（${p.base_url}）`,
      })),
    [presets],
  );
  const preset = presets.find((p) => p.base_url === baseUrl);
  const modelPlaceholder =
    (scope === 'vision' ? preset?.vision_model : preset?.agent_model) || '模型名，如 qwen3-vl:8b';
  const isCloud = provider === 'openai';

  return (
    <>
      <Divider titlePlacement="start" style={{ margin: '4px 0 16px' }}>
        {SECTION_TITLES[scope]}
      </Divider>
      <Form.Item name={[scope, 'provider']} label="服务商" rules={[{ required: true }]}>
        <LockedField locked={ro('provider')}>
          <Radio.Group options={PROVIDER_OPTIONS} optionType="button" buttonStyle="solid" />
        </LockedField>
      </Form.Item>
      {isCloud && (
        <Form.Item
          name={[scope, 'base_url']}
          label="接口地址（base_url）"
          rules={[
            { required: true, message: '请填写或选择 base_url' },
            { pattern: /^https?:\/\//, message: '需以 http:// 或 https:// 开头' },
          ]}
        >
          <LockedField locked={ro('base_url')}>
            <AutoComplete
              options={presetOptions}
              placeholder="选择常用服务商或直接输入，如 https://api.deepseek.com/v1"
              allowClear
            />
          </LockedField>
        </Form.Item>
      )}
      {isCloud && (
        <Form.Item
          name={[scope, 'api_key']}
          label="API Key"
          validateTrigger={false}
          rules={[
            {
              validator: async (_: unknown, value: string) => {
                if (ro('api_key')) return; // 环境变量锁定时用已存/环境值，不校验表单
                if (!value && !masked) throw new Error('请填写 api_key');
              },
            },
          ]}
        >
          <LockedField locked={ro('api_key')}>
            <Input.Password
              autoComplete="new-password"
              placeholder={masked ? `已保存 ${masked}，留空保持不变` : 'sk-…'}
            />
          </LockedField>
        </Form.Item>
      )}
      <Form.Item name={[scope, 'model']} label="模型名" rules={[{ required: true, message: '请填写模型名' }]}>
        <LockedField locked={ro('model')}>
          <Input placeholder={modelPlaceholder} />
        </LockedField>
      </Form.Item>
      {scope === 'vision' && isCloud && (
        <Text type="warning" style={{ display: 'block', marginTop: -8, marginBottom: 8 }}>
          选择云端视觉模型后，照片将上传至该服务商处理
        </Text>
      )}
    </>
  );
}

export default function LLMSettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message: antdMessage } = AntApp.useApp();
  const [form] = Form.useForm();
  const [view, setView] = useState<LLMSettingsView | null>(null);
  const [testing, setTesting] = useState<Scope | null>(null);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ scope: Scope; ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    setView(null);
    setTestResult(null);
    api
      .getLLMSettings()
      .then((v) => {
        setView(v);
        form.setFieldsValue({
          vision: { provider: v.vision.provider, base_url: v.vision.base_url, api_key: '', model: v.vision.model },
          agent: { provider: v.agent.provider, base_url: v.agent.base_url, api_key: '', model: v.agent.model },
        });
      })
      .catch((e: Error) => antdMessage.error(`加载模型设置失败：${e.message}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  /** 从表单取某一端点的提交值（ollama 只提交 provider+model，云端附完整连接信息） */
  const endpointPayload = (scope: Scope) => {
    const v = form.getFieldValue(scope) || {};
    if (v.provider === 'openai') {
      return { provider: 'openai', base_url: v.base_url, api_key: v.api_key || '', model: v.model };
    }
    return { provider: 'ollama', model: v.model };
  };

  const runTest = async (scope: Scope) => {
    setTestResult(null);
    try {
      await form.validateFields([
        [scope, 'provider'],
        [scope, 'base_url'],
        [scope, 'api_key'],
        [scope, 'model'],
      ]);
    } catch {
      return;
    }
    setTesting(scope);
    try {
      const r = await api.testLLMConnection(scope, endpointPayload(scope));
      setTestResult(
        r.ok
          ? { scope, ok: true, text: `${TEST_LABELS[scope]}通道连接成功（${r.latency_ms ?? '?'} ms）` }
          : { scope, ok: false, text: r.message },
      );
    } catch (e) {
      setTestResult({ scope, ok: false, text: (e as Error).message });
    } finally {
      setTesting(null);
    }
  };

  const onSave = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    try {
      const saved = await api.saveLLMSettings({
        vision: endpointPayload('vision'),
        agent: endpointPayload('agent'),
      });
      antdMessage.success('模型配置已保存，下次对话生效');
      saved.notices?.forEach((n) => antdMessage.warning(n, 4));
      onClose();
    } catch (e) {
      antdMessage.error(`保存失败：${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="模型设置"
      open={open}
      onCancel={onClose}
      width="min(520px, calc(100vw - 32px))"
      destroyOnHidden
      styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      footer={
        <Space wrap style={{ justifyContent: 'flex-end', width: '100%' }}>
          <Button loading={testing === 'vision'} onClick={() => void runTest('vision')}>
            测试视觉
          </Button>
          <Button loading={testing === 'agent'} onClick={() => void runTest('agent')}>
            测试 Agent
          </Button>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={() => void onSave()}>
            保存
          </Button>
        </Space>
      }
    >
      {view?.config_source === 'models.json' && (
        <Alert
          showIcon
          type="info"
          style={{ marginBottom: 12 }}
          message="模型端点由 ~/.pi/agent/models.json 的 opencode-luna 提供"
          description="密钥在此处集中管理，修改 models.json 即时生效。如需临时切换，用环境变量（如 AGENT_MODEL）覆盖。"
        />
      )}
      <Form form={form} layout="vertical" requiredMark={false}>
        <EndpointFields scope="vision" view={view} form={form} />
        <EndpointFields scope="agent" view={view} form={form} />
        {testResult && (
          <Alert
            style={{ marginTop: 8 }}
            showIcon
            type={testResult.ok ? 'success' : 'error'}
            title={
              testResult.ok
                ? testResult.text
                : `${TEST_LABELS[testResult.scope]}通道测试失败：${testResult.text}`
            }
          />
        )}
      </Form>
    </Modal>
  );
}
