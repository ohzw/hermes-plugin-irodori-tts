import {describe, expect, it} from 'vitest';
import {destinationFromPath, pathForDestination} from '../src/routing';

describe('standalone dashboard routing', () => {
  it.each([
    ['/workspace', 'workspace'],
    ['/overview', 'overview'],
    ['/history', 'history'],
    ['/dictionary', 'dictionary'],
    ['/diagnostics', 'diagnostics'],
  ] as const)('maps %s to %s', (path, destination) => {
    expect(destinationFromPath(path)).toBe(destination);
    expect(pathForDestination(destination)).toBe(path);
  });

  it('canonicalizes root and unknown paths to workspace', () => {
    expect(destinationFromPath('/')).toBe('workspace');
    expect(destinationFromPath('/not-a-page')).toBe('workspace');
    expect(pathForDestination('workspace')).toBe('/workspace');
  });
});
