import { Config } from "@remotion/cli/config";

// Inline .woff2 imports as data: URLs so font loading never touches the
// network — not even the local bundle server. Keeps renders hermetic in
// offline/locked-down environments. See src/fonts.ts.
Config.overrideWebpackConfig((config) => ({
  ...config,
  module: {
    ...config.module,
    rules: [
      ...(config.module?.rules ?? []),
      { test: /\.woff2$/, type: "asset/inline" },
    ],
  },
}));
