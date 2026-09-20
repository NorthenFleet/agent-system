// Local build fallback for the OpenClaw peer package, whose installed Chinese
// distribution currently omits the plugin-sdk declaration subpath.
declare module "openclaw/plugin-sdk" {
  export interface OpenClawPluginApi {
    [key: string]: any;
  }
}

