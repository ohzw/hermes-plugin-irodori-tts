/// <reference types="vite/client" />

import type {ComponentType} from 'react';

declare global {
  interface Window {
    __HERMES_PLUGIN_SDK__: {
      React: typeof import('react');
      fetchJSON?: <T>(url: string, init?: RequestInit) => Promise<T>;
      authedFetch?: (url: string, init?: RequestInit) => Promise<Response>;
    };
    __HERMES_PLUGINS__: {
      register: (name: string, component: ComponentType) => void;
      registerSlot?: (name: string, slot: string, component: ComponentType) => void;
    };
  }
}

export {};
