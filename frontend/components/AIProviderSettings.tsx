'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, Key, RefreshCw } from 'lucide-react';
import { AISettings, ModelFamily, getAISettings, saveAISettings, testAIConnection } from '../lib/api';

export function AIProviderSettings() {
  const [settings, setSettings] = useState<AISettings | null>(null);
  const [provider, setProvider] = useState<AISettings['provider']>('openai');
  const [family, setFamily] = useState<ModelFamily>('gemini');
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { getAISettings().then((value) => { setSettings(value); setProvider(value.provider); setFamily(value.model_family ?? 'gemini'); }).catch((e) => setMessage(e.message)); }, []);

  const save = async () => {
    setBusy(true); setMessage('');
    try { const value = await saveAISettings(provider, apiKey || undefined, family); setSettings(value); setApiKey(''); setMessage('Settings saved. Test the connection to verify the provider key.'); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Could not save settings.'); }
    finally { setBusy(false); }
  };
  const test = async () => {
    setBusy(true); setMessage('');
    try { const value = await testAIConnection(); setSettings(await getAISettings()); setMessage(value.message); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Connection test failed.'); }
    finally { setBusy(false); }
  };

  return <div className="max-w-xl mx-auto py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
    <div className="flex items-center gap-3"><Key className="w-5 h-5 text-[#F26D5B]"/><div><h3 className="text-sm font-bold">AI provider connection</h3><p className="text-xs text-[#7A6C63] dark:text-slate-400">Your encrypted key is used for AI text. Image generation keeps the existing image service configuration.</p></div></div>
    <div className="flex items-center justify-between rounded-xl bg-white dark:bg-[#0F172A] p-3 text-xs"><span>Connection status</span><span className={`font-bold ${settings?.connection_status === 'CONNECTED' ? 'text-emerald-600' : 'text-amber-600'}`}>{settings?.connection_status === 'CONNECTED' ? 'Connected' : settings?.configured ? 'Not tested' : 'Not configured'}</span></div>
    <label className="block text-xs font-semibold">AI provider<select value={provider} onChange={(e) => setProvider(e.target.value as AISettings['provider'])} className="mt-1.5 w-full rounded-xl border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-[#0F172A] p-3"><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option><option value="openrouter">OpenRouter (Gemini and OpenAI models)</option></select></label>
    {provider === 'openrouter' && <label className="block text-xs font-semibold">Models served through OpenRouter<select value={family} onChange={(e) => setFamily(e.target.value as ModelFamily)} className="mt-1.5 w-full rounded-xl border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-[#0F172A] p-3"><option value="gemini">Google Gemini models</option><option value="openai">OpenAI GPT models</option></select></label>}
    <label className="block text-xs font-semibold">API key<input type="password" autoComplete="new-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={settings?.masked_key ? 'Saved securely •••••••• (enter to replace)' : 'Enter API key'} className="mt-1.5 w-full rounded-xl border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-[#0F172A] p-3" /></label>
    {settings?.key_source === 'workspace' && <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">Using a workspace managed key. Add your own key to override it for your account.</p>}
    <div className="flex gap-2"><button disabled={busy} onClick={save} className="rounded-xl bg-[#F26D5B] px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">Save API key</button><button disabled={busy || !settings?.configured} onClick={test} className="inline-flex items-center gap-2 rounded-xl border border-[#EDE6DD] dark:border-white/10 px-4 py-2.5 text-xs font-bold disabled:opacity-50">{busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin"/> : <CheckCircle2 className="h-3.5 w-3.5"/>}Test connection</button></div>
    {message && <p role="status" className="text-xs text-[#7A6C63] dark:text-slate-300">{message}</p>}
  </div>;
}
