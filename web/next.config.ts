import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The Python project above this directory has no lockfile Next should inherit, but its
  // presence makes Next guess at the workspace root. Pin it.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
