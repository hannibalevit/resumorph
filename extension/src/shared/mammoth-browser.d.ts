declare module "mammoth/mammoth.browser" {
  export type MammothMessage = {
    type: string;
    message: string;
  };

  export type ExtractRawTextResult = {
    value: string;
    messages: MammothMessage[];
  };

  export function extractRawText(input: { arrayBuffer: ArrayBuffer }): Promise<ExtractRawTextResult>;

  const mammoth: {
    extractRawText: typeof extractRawText;
  };

  export default mammoth;
}
