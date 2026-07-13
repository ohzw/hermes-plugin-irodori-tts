import {useState} from 'react';
import type {FormEvent} from 'react';
import {api} from '../../shared/api';
import {Button, Switch, Textarea} from '../../components/ui';

export function Playground() {
  const [text, setText] = useState('');
  const [callLlm, setCallLlm] = useState(false);
  const [applyDictionary, setApplyDictionary] = useState(true);
  const [output, setOutput] = useState<Record<string, unknown> | null>(null);
  const [audio, setAudio] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  const preview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!text.trim()) {
      setError('Text is required.');
      return;
    }
    setError('');
    try {
      const result = await api.rewritePreview({text, call_llm: callLlm, apply_dictionary: applyDictionary});
      setOutput(result.data);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to preview text');
    }
  };

  const generate = async () => {
    if (!text.trim()) {
      setError('Text is required.');
      return;
    }
    setError('');
    try {
      const result = await api.tts({text, call_llm: callLlm, apply_dictionary: applyDictionary, format: 'mp3'});
      setAudio(result.data);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to generate audio');
    }
  };

  return (
    <section className="playground">
      <div className="page-heading playground-heading">
        <div><div className="eyebrow">PLAYGROUND</div><h2>Playground</h2><p>Preview the rewrite or generate audio without leaving your workspace.</p></div>
      </div>
      <form className="playground-form" onSubmit={preview}>
        <label className="field-label" htmlFor="playground-text">Input text</label>
        <Textarea id="playground-text" name="text" value={text} onChange={(event) => setText(event.target.value)} rows={7} placeholder="Write a line to synthesize" />
        <div className="playground-options">
          <label><Switch checked={callLlm} onChange={(event) => setCallLlm(event.target.checked)} /> Call LLM</label>
          <label><Switch checked={applyDictionary} onChange={(event) => setApplyDictionary(event.target.checked)} /> Apply dictionary</label>
        </div>
        <div className="playground-actions"><Button type="submit" variant="outline">Preview</Button><Button type="button" id="playground-tts-button" onClick={() => void generate()}>Generate TTS</Button></div>
      </form>
      {error && <div className="shell-alert" role="alert">{error}</div>}
      {output && <div id="playground-output" className="playground-output"><pre>{JSON.stringify(output, null, 2)}</pre></div>}
      {audio && <div id="playground-audio-result" className="audio-result"><p>Generated {String(audio.bytes || 0)} bytes in {String((audio.timing_ms as Record<string, unknown> || {}).total || 0)} ms.</p>{typeof audio.data_url === 'string' && <audio controls preload="metadata" src={audio.data_url} />}</div>}
    </section>
  );
}
