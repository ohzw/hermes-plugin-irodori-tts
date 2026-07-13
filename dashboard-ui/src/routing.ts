export const destinations = [
  {id: 'workspace', label: 'Workspace'},
  {id: 'overview', label: 'Overview'},
  {id: 'history', label: 'History'},
  {id: 'dictionary', label: 'Dictionary'},
  {id: 'diagnostics', label: 'Diagnostics'},
] as const;

export type Destination = typeof destinations[number]['id'];

const destinationSet = new Set<Destination>(destinations.map(({id}) => id));

export function destinationFromPath(pathname: string): Destination {
  const segment = pathname.replace(/^\/+|\/+$/g, '').split('/')[0] as Destination;
  return destinationSet.has(segment) ? segment : 'workspace';
}

export function pathForDestination(destination: Destination): string {
  return `/${destination}`;
}

export function canonicalPath(pathname: string): string {
  return pathForDestination(destinationFromPath(pathname));
}

export function navigateTo(destination: Destination): void {
  const path = pathForDestination(destination);
  if (window.location.pathname !== path) {
    window.history.pushState({destination}, '', path);
  }
  window.dispatchEvent(new PopStateEvent('popstate'));
}
