import './launcher.css';
import Launcher from './launcher/Launcher';

const registry = window.__HERMES_PLUGINS__;
if (!registry?.register) {
  throw new Error('Hermes dashboard plugin registry is unavailable');
}

registry.register('irodori-tts', Launcher);
