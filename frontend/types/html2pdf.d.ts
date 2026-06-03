declare module "html2pdf.js" {
  interface Worker { set: (o: Record<string, unknown>) => Worker; from: (el: HTMLElement | string) => Worker; save: () => Promise<void> }
  function html2pdf(): Worker;
  export default html2pdf;
}
