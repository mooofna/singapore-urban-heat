// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
  namespace App {}
}

export {};

declare module '*?worker&url' {
  const url: string;
  export default url;
}

declare module '*.md?raw' {
  const text: string;
  export default text;
}
