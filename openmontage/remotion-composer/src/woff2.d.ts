// .woff2 imports are inlined by webpack as data: URLs
// (see remotion.config.ts).
declare module "*.woff2" {
  const dataUrl: string;
  export default dataUrl;
}
